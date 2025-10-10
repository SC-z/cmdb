"""
CMDB API Views
"""
import json
import os
from datetime import datetime
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.http import JsonResponse, HttpResponse, HttpResponseForbidden
from django.views import View
from django.conf import settings
from .models import Server, HardwareInfo, SystemConfig


@csrf_exempt
def agent_report(request):
    """
    Agent上报接口
    POST /api/agent/report/
    """
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed', 'status': 'error'}, status=405)

    try:
        # 解析请求数据
        data = json.loads(request.body.decode('utf-8'))

        # 验证必填字段
        sn = data.get('sn')
        if not sn:
            return JsonResponse({'error': 'SN is required', 'status': 'error'}, status=400)

        management_ip = data.get('management_ip')
        if not management_ip:
            return JsonResponse({'error': 'management_ip is required', 'status': 'error'}, status=400)

        hostname = data.get('hostname', '')
        hardware_info = data.get('hardware_info', {})

        # 查找或创建服务器记录（优先使用IP查找，避免临时SN导致重复）
        is_new = False
        try:
            # 优先使用IP查找
            server = Server.objects.get(management_ip=management_ip)
            # 服务器已存在，更新所有信息（包括SN）
            server.sn = sn  # 更新真实SN（覆盖临时SN）
            server.hostname = hostname
            server.status = 'online'
            server.last_report_time = timezone.now()
            server.save()
        except Server.DoesNotExist:
            # 新服务器，创建记录
            server = Server.objects.create(
                sn=sn,
                hostname=hostname,
                management_ip=management_ip,
                status='online',
                last_report_time=timezone.now()
            )
            is_new = True

        # 更新或创建硬件信息（适配v2.0数据结构）
        if hardware_info:
            # 提取CPU信息
            cpu_info = hardware_info.get('cpu', {})

            # 提取内存信息
            memory_info = hardware_info.get('memory', {})
            memory_modules = memory_info.get('modules', [])
            memory_total_gb = memory_info.get('total_gb', 0)

            # 提取磁盘信息
            disks = hardware_info.get('disks', [])

            hw_data = {
                'server': server,
                'cpu_info': cpu_info,
                'memory_modules': memory_modules,
                'memory_total_gb': memory_total_gb,
                'disks': disks,
                'raw_data': data  # 保存完整的原始数据
            }

            HardwareInfo.objects.update_or_create(
                server=server,
                defaults=hw_data
            )

        return JsonResponse({
            'status': 'success',
            'is_new': is_new,
            'server_id': server.id,
            'message': '新服务器已注册' if is_new else '数据已更新'
        })

    except json.JSONDecodeError:
        return JsonResponse({'error': 'Invalid JSON', 'status': 'error'}, status=400)
    except Exception as e:
        return JsonResponse({'error': str(e), 'status': 'error'}, status=500)


def server_list(request):
    """
    获取服务器列表
    GET /api/servers/
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        servers = Server.objects.all().order_by('-created_at')

        results = []
        for server in servers:
            results.append({
                'id': server.id,
                'sn': server.sn,
                'hostname': server.hostname,
                'management_ip': server.management_ip,
                'status': server.status,
                'last_report_time': server.last_report_time.isoformat() if server.last_report_time else None,
                'agent_deployed': server.agent_deployed,
                'created_at': server.created_at.isoformat(),
            })

        return JsonResponse({
            'count': len(results),
            'results': results
        })

    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def server_detail(request, server_id):
    """
    获取服务器详情
    GET /api/servers/{server_id}/
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    try:
        server = Server.objects.get(id=server_id)

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

        # 添加硬件信息（v2.0数据结构）
        if hasattr(server, 'hardware'):
            hardware = server.hardware
            result['hardware'] = {
                'cpu_info': hardware.cpu_info,
                'memory_modules': hardware.memory_modules,
                'memory_total_gb': hardware.memory_total_gb,
                'disks': hardware.disks,
                'collected_at': hardware.collected_at.isoformat(),
                'raw_data': hardware.raw_data
            }

        return JsonResponse(result)

    except Server.DoesNotExist:
        return JsonResponse({'error': 'Server not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)


def agent_script(request):
    """
    提供agent脚本下载
    GET /api/agent/script/

    带IP白名单验证
    """
    if request.method != 'GET':
        return JsonResponse({'error': 'Method not allowed'}, status=405)

    # 获取客户端IP
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        client_ip = x_forwarded_for.split(',')[0].strip()
    else:
        client_ip = request.META.get('REMOTE_ADDR')

    # 白名单验证
    config = SystemConfig.get_config()
    if not config.is_ip_allowed(client_ip):
        return HttpResponseForbidden(f'IP {client_ip} 不在白名单中，访问被拒绝')

    # 返回脚本内容
    script_path = os.path.join(settings.BASE_DIR, 'assets', 'agent.py')
    try:
        with open(script_path, 'r', encoding='utf-8') as f:
            script_content = f.read()
        return HttpResponse(script_content, content_type='text/plain; charset=utf-8')
    except FileNotFoundError:
        return HttpResponse('脚本文件不存在', status=404)
    except Exception as e:
        return HttpResponse(f'读取脚本失败: {str(e)}', status=500)
