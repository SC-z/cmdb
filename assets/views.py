import ipaddress
import subprocess
from django.contrib import messages
from django.db.models import Count, Prefetch, Q
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from .forms import ExecutionTaskForm, AddServerForm, SystemSettingsForm, CredentialForm, ServerOOBForm
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
    Credential,
)
from .utils import deploy_agent_to_server, test_ssh_connection, update_server_cron


def server_list_view(request):
    """
    服务器列表页面视图

    显示所有已添加的服务器列表,支持搜索和状态过滤功能。
    这是CMDB系统的主页面,提供服务器概览和快速导航。

    功能特性：
    1. 显示所有服务器,按创建时间倒序排列
    2. 支持按序列号、主机名、管理IP进行模糊搜索
    3. 支持按服务器状态���行过滤
    4. 提供服务器详情和删除操作的链接

    Args:
        request: Django的HttpRequest对象,包含GET参数

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

    # 获取所有服务器,按创建时间倒序排列,并预加载硬件信息
    servers = Server.objects.select_related('hardware').order_by('-created_at')

    # ==================== 搜索过滤逻辑 ====================

    # 如果有搜索关键词,在多个字段中进行模糊匹配
    if search_query:
        # 使用Q对象实现OR查询,搜索序列号、主机名或管理IP
        from django.db.models import Q
        servers = servers.filter(
            Q(sn__icontains=search_query) |  # 序列号包含关键词
            Q(hostname__icontains=search_query) |  # 主机名包含关键词
            Q(management_ip__icontains=search_query) |  # 管理IP包含关键词
            Q(bmc_ip__icontains=search_query)  # BMC IP包���关键词
        )

    # 如果选择了状态过滤器,按状态过滤
    if status_filter:
        servers = servers.filter(status=status_filter)

    # ==================== 硬件信息整理 ====================

    server_list = []
    for server in servers:
        hardware = getattr(server, "hardware", None)
        cpu_info = hardware.cpu_info if hardware and isinstance(hardware.cpu_info, dict) else {}
        logical_cores = cpu_info.get("logical_cores")
        architecture = cpu_info.get("architecture")
        memory_total = hardware.memory_total_gb if hardware else None

        server.display_cpu_logical = logical_cores if logical_cores is not None else "--"
        server.display_cpu_arch = architecture or "--"
        server.display_memory_total = f"{memory_total} GB" if memory_total is not None else "--"

        server_list.append(server)

    # ==================== 上下文准备 ====================

    # 准备模板上下文变量
    context = {
        "servers": server_list,  # 过滤后的服务器列表
        "search_query": search_query,  # 搜索关键词（用于保持搜索框内容）
        "status_filter": status_filter,  # 状态过滤器（用于保持下拉框选择）
    }

    # 渲染模板并返回响应
    return render(request, "server_list.html", context)


def add_server_view(request):
    """
    添加服务器页面视图

    处理新服务器的添加流程,包括：
    1. 表单数据验证
    2. 凭据处理（支持选择凭据或手动输入）
    3. IP地址格式检查
    4. SSH连接测试
    5. 服务器记录创建
    6. Agent自动部署

    这是一个完整的表单处理流程,展示了Django视图的最佳实践。

    Args:
        request: Django的HttpRequest对象

    Returns:
        HttpResponse: GET请求返回添加表单页面,POST请求处理完成后重定向
    """
    if request.method == 'POST':
        form = AddServerForm(request.POST)
        if form.is_valid():
            management_ip = form.cleaned_data['management_ip']
            ssh_port = form.cleaned_data['ssh_port']
            
            # 处理凭据逻辑
            credential = form.cleaned_data.get('credential')
            if credential:
                ssh_username = credential.username
                ssh_password = credential.get_password()
            else:
                ssh_username = form.cleaned_data.get('ssh_username')
                ssh_password = form.cleaned_data.get('ssh_password')
            
            # SSH连接测试
            messages.info(request, f'正在测试SSH连接到 {management_ip}:{ssh_port}...')
            ssh_success, ssh_message = test_ssh_connection(
                management_ip, ssh_port, ssh_username, ssh_password
            )
            
            if not ssh_success:
                messages.error(request, f'SSH连接失败: {ssh_message},服务器未添加到数据库')
                return render(request, 'add_server.html', {'form': form})
            
            try:
                # 创建服务器对象
                server = Server.objects.create(
                    sn=f'TEMP-{management_ip}',
                    # hostname和bmc_ip将在Agent首次上报时更新
                    management_ip=management_ip,
                    ssh_username=ssh_username,
                    ssh_port=ssh_port,
                    status='unknown'
                )
                server.set_ssh_password(ssh_password)
                server.save()
                
                # Agent部署
                messages.info(request, f'SSH连接成功,正在部署Agent...')
                deploy_success, deploy_message = deploy_agent_to_server(server)
                
                if deploy_success:
                    messages.success(request, f'✓ 服务器 {management_ip} 添加成功,Agent部署成功！')
                else:
                    messages.warning(request, f'⚠ 服务器 {management_ip} ���添加,但Agent部署失败: {deploy_message}')
                
                return redirect('assets:server_list')
                
            except Exception as e:
                messages.error(request, f'创建服务器记录失败: {str(e)}')
                return render(request, 'add_server.html', {'form': form})
    else:
        form = AddServerForm()

    return render(request, 'add_server.html', {'form': form})


def server_detail_view(request, server_id):
    """
    服务器详情页面视图

    显示指定服务器的详细信息,包括：
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
    # 如果服务器不存在,会自动返回404错误页面
    server = get_object_or_404(Server, id=server_id)

    # 准备模板上下文
    context = {
        'server': server,  # 服务器对象,包含基本信息和关联的硬件信息
    }

    # 渲染详情页面
    return render(request, 'server_detail.html', context)


