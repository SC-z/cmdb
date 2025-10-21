import ipaddress
from django.contrib import messages
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import ExecutionTaskForm
from .execution import (
    calculate_next_run,
    create_run_for_task,
    get_task_servers,
    has_active_run,
    start_run_async,
)
from .models import (
    ExecutionStage,
    ExecutionRun,
    ExecutionTask,
    HardwareInfo,
    Server,
    SystemConfig,
)
from .utils import deploy_agent_to_server, test_ssh_connection, update_server_cron


def server_list_view(request):
    """
    服务器列表页面视图

    显示所有已添加的服务器列表，支持搜索和状态过滤功能。
    这是CMDB系统的主页面，提供服务器概览和快速导航。

    功能特性：
    1. 显示所有服务器，按创建时间倒序排列
    2. 支持按序列号、主机名、管理IP进行模糊搜索
    3. 支持按服务器状态进行过滤
    4. 提供服务器详情和删除操作的链接

    Args:
        request: Django的HttpRequest对象，包含GET参数

    Returns:
        HttpResponse: 渲染后的服务器列表页面

    模板: server_list.html
    上下文变量:
        - servers: 过滤后的服务器查询集
        - search_query: 当前搜索关键词
        - status_filter: 当前状态过滤器
    """
    # 获取GET参数
    search_query = request.GET.get('search', '').strip()  # 搜索关键词
    status_filter = request.GET.get('status', '').strip() # 状态过滤器

    # 获取所有服务器，按创建时间倒序排列
    servers = Server.objects.all().order_by('-created_at')

    # ==================== 搜索过滤逻辑 ====================

    # 如果有搜索关键词，在多个字段中进行模糊匹配
    if search_query:
        # 使用Q对象实现OR查询，搜索序列号、主机名或管理IP
        from django.db.models import Q
        servers = servers.filter(
            Q(sn__icontains=search_query) |  # 序列号包含关键词
            Q(hostname__icontains=search_query) |  # 主机名包含关键词
            Q(management_ip__icontains=search_query)  # 管理IP包含关键词
        )

    # 如果选择了状态过滤器，按状态过滤
    if status_filter:
        servers = servers.filter(status=status_filter)

    # ==================== 上下文准备 ====================

    # 准备模板上下文变量
    context = {
        'servers': servers,  # 过滤后的服务器列表
        'search_query': search_query,  # 搜索关键词（用于保持搜索框内容）
        'status_filter': status_filter,  # 状态过滤器（用于保持下拉框选择）
    }

    # 渲染模板并返回响应
    return render(request, 'server_list.html', context)


