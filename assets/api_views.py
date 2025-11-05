"""
CMDB API Views

这个模块包含了CMDB系统的所有API接口,用于处理与Agent的通信和数据交换。
主要功能包括：
1. Agent数据上报接口
2. 服务器信息查询接口
3. Agent脚本下载接口

API设计遵循RESTful原则,使用JSON格式进行数据交换。
"""
import ipaddress
import json
import os
from datetime import datetime
from django.db import transaction
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views import View
from django.conf import settings
from .models import Server, HardwareInfo, SystemConfig
from .utils import archive_server_record


def normalize_optional_ip(value):
    """将可选IP字符串规范化,无效值返回None。"""
    if value is None:
        return None
    if isinstance(value, str):
        trimmed = value.strip()
        if not trimmed or trimmed.lower() == 'null':
            return None
        try:
            ipaddress.ip_address(trimmed)
        except ValueError:
            return None
        return trimmed
    return None


@csrf_exempt
def agent_report(request):
    """
    Agent数据上报接口

    这是CMDB系统最核心的API接口,用于接收Agent上报的服务器硬件信息。
    支持新服务器注册和已有服务器的数据更新。

    请求格式:
        POST /api/agent/report/
        Content-Type: application/json

    请求体结构:
        {
            "sn": "服务器序列号",
            "management_ip": "管理IP地址",
            "bmc_ip": "可选BMC/IPMI地址",
            "hostname": "主机名",
            "hardware_info": {
                "cpu": {
                    "model": "CPU型号",
                    "architecture": "架构",
                    "physical_cores": 物理核心数,
                    "logical_cores": 逻辑核心数
                },
                "memory": {
                    "modules": [内存条列表],
                    "total_gb": 总内存GB数
                },
                "disks": [磁盘列表]
            }
        }

    响应格式:
        成功 (200): {"status": "success", "is_new": true/false, "server_id": 123, "message": "消息"}
        失败 (4xx/5xx): {"error": "错误信息", "status": "error"}

    Args:
        request: Django的HttpRequest对象

    Returns:
        JsonResponse: JSON格式的响应数据

    安全考虑:
        - 使用@csrf_exempt禁用CSRF保护（因为Agent无法获取CSRF token）
        - 验证必填字段防止恶意数据
        - 限制HTTP方法为POST

    业务逻辑:
        1. 验证请求数据格式和必填字段
        2. 根据IP地址查找或创建服务器记录
        3. 更新服务器状态和最后上报时间
        4. 处理硬件信息数据
        5. 返回处理结果
    """
    # ==================== 请求方法验证 ====================

    # 只接受POST请求,确保数据安全
    if request.method != 'POST':
        return JsonResponse({
            'error': 'Method not allowed',
            'status': 'error'
        }, status=405)

    # ==================== 数据解析和验证 ====================

    try:
        # 解析JSON格式的请求数据
        data = json.loads(request.body.decode('utf-8'))

        # 验证必填字段：服务器序列号
        sn = data.get('sn')
        if not sn:
            return JsonResponse({
                'error': 'SN is required',
                'status': 'error'
            }, status=400)

        # 验证必填字段：管理IP地址
        management_ip = data.get('management_ip')
        if not management_ip:
            return JsonResponse({
                'error': 'management_ip is required',
                'status': 'error'
            }, status=400)

        # 获取可选字段
        hostname = data.get('hostname', '')
        bmc_ip_provided = 'bmc_ip' in data
        bmc_ip = normalize_optional_ip(data.get('bmc_ip')) if bmc_ip_provided else None
        hardware_info = data.get('hardware_info', {})

        # ==================== 服务器记录处理 ====================

        # 查找或创建服务器记录
        # 优先使用IP地址查找,避免临时SN导致重复记录
        is_new = False  # 标记是否为新服务器

        now = timezone.now()

        with transaction.atomic():
            server_by_ip = (
                Server.objects.select_for_update()
                .filter(management_ip=management_ip)
                .order_by('-updated_at')
                .first()
            )
            server_by_sn = (
                Server.objects.select_for_update()
                .filter(sn=sn)
                .order_by('-updated_at')
                .first()
            )

            if server_by_sn and server_by_ip and server_by_sn.id == server_by_ip.id:
                server = server_by_sn
                is_new = False
            else:
                if server_by_sn:
                    reason = 'sn_ip_changed' if server_by_sn.management_ip != management_ip else 'sn_duplicate'
                    archive_server_record(server_by_sn, reason=reason)

                if server_by_ip:
                    archive_server_record(server_by_ip, reason='ip_reused_by_new_sn')

                server = Server.objects.create(
                    sn=sn,
                    hostname=hostname,
                    management_ip=management_ip,
                    bmc_ip=bmc_ip if bmc_ip_provided else None,
                    status='online',
                    last_report_time=now
                )
                is_new = True

            if not is_new:
                server.sn = sn
                server.hostname = hostname
                if server.management_ip != management_ip:
                    server.management_ip = management_ip
                if bmc_ip_provided:
                    server.bmc_ip = bmc_ip
                server.status = 'online'
                server.last_report_time = now
                update_fields = ['sn', 'hostname', 'management_ip', 'status', 'last_report_time']
                if bmc_ip_provided:
                    update_fields.append('bmc_ip')
                server.save(update_fields=update_fields)

        # ==================== 硬件信息处理 ====================

        # 处理v2.0数据结构的硬件信息
        if hardware_info:
            # 提取CPU信息
            cpu_info = hardware_info.get('cpu', {})

            # 提取内存信息
            memory_info = hardware_info.get('memory', {})
            memory_modules = memory_info.get('modules', [])  # 内存条详细信息列表
            memory_total_gb = memory_info.get('total_gb', 0)  # 总内存容量

            # 提取磁盘信息
            disks = hardware_info.get('disks', [])  # 磁盘设备列表

            # 准备硬件信息数据
            hw_data = {
                'cpu_info': cpu_info,
                'memory_modules': memory_modules,
                'memory_total_gb': memory_total_gb,
                'disks': disks,
                'raw_data': data  # 保存完整的原始数据,用于调试
            }

            # 使用update_or_create方法更新或创建硬件信息记录
            # 这样可以确保每台服务器只有一条硬件信息记录
            HardwareInfo.objects.update_or_create(
                server=server,
                defaults=hw_data
            )

        # ==================== 响应返回 ====================

        return JsonResponse({
            'status': 'success',
            'is_new': is_new,
            'server_id': server.id,
            'message': '新服务器已注册' if is_new else '数据已更新'
        })

    # ==================== 异常处理 ====================

    except json.JSONDecodeError:
        # JSON解析错误
        return JsonResponse({
            'error': 'Invalid JSON',
            'status': 'error'
        }, status=400)

    except Exception as e:
        # 其他未预期的异常
        return JsonResponse({
            'error': str(e),
            'status': 'error'
        }, status=500)


