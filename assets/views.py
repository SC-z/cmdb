import ipaddress
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib import messages
from .models import Server, HardwareInfo, SystemConfig
from .utils import deploy_agent_to_server, test_ssh_connection, update_server_cron


def server_list_view(request):
    """服务器列表页面"""
    search_query = request.GET.get('search', '')
    status_filter = request.GET.get('status', '')

    servers = Server.objects.all().order_by('-created_at')

    # 搜索过滤
    if search_query:
        servers = servers.filter(
            sn__icontains=search_query
        ) | servers.filter(
            hostname__icontains=search_query
        ) | servers.filter(
            management_ip__icontains=search_query
        )

    # 状态过滤
    if status_filter:
        servers = servers.filter(status=status_filter)

    context = {
        'servers': servers,
        'search_query': search_query,
        'status_filter': status_filter,
    }

    return render(request, 'server_list.html', context)


def add_server_view(request):
    """添加服务器页面"""
    if request.method == 'POST':
        management_ip = request.POST.get('management_ip', '').strip()
        ssh_username = request.POST.get('ssh_username', '').strip()
        ssh_password = request.POST.get('ssh_password', '')
        ssh_port = request.POST.get('ssh_port', '22').strip()
        hostname = request.POST.get('hostname', '').strip()

        # 1. 基本验证
        if not all([management_ip, ssh_username, ssh_password]):
            messages.error(request, '请填写所有必填字段（管理IP、SSH用户名、SSH密码）')
            return render(request, 'add_server.html')

        # 2. IP格式验证
        try:
            ipaddress.ip_address(management_ip)
        except ValueError:
            messages.error(request, f'IP地址格式错误: {management_ip}，请输入正确的IPv4或IPv6地址')
            return render(request, 'add_server.html')

        # 3. 端口号验证
        try:
            ssh_port_int = int(ssh_port)
            if not (1 <= ssh_port_int <= 65535):
                raise ValueError('端口号超出范围')
        except ValueError:
            messages.error(request, f'SSH端口号错误: {ssh_port}，请输入1-65535之间的数字')
            return render(request, 'add_server.html')

        # 4. 检查IP是否已存在
        if Server.objects.filter(management_ip=management_ip).exists():
            messages.error(request, f'IP地址 {management_ip} 已存在，请勿重复添加')
            return render(request, 'add_server.html')

        # 5. 测试SSH连接（先测试，再创建记录）
        messages.info(request, f'正在测试SSH连接到 {management_ip}:{ssh_port_int}...')
        ssh_success, ssh_message = test_ssh_connection(management_ip, ssh_port_int, ssh_username, ssh_password)

        if not ssh_success:
            messages.error(request, f'SSH连接失败: {ssh_message}，服务器未添加到数据库')
            return render(request, 'add_server.html')

        # 6. SSH测试成功，创建服务器记录
        try:
            server = Server.objects.create(
                sn=f'TEMP-{management_ip}',  # 临时SN，等Agent上报后更新
                hostname=hostname,
                management_ip=management_ip,
                ssh_username=ssh_username,
                ssh_port=ssh_port_int,
                status='unknown'
            )
            server.set_ssh_password(ssh_password)
            server.save()

            # 7. 自动部署Agent
            messages.info(request, f'SSH连接成功，正在部署Agent...')
            deploy_success, deploy_message = deploy_agent_to_server(server)

            if deploy_success:
                messages.success(request, f'✓ 服务器 {management_ip} 添加成功，Agent部署成功！')
            else:
                messages.warning(request, f'⚠ 服务器 {management_ip} 已添加，但Agent部署失败: {deploy_message}')

            return redirect('assets:server_list')

        except Exception as e:
            messages.error(request, f'创建服务器记录失败: {str(e)}')
            return render(request, 'add_server.html')

    return render(request, 'add_server.html')


def server_detail_view(request, server_id):
    """服务器详情页面"""
    server = get_object_or_404(Server, id=server_id)

    context = {
        'server': server,
    }

    return render(request, 'server_detail.html', context)


def delete_server_view(request, server_id):
    """删除服务器"""
    if request.method == 'POST':
        server = get_object_or_404(Server, id=server_id)
        server_sn = server.sn
        server.delete()
        messages.success(request, f'服务器 {server_sn} 已删除')

    return redirect('assets:server_list')


def system_settings_view(request):
    """系统设置页面"""
    config = SystemConfig.get_config()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_config':
            # 更新配置
            config.allowed_networks = request.POST.get('allowed_networks', '')
            config.cron_expression = request.POST.get('cron_expression', '0 * * * *')
            config.cron_description = request.POST.get('cron_description', '')
            config.save()
            messages.success(request, '配置更新成功')

        elif action == 'update_all_cron':
            # 批量更新所有主机的定时任务
            success_count = 0
            fail_count = 0

            servers = Server.objects.filter(agent_deployed=True)
            for server in servers:
                try:
                    success = update_server_cron(server, config.cron_expression)
                    if success:
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception as e:
                    fail_count += 1

            messages.success(request, f'定时任务更新完成：成功 {success_count} 台，失败 {fail_count} 台')

        return redirect('assets:system_settings')

    # 统计信息
    total_servers = Server.objects.count()
    deployed_servers = Server.objects.filter(agent_deployed=True).count()

    context = {
        'config': config,
        'total_servers': total_servers,
        'deployed_servers': deployed_servers,
    }
    return render(request, 'system_settings.html', context)