def add_server_view(request):
    """
    添加服务器页面视图

    处理新服务器的添加流程，包括：
    1. 表单数据验证
    2. IP地址格式检查
    3. SSH连接测试
    4. 服务器记录创建
    5. Agent自动部署

    这是一个完整的表单处理流程，展示了Django视图的最佳实践。

    Args:
        request: Django的HttpRequest对象

    Returns:
        HttpResponse: GET请求返回添加表单页面，POST请求处理完成后重定向

    模板: add_server.html

    表单字段:
        - management_ip: 管理IP地址（必填）
        - ssh_username: SSH用户名（必填）
        - ssh_password: SSH密码（必填）
        - ssh_port: SSH端口（可选，默认22）
        - hostname: 主机名（可选）
    """
    # ==================== POST请求处理 ====================

    if request.method == 'POST':
        # 获取并清理表单数据
        management_ip = request.POST.get('management_ip', '').strip()
        ssh_username = request.POST.get('ssh_username', '').strip()
        ssh_password = request.POST.get('ssh_password', '').strip()
        ssh_port = request.POST.get('ssh_port', '22').strip()
        hostname = request.POST.get('hostname', '').strip()

        # ==================== 数据验证阶段 ====================

        # 1. 必填字段验证
        # 确保关键信息都已填写，这是创建服务器的最低要求
        if not all([management_ip, ssh_username, ssh_password]):
            messages.error(
                request,
                '请填写所有必填字段（管理IP、SSH用户名、SSH密码）'
            )
            return render(request, 'add_server.html')

        # 2. IP地址格式验证
        # 使用Python标准库验证IP地址格式的有效性
        try:
            ipaddress.ip_address(management_ip)
        except ValueError:
            messages.error(
                request,
                f'IP地址格式错误: {management_ip}，请输入正确的IPv4或IPv6地址'
            )
            return render(request, 'add_server.html')

        # 3. SSH端口号验证
        # 确保端口号在有效范围内（1-65535）
        try:
            ssh_port_int = int(ssh_port)
            if not (1 <= ssh_port_int <= 65535):
                raise ValueError('端口号超出范围')
        except ValueError:
            messages.error(
                request,
                f'SSH端口号错误: {ssh_port}，请输入1-65535之间的数字'
            )
            return render(request, 'add_server.html')

        # 4. IP地址唯一性检查
        # 防止重复添加同一台服务器
        if Server.objects.filter(management_ip=management_ip).exists():
            messages.error(
                request,
                f'IP地址 {management_ip} 已存在，请勿重复添加'
            )
            return render(request, 'add_server.html')

        # ==================== SSH连接测试阶段 ====================

        # 5. 在创建数据库记录之前先测试SSH连接
        # 这样可以避免因为连接问题导致数据库中产生无效记录
        messages.info(
            request,
            f'正在测试SSH连接到 {management_ip}:{ssh_port_int}...'
        )

        ssh_success, ssh_message = test_ssh_connection(
            management_ip,
            ssh_port_int,
            ssh_username,
            ssh_password
        )

        # 如果SSH连接失败，显示错误信息但不创建记录
        if not ssh_success:
            messages.error(
                request,
                f'SSH连接失败: {ssh_message}，服务器未添加到数据库'
            )
            return render(request, 'add_server.html')

        # ==================== 数据库记录创建阶段 ====================

        # 6. SSH测试成功，创建服务器记录
        try:
            # 创建服务器对象
            server = Server.objects.create(
                sn=f'TEMP-{management_ip}',  # 临时序列号，等待Agent上报真实SN
                hostname=hostname,
                management_ip=management_ip,
                ssh_username=ssh_username,
                ssh_port=ssh_port_int,
                status='unknown'  # 初始状态为未知
            )

            # 设置SSH密码（Base64编码存储）
            server.set_ssh_password(ssh_password)
            server.save()

            # ==================== Agent部署阶段 ====================

            # 7. 自动部署数据采集Agent
            messages.info(
                request,
                f'SSH连接成功，正在部署Agent...'
            )

            deploy_success, deploy_message = deploy_agent_to_server(server)

            # 根据部署结果显示不同的提示信息
            if deploy_success:
                messages.success(
                    request,
                    f'✓ 服务器 {management_ip} 添加成功，Agent部署成功！'
                )
            else:
                messages.warning(
                    request,
                    f'⚠ 服务器 {management_ip} 已添加，但Agent部署失败: {deploy_message}'
                )

            # 操作完成，重定向到服务器列表页面
            return redirect('assets:server_list')

        except Exception as e:
            # 数据库操作异常处理
            messages.error(
                request,
                f'创建服务器记录失败: {str(e)}'
            )
            return render(request, 'add_server.html')

    # ==================== GET请求处理 ====================

    # 如果是GET请求，直接显示添加服务器表单页面
    return render(request, 'add_server.html')


def server_detail_view(request, server_id):
    """
    服务器详情页面视图

    显示指定服务器的详细信息，包括：
    1. 服务器基本信息
    2. 硬件配置信息
    3. Agent部署状态
    4. 最后上报时间

    Args:
        request: Django的HttpRequest对象
        server_id: 服务器的数据库主键ID

    Returns:
        HttpResponse: 渲染后的服务器详情页面

    模板: server_detail.html
    上下文变量:
        - server: 服务器对象实例
    """
    # 使用get_object_or_404获取服务器对象
    # 如果服务器不存在，会自动返回404错误页面
    server = get_object_or_404(Server, id=server_id)

    # 准备模板上下文
    context = {
        'server': server,  # 服务器对象，包含基本信息和关联的硬件信息
    }

    # 渲染详情页面
    return render(request, 'server_detail.html', context)


def delete_server_view(request, server_id):
    """
    删除服务器视图

    处理服务器删除操作，采用POST方法防止CSRF攻击。
    删除服务器时会同时删除相关的硬件信息记录（级联删除）。

    Args:
        request: Django的HttpRequest对象
        server_id: 要删除的服务器ID

    Returns:
        HttpResponseRedirect: 重定向到服务器列表页面

    安全考虑：
    - 只接受POST请求，防止意外删除
    - 使用事务确保数据一致性
    - 级联删除相关的硬件信息
    """
    # 确保只有POST请求才能执行删除操作
    if request.method == 'POST':
        # 获取要删除的服务器对象
        server = get_object_or_404(Server, id=server_id)
        server_sn = server.sn  # 保存序列号用于显示消息

        # 执行删除操作（会自动级联删除相关的硬件信息）
        server.delete()

        # 添加成功消息
        messages.success(request, f'服务器 {server_sn} 已删除')

    # 重定向到服务器列表页面
    return redirect('assets:server_list')