def server_list(request):
    """
    服务器列表API接口

    提供所有服务器的列表信息,支持分页和过滤功能。
    可以用于监控系统集成、数据展示等场景。

    请求格式:
        GET /api/servers/

    查询参数:
        - 无（未来可扩展分页、搜索、过滤参数）

    响应格式:
        {
            "count": 服务器总数,
            "results": [
                {
                    "id": 服务器ID,
                    "sn": "序列号",
                    "hostname": "主机名",
                    "management_ip": "管理IP",
                    "status": "状态",
                    "last_report_time": "最后上报时间(ISO格式)",
                    "agent_deployed": true/false,
                    "created_at": "创建时间(ISO格式)"
                }
            ]
        }

    Args:
        request: Django的HttpRequest对象

    Returns:
        JsonResponse: 包含服务器列表的JSON响应

    使用场景:
        - 监控系统集成
        - 前端页面数据展示
        - 数据导出和分析
    """
    # ==================== 请求方法验证 ====================

    # 只接受GET请求
    if request.method != 'GET':
        return JsonResponse({
            'error': 'Method not allowed'
        }, status=405)

    try:
        # ==================== 数据查询 ====================

        # 获取所有服务器,按创建时间倒序排列
        servers = Server.objects.all().order_by('-created_at')

        # ==================== 数据序列化 ====================

        # 将数据库查询结果转换为JSON格式
        results = []
        for server in servers:
            server_data = {
                'id': server.id,
                'sn': server.sn,
                'hostname': server.hostname,
                'management_ip': server.management_ip,
                'status': server.status,
                # 时间字段转换为ISO格式字符串,如果为空则为None
                'last_report_time': server.last_report_time.isoformat() if server.last_report_time else None,
                'agent_deployed': server.agent_deployed,
                'created_at': server.created_at.isoformat(),
            }
            results.append(server_data)

        # ==================== 响应返回 ====================

        return JsonResponse({
            'count': len(results),
            'results': results
        })

    except Exception as e:
        # 异常处理,返回错误信息
        return JsonResponse({
            'error': str(e)
        }, status=500)