def delete_server_view(request, server_id):
    """
    删除服务器视图

    处理服务器删除操作,采用POST方法防止CSRF攻击。
    删除服务器时会同时删除相关的硬件信息记录（级联删除）。

    Args:
        request: Django的HttpRequest对象
        server_id: 要删除的服务器ID

    Returns:
        HttpResponseRedirect: 重定向到服务器列表页面

    安全考虑：
    - 只接受POST请求,防止意外删除
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


def bulk_server_action_view(request):
    """现役服务器批量操作。"""

    if request.method != 'POST':
        return redirect('assets:server_list')

    action = request.POST.get('action', '').strip()
    selected_ids = request.POST.getlist('selected')

    if not selected_ids:
        messages.warning(request, '请选择至少一台服务器后再执行操作')
        return redirect('assets:server_list')

    try:
        id_list = [int(pk) for pk in selected_ids]
    except ValueError:
        messages.error(request, '选择的服务器ID无效')
        return redirect('assets:server_list')

    if action == 'delete':
        if not request.user.has_perm('assets.delete_server'):
            messages.error(request, '没有执行批量删除的权限')
            return redirect('assets:server_list')

        queryset = Server.objects.filter(id__in=id_list)
        deleted_count = queryset.count()
        queryset.delete()
        messages.success(request, f'已删除 {deleted_count} 台服务器')
    else:
        messages.error(request, '未识别的批量操作类型')

    return redirect('assets:server_list')


def system_settings_view(request):
    """
    系统设置页面视图
    """
    config = SystemConfig.get_config()

    if request.method == 'POST':
        action = request.POST.get('action')

        if action == 'update_config':
            form = SystemSettingsForm(request.POST, instance=config)
            if form.is_valid():
                form.save()
                messages.success(request, '配置更新成功')
            else:
                 messages.error(request, '配置更新失败，请检查输入')
        
        elif action == 'update_all_cron':
            # 批量更新逻辑保持不变，但可以从config中获取最新的cron表达式
            success_count = 0
            fail_count = 0
            servers = Server.objects.filter(agent_deployed=True)

            for server in servers:
                try:
                    # 重新从数据库获取最新配置，确保使用刚保存的值
                    current_config = SystemConfig.get_config()
                    success = update_server_cron(server, current_config.cron_expression)
                    if success:
                        success_count += 1
                    else:
                        fail_count += 1
                except Exception:
                    fail_count += 1

            messages.success(
                request,
                f'定时任务更新完成：成功 {success_count} 台,失败 {fail_count} 台'
            )

        return redirect('assets:system_settings')

    else:
        form = SystemSettingsForm(instance=config)

    # 计算统计信息
    total_servers = Server.objects.count()
    deployed_servers = Server.objects.filter(agent_deployed=True).count()

    context = {
        'form': form, # 传递form而不是config对象，template需要调整
        'config': config, # 保留config以便template中其他部分使用（如updated_at）
        'total_servers': total_servers,
        'deployed_servers': deployed_servers,
    }

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
                messages.success(request, '周期任务已创建,可在任务列表中查看。')

            return redirect('assets:task_detail', task_id=task.id)
        else:
            messages.error(request, '表单验证失败,请检查输入信息。')
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
                messages.warning(request, '已存在执行中的任务,请稍后再试。')
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
    """删除远程执行任务,支持级联清理相关记录。"""

    task = get_object_or_404(ExecutionTask, id=task_id)

    if request.method == 'POST':
        task_name = task.name
        task.delete()
        messages.success(request, f'任务 {task_name} 已清理。')
        return redirect('assets:task_list')

    messages.error(request, '仅允许通过 POST 请求删除任务。')
    return redirect('assets:task_detail', task_id=task.id)


def credential_list_view(request):
    """凭据列表视图"""
    credentials = Credential.objects.all()
    context = {'credentials': credentials}
    return render(request, 'credential_list.html', context)


def credential_add_view(request):
    """添加凭据视图"""
    if request.method == 'POST':
        form = CredentialForm(request.POST)
        if form.is_valid():
            credential = form.save(commit=False)
            credential.set_password(form.cleaned_data['input_password'])
            credential.save()
            messages.success(request, '凭据已创建。')
            return redirect('assets:credential_list')
    else:
        form = CredentialForm()
    
    context = {'form': form, 'title': '添加凭据'}
    return render(request, 'credential_form.html', context)


def credential_edit_view(request, pk):
    """编辑凭据视图"""
    credential = get_object_or_404(Credential, pk=pk)
    
    if request.method == 'POST':
        form = CredentialForm(request.POST, instance=credential)
        if form.is_valid():
            cred = form.save(commit=False)
            password = form.cleaned_data.get('input_password')
            if password:
                cred.set_password(password)
            cred.save()
            messages.success(request, '凭据已更新。')
            return redirect('assets:credential_list')
    else:
        form = CredentialForm(instance=credential)
    
    context = {'form': form, 'title': '编辑凭据', 'credential': credential}
    return render(request, 'credential_form.html', context)


def credential_delete_view(request, pk):
    """删除凭据视图"""
    credential = get_object_or_404(Credential, pk=pk)
    
    if request.method == 'POST':
        title = credential.title
        credential.delete()
        messages.success(request, f'凭据 "{title}" 已删除。')
        return redirect('assets:credential_list')
    
    # 简单的确认页面或者直接通过POST删除，这里我们复用一个简单的确认模板
    context = {'object': credential, 'cancel_url': 'assets:credential_list'}
    return render(request, 'confirm_delete.html', context)


# ==================== 带外管理视图 ====================

def _execute_ipmi_command(server, command):
    """
    执行IPMI命令
    command: 'on', 'off', 'reset', 'status'
    """
    bmc_ip = server.bmc_ip
    username = server.oob_username
    password = server.get_oob_password()

    if not bmc_ip or not username or not password:
        return False, "缺少带外管理配置（IP、用户名或密码）"

    # 构建命令: ipmitool -I lanplus -H <ip> -U <user> -P <pass> power <command>
    cmd_args = [
        'ipmitool', 
        '-I', 'lanplus', 
        '-H', bmc_ip, 
        '-U', username, 
        '-P', password, 
        'power', command
    ]
    
    try:
        # 设置超时时间为10秒，避免长时间阻塞
        result = subprocess.run(cmd_args, capture_output=True, text=True, timeout=10)
        
        if result.returncode == 0:
            return True, result.stdout.strip()
        else:
            # 某些情况下错误信息在stdout中
            error_msg = result.stderr.strip() or result.stdout.strip()
            return False, f"执行失败: {error_msg}"
            
    except subprocess.TimeoutExpired:
        return False, "连接超时，请检查网络或BMC地址"
    except FileNotFoundError:
        return False, "未找到ipmitool命令，请联系管理员安装"
    except Exception as e:
        return False, str(e)

def server_edit_oob_view(request, server_id):
    """编辑服务器带外管理信息"""
    server = get_object_or_404(Server, id=server_id)
    
    if request.method == 'POST':
        form = ServerOOBForm(request.POST, instance=server)
        if form.is_valid():
            server = form.save(commit=False)
            
            credential = form.cleaned_data.get('credential')
            password_input = form.cleaned_data.get('oob_password_input')
            
            # 优先使用选择的凭据
            if credential:
                server.oob_username = credential.username
                server.set_oob_password(credential.get_password())
            # 其次使用手动输入的密码（如果不为空）
            elif password_input:
                server.set_oob_password(password_input)
            
            server.save()
            messages.success(request, '带外管理信息已更新')
            return redirect('assets:server_detail', server_id=server.id)
    else:
        form = ServerOOBForm(instance=server)
    
    context = {
        'form': form, 
        'server': server,
        'title': '配置带外管理信息'
    }
    # 复用通用表单模板或创建新的，这里我们将创建一个新的
    return render(request, 'server_oob_form.html', context)

def server_power_on_view(request, server_id):
    """远程开机"""
    if request.method != 'POST':
        return redirect('assets:server_list')
        
    server = get_object_or_404(Server, id=server_id)
    success, message = _execute_ipmi_command(server, 'on')
    
    if success:
        messages.success(request, f'服务器 {server.management_ip} 开机指令发送成功')
    else:
        messages.error(request, f'服务器 {server.management_ip} 开机失败: {message}')
        
    return redirect('assets:server_list')

def server_power_off_view(request, server_id):
    """远程关机"""
    if request.method != 'POST':
        return redirect('assets:server_list')
        
    server = get_object_or_404(Server, id=server_id)
    success, message = _execute_ipmi_command(server, 'off')
    
    if success:
        messages.success(request, f'服务器 {server.management_ip} 关机指令发送成功')
    else:
        messages.error(request, f'服务器 {server.management_ip} 关机失败: {message}')
        
    return redirect('assets:server_list')

def server_power_reset_view(request, server_id):
    """远程重启"""
    if request.method != 'POST':
        return redirect('assets:server_list')
        
    server = get_object_or_404(Server, id=server_id)
    success, message = _execute_ipmi_command(server, 'reset')
    
    if success:
        messages.success(request, f'服务器 {server.management_ip} 重启指令发送成功')
    else:
        messages.error(request, f'服务器 {server.management_ip} 重启失败: {message}')
        
    return redirect('assets:server_list')