def system_settings_view(request):
    """
    系统设置页面视图

    管理CMDB系统的全局配置，包括：
    1. IP白名单配置（控制Agent脚本访问权限）
    2. 定时任务Cron表达式配置
    3. 批量更新服务器定时任务
    4. 系统统计信息展示

    展示了Django视图如何处理复杂的表单操作和系统管理功能。

    Args:
        request: Django的HttpRequest对象

    Returns:
        HttpResponse: 渲染后的系统设置页面

    模板: system_settings.html
    上下文变量:
        - config: 系统配置对象
        - total_servers: 服务器总数
        - deployed_servers: 已部署Agent的服务器数量
    """
    # 获取系统配置（使用单例模式）
    config = SystemConfig.get_config()

    # ==================== POST请求处理 ====================

    if request.method == 'POST':
        # 获取操作类型标识
        action = request.POST.get('action')

        if action == 'update_config':
            # ==================== 配置更新操作 ====================

            # 更新IP白名单配置
            config.allowed_networks = request.POST.get('allowed_networks', '')

            # 更新Cron表达式
            config.cron_expression = request.POST.get('cron_expression', '0 * * * *')

            # 更新定时任务描述
            config.cron_description = request.POST.get('cron_description', '')

            # 保存配置到数据库
            config.save()

            # 添加成功提示消息
            messages.success(request, '配置更新成功')

        elif action == 'update_all_cron':
            # ==================== 批量更新定时任务操作 ====================

            # 初始化计数器
            success_count = 0  # 成功更新的服务器数量
            fail_count = 0     # 更新失败的服务器数量

            # 获取所有已部署Agent的服务器
            servers = Server.objects.filter(agent_deployed=True)

            # 逐个更新服务器的定时任务
            for server in servers:
                try:
                    # 调用工具函数更新单个服务器的Cron任务
                    success = update_server_cron(server, config.cron_expression)

                    if success:
                        success_count += 1
                    else:
                        fail_count += 1

                except Exception as e:
                    # 异常处理，记录失败数量
                    fail_count += 1

            # 显示批量更新结果
            messages.success(
                request,
                f'定时任务更新完成：成功 {success_count} 台，失败 {fail_count} 台'
            )

        # 操作完成后重定向，防止表单重复提交
        return redirect('assets:system_settings')

    # ==================== GET请求处理 ====================

    # 计算系统统计信息
    total_servers = Server.objects.count()  # 服务器总数
    deployed_servers = Server.objects.filter(agent_deployed=True).count()  # 已部署Agent的服务器数

    # 准备模板上下文
    context = {
        'config': config,  # 系统配置对象
        'total_servers': total_servers,  # 服务器总数
        'deployed_servers': deployed_servers,  # 已部署Agent的服务器数
    }

    # 渲染系统设置页面
    return render(request, 'system_settings.html', context)


def task_list_view(request):
    """远程执行任务总览页面。"""

    tasks = ExecutionTask.objects.all()

    status_filter = request.GET.get('status', '').strip()
    task_type_filter = request.GET.get('type', '').strip()
    owner_filter = request.GET.get('owner', '').strip()

    if task_type_filter:
        tasks = tasks.filter(task_type=task_type_filter)

    if status_filter:
        tasks = tasks.filter(runs__status=status_filter)

    if owner_filter:
        tasks = tasks.filter(created_by__username__icontains=owner_filter)

    if status_filter or owner_filter:
        tasks = tasks.distinct()

    tasks = tasks.prefetch_related(
        'targets__server',
        Prefetch('runs', queryset=ExecutionRun.objects.select_related('triggered_by').order_by('-created_at')),
    ).annotate(target_count=Count('targets', distinct=True))

    task_items = []
    for task in tasks:
        run_list = list(task.runs.all())
        latest_run = run_list[0] if run_list else None
        upcoming_run = next((run for run in run_list if run.status in ('scheduled', 'queued')), None)
        task_items.append({
            'task': task,
            'latest_run': latest_run,
            'upcoming_run': upcoming_run,
            'target_count': task.target_count,
        })

    context = {
        'task_items': task_items,
        'status_filter': status_filter,
        'task_type_filter': task_type_filter,
        'owner_filter': owner_filter,
        'status_choices': ExecutionRun.STATUS_CHOICES,
        'task_type_choices': ExecutionTask.TASK_TYPE_CHOICES,
    }

    return render(request, 'task_list.html', context)