def server_detail(request, server_id):
    """
    服务器详情API接口

    获取指定服务器的详细信息,包括基本信息和完整的硬件配置。
    这是server_list接口的详细信息版本。

    请求格式:
        GET /api/servers/{server_id}/

    路径参数:
        - server_id: 服务器的数据库主键ID

    响应格式:
        成功 (200): {
            "id": 服务器ID,
            "sn": "序列号",
            "hostname": "主机名",
            "management_ip": "管理IP",
            "status": "状态",
            "last_report_time": "最后上报时间",
            "created_at": "创建时间",
            "updated_at": "更新时间",
            "agent_deployed": true/false,
            "agent_version": "Agent版本",
            "hardware": {
                "cpu_info": CPU详细信息,
                "memory_modules": 内存条信息列表,
                "memory_total_gb": 总内存GB数,
                "disks": 磁盘信息列表,
                "collected_at": "数据采集时间",
                "raw_data": 原始上报数据
            }
        }

        失败 (404): {"error": "Server not found"}
        失败 (500): {"error": "错误信息"}

    Args:
        request: Django的HttpRequest对象
        server_id: 服务器ID

    Returns:
        JsonResponse: 包含服务器详情的JSON响应

    使用场景:
        - 服务器详细信息展示
        - 硬件配置分析
        - 监控系统集成
    """
    # ==================== 请求方法验证 ====================

    # 只接受GET请求
    if request.method != 'GET':
        return JsonResponse({
            'error': 'Method not allowed'
        }, status=405)

    try:
        # ==================== 数据查询 ====================

        # 根据ID查询服务器,如果不存在会抛出DoesNotExist异常
        server = Server.objects.get(id=server_id)

        # ==================== 基本信息序列化 ====================

        # 构建基本服务器信息
        result = {
            'id': server.id,
            'sn': server.sn,
            'hostname': server.hostname,
            'management_ip': server.management_ip,
            'status': server.status,
            'last_report_time': server.last_report_time.isoformat() if server.last_report_time else None,
            'created_at': server.created_at.isoformat(),
            'updated_at': server.updated_at.isoformat(),
            'agent_deployed': server.agent_deployed,
            'agent_version': server.agent_version,
        }

        # ==================== 硬件信息处理 ====================

        # 检查服务器是否有关联的硬件信息
        if hasattr(server, 'hardware'):
            hardware = server.hardware

            # 添加v2.0数据结构的硬件信息
            result['hardware'] = {
                'cpu_info': hardware.cpu_info,
                'memory_modules': hardware.memory_modules,
                'memory_total_gb': hardware.memory_total_gb,
                'disks': hardware.disks,
                'collected_at': hardware.collected_at.isoformat(),
                'raw_data': hardware.raw_data  # 包含原始上报数据
            }

        # ==================== 响应返回 ====================

        return JsonResponse(result)

    # ==================== 异常处理 ====================

    except Server.DoesNotExist:
        # 服务器不存在
        return JsonResponse({
            'error': 'Server not found'
        }, status=404)

    except Exception as e:
        # 其他异常
        return JsonResponse({
            'error': str(e)
        }, status=500)


def agent_script(request):
    """
    Agent脚本下载接口

    提供Agent脚本文件的下载服务,用于服务器自动部署Agent。
    包含IP白名单验证,确保只有授权的IP可以下载脚本。

    请求格式:
        GET /api/agent/script/

    安全机制:
        1. IP白名单验证：只允许配置的IP网段访问
        2. 代理IP识别：正确处理X-Forwarded-For头
        3. 文件安全检查：确保脚本文件存在且可读

    响应格式:
        成功 (200): 返回agent.py脚本内容,Content-Type为text/plain
        失败 (403): IP不在白名单中
        失败 (404): 脚本文件不存在
        失败 (500): 服务器内部错误

    Args:
        request: Django的HttpRequest对象

    Returns:
        HttpResponse: Agent脚本文件内容或错误信息

    安全考虑:
        - IP白名单验证防止未授权访问
        - 处理代理服务器的X-Forwarded-For头
        - 文件路径安全检查,防止路径遍历攻击
    """
    # ==================== 请求方法验证 ====================

    # 只接受GET请求
    if request.method != 'GET':
        return JsonResponse({
            'error': 'Method not allowed'
        }, status=405)

    # ==================== 客户端IP获取 ====================

    # 获取客户端真实IP地址
    # 优先检查X-Forwarded-For头（处理代理和负载均衡器）
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        # X-Forwarded-For可能包含多个IP,取第一个（客户端真实IP）
        client_ip = x_forwarded_for.split(',')[0].strip()
    else:
        # 如果没有代理,直接使用REMOTE_ADDR
        client_ip = request.META.get('REMOTE_ADDR')

    # ==================== IP白名单验证 ====================

    # 获取系统配置
    config = SystemConfig.get_config()

    # 验证客户端IP是否在白名单中
    if not config.is_ip_allowed(client_ip):
        return HttpResponseForbidden(
            f'IP {client_ip} 不在白名单中,访问被拒绝'
        )

    # ==================== 脚本文件处理 ====================

    # 构建脚本文件的完整路径
    # 使用os.path.join确保跨平台兼容性
    script_path = os.path.join(settings.BASE_DIR, 'assets', 'agent.py')

    try:
        # 读取脚本文件内容
        with open(script_path, 'r', encoding='utf-8') as f:
            script_content = f.read()

        # 返回脚本内容,设置正确的Content-Type
        return HttpResponse(
            script_content,
            content_type='text/plain; charset=utf-8'
        )

    except FileNotFoundError:
        # 脚本文件不存在
        return HttpResponse(
            '脚本文件不存在',
            status=404
        )

    except Exception as e:
        # 其他读取错误
        return HttpResponse(
            f'读取脚本失败: {str(e)}',
            status=500
        )