def task_create_view(request):
    """创建远程执行任务。"""

    if request.method == 'POST':
        form = ExecutionTaskForm(request.POST)
        if form.is_valid():
            task = form.save(commit=False)
            if request.user.is_authenticated:
                task.created_by = request.user
            if task.is_periodic and task.cron_expression:
                task.next_run_at = calculate_next_run(task.cron_expression)
            task.save()

            servers = list(form.cleaned_data['servers'])
            for index, server in enumerate(servers):
                task.targets.create(server=server, order=index)

            # 需要立即执行的任务
            if task.task_type == 'one_off' and form.should_start_immediately:
                try:
                    run = create_run_for_task(task, triggered_by=request.user, manual=True)
                except ValueError as exc:
                    messages.error(request, str(exc))
                else:
                    start_run_async(run)
                    messages.success(request, '任务已创建并开始执行。')
            elif task.task_type == 'one_off' and form.scheduled_datetime:
                try:
                    run = create_run_for_task(
                        task,
                        scheduled_for=form.scheduled_datetime,
                        triggered_by=request.user,
                        manual=True,
                    )
                except ValueError as exc:
                    messages.error(request, str(exc))
                else:
                    task.next_run_at = form.scheduled_datetime
                    task.save(update_fields=['next_run_at'])
                    messages.success(request, '任务已创建并安排在指定时间执行。')
            else:
                run_now = request.POST.get('run_now') == 'on'
                if run_now:
                    try:
                        run = create_run_for_task(task, triggered_by=request.user, manual=True)
                    except ValueError as exc:
                        messages.error(request, str(exc))
                    else:
                        start_run_async(run)
                messages.success(request, '周期任务已创建，可在任务列表中查看。')

            return redirect('assets:task_detail', task_id=task.id)
        else:
            messages.error(request, '表单验证失败，请检查输入信息。')
    else:
        form = ExecutionTaskForm()

    context = {
        'form': form,
        'server_count': Server.objects.count(),
    }
    return render(request, 'task_create.html', context)


def task_detail_view(request, task_id):
    """任务详情与执行历史页面。"""

    task = get_object_or_404(
        ExecutionTask.objects.prefetch_related(
            'targets__server',
            Prefetch(
                'runs',
                queryset=ExecutionRun.objects.select_related('triggered_by').prefetch_related(
                    Prefetch('stages', queryset=ExecutionStage.objects.prefetch_related('jobs__server').order_by('order'))
                ).order_by('-created_at')
            ),
        ),
        id=task_id,
    )

    runs = list(task.runs.all())
    selected_run = None
    selected_run_id = request.GET.get('run')
    if selected_run_id:
        selected_run = next((run for run in runs if str(run.id) == selected_run_id), None)
    if not selected_run and runs:
        selected_run = runs[0]

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'trigger':
            if has_active_run(task):
                messages.warning(request, '已存在执行中的任务，请稍后再试。')
            else:
                try:
                    run = create_run_for_task(task, triggered_by=request.user, manual=True)
                except ValueError as exc:
                    messages.error(request, str(exc))
                else:
                    start_run_async(run)
                    messages.success(request, '已触发新的执行。')
            return redirect('assets:task_detail', task_id=task.id)

        if action == 'toggle':
            task.is_enabled = not task.is_enabled
            task.save(update_fields=['is_enabled'])
            status_label = '启用' if task.is_enabled else '停用'
            messages.success(request, f'任务已{status_label}。')
            return redirect('assets:task_detail', task_id=task.id)

        if action == 'retry_failed':
            run_id = request.POST.get('run_id')
            run = get_object_or_404(ExecutionRun, id=run_id, task=task)
            failed_servers = []
            for stage in run.stages.prefetch_related('jobs__server'):
                for job in stage.jobs.all():
                    if job.status == 'failed':
                        failed_servers.append(job.server)

            if not failed_servers:
                messages.info(request, '没有失败的节点需要重试。')
            else:
                try:
                    new_run = create_run_for_task(task, servers=failed_servers, triggered_by=request.user, manual=True)
                except ValueError as exc:
                    messages.error(request, str(exc))
                else:
                    start_run_async(new_run)
                    messages.success(request, f'已为 {len(failed_servers)} 台服务器重新触发执行。')
            return redirect('assets:task_detail', task_id=task.id)

        if action == 'cancel_run':
            run_id = request.POST.get('run_id')
            run = get_object_or_404(ExecutionRun, id=run_id, task=task)
            if run.status in ['queued', 'scheduled']:
                run.status = 'cancelled'
                run.finished_at = timezone.now()
                run.save(update_fields=['status', 'finished_at'])
                messages.success(request, '任务已取消。')
            else:
                messages.warning(request, '仅能取消排队或计划中的任务。')
            return redirect('assets:task_detail', task_id=task.id)

    context = {
        'task': task,
        'runs': runs,
        'selected_run': selected_run,
        'task_servers': get_task_servers(task),
    }
    return render(request, 'task_detail.html', context)


def task_delete_view(request, task_id):
    """删除远程执行任务，支持级联清理相关记录。"""

    task = get_object_or_404(ExecutionTask, id=task_id)

    if request.method == 'POST':
        task_name = task.name
        task.delete()
        messages.success(request, f'任务 {task_name} 已清理。')
        return redirect('assets:task_list')

    messages.error(request, '仅允许通过 POST 请求删除任务。')
    return redirect('assets:task_detail', task_id=task.id)
