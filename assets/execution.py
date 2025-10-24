"""远程批量执行任务的调度与执行工具。"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional

from django.db import transaction
from django.utils import timezone

from .models import ExecutionJob, ExecutionRun, ExecutionStage, ExecutionTask, Server
from .utils import ssh_connection

logger = logging.getLogger(__name__)

try:  # pragma: no cover - 依赖可选
    from croniter import croniter  # type: ignore
except Exception:  # pragma: no cover - 安全回退
    croniter = None


@dataclass
class JobResult:
    server: Server
    exit_code: Optional[int]
    stdout: str
    stderr: str
    error: Optional[str]


def calculate_next_run(cron_expression: str, reference: Optional[timezone.datetime] = None) -> Optional[timezone.datetime]:
    """根据 Cron 表达式计算下一次执行时间。"""

    if not cron_expression:
        return None

    if croniter is None:
        logger.warning("croniter 未安装,无法计算下一次执行时间。")
        return None

    reference_time = reference or timezone.now()
    if timezone.is_naive(reference_time):
        reference_time = timezone.make_aware(reference_time, timezone.get_current_timezone())

    iterator = croniter(cron_expression, reference_time)
    next_timestamp = iterator.get_next()
    dt = datetime.fromtimestamp(next_timestamp, tz=timezone.utc)
    return dt.astimezone(timezone.get_current_timezone())


def _prepare_stage(run: ExecutionRun, servers: Iterable[Server]) -> ExecutionStage:
    stage = ExecutionStage.objects.create(run=run, name='远程执行', order=1)
    targets = list(servers)
    for server in targets:
        ExecutionJob.objects.create(stage=stage, server=server)
    return stage


def create_run_for_task(
    task: ExecutionTask,
    *,
    servers: Optional[Iterable[Server]] = None,
    scheduled_for: Optional[timezone.datetime] = None,
    triggered_by=None,
    manual: bool = False,
    status: Optional[str] = None,
) -> ExecutionRun:
    """为任务创建一次执行记录,并初始化阶段与作业。"""

    if servers is None:
        servers = [target.server for target in task.targets.select_related('server').order_by('order', 'id')]
    else:
        servers = list(servers)

    if not servers:
        raise ValueError('任务未配置目标服务器,无法创建执行。')

    if scheduled_for and timezone.is_naive(scheduled_for):
        scheduled_for = timezone.make_aware(scheduled_for, timezone.get_current_timezone())

    run_status = status or ('scheduled' if scheduled_for and scheduled_for > timezone.now() else 'queued')

    with transaction.atomic():
        run = ExecutionRun.objects.create(
            task=task,
            status=run_status,
            scheduled_for=scheduled_for,
            triggered_by=triggered_by if getattr(triggered_by, 'is_authenticated', False) else None,
            is_manual=manual,
        )
        _prepare_stage(run, servers)

    return run


def _update_task_schedule(task: ExecutionTask):
    if task.is_periodic and task.cron_expression:
        next_time = calculate_next_run(task.cron_expression, reference=timezone.now())
        if next_time:
            task.next_run_at = next_time
            task.save(update_fields=['next_run_at'])


def _execute_job(job: ExecutionJob, command: str) -> JobResult:
    server = job.server

    try:
        with ssh_connection(server) as ssh:
            stdin, stdout, stderr = ssh.exec_command(command)
            stdout_content = stdout.read().decode('utf-8', errors='ignore')
            stderr_content = stderr.read().decode('utf-8', errors='ignore')
            exit_code = stdout.channel.recv_exit_status()
            return JobResult(server, exit_code, stdout_content, stderr_content, None)
    except Exception as exc:  # pragma: no cover - 网络异常难以在测试中复现
        logger.exception('执行远程命令失败: %s', exc)
        return JobResult(server, None, '', '', str(exc))


def _execute_run(run_id: int):
    run = ExecutionRun.objects.select_related('task').get(id=run_id)
    if run.status in {'running', 'success', 'failed', 'cancelled'}:
        return

    run.status = 'running'
    run.started_at = timezone.now()
    run.save(update_fields=['status', 'started_at'])

    stage = run.stages.select_related('run').first()
    if not stage:
        stage = ExecutionStage.objects.create(run=run, name='远程执行', order=1)

    stage.status = 'running'
    stage.started_at = timezone.now()
    stage.save(update_fields=['status', 'started_at'])

    all_success = True

    for job in stage.jobs.select_related('server').order_by('server__management_ip'):
        job.status = 'running'
        job.started_at = timezone.now()
        job.save(update_fields=['status', 'started_at'])

        result = _execute_job(job, run.task.command)

        job.exit_code = result.exit_code
        job.stdout = result.stdout
        job.stderr = result.stderr
        job.error_message = result.error or ''
        job.finished_at = timezone.now()

        if result.error or (result.exit_code is not None and result.exit_code != 0):
            job.status = 'failed'
            job.save(update_fields=['exit_code', 'stdout', 'stderr', 'error_message', 'finished_at', 'status'])
            all_success = False
        else:
            job.status = 'success'
            job.save(update_fields=['exit_code', 'stdout', 'stderr', 'error_message', 'finished_at', 'status'])

    stage.status = 'success' if all_success else 'failed'
    stage.finished_at = timezone.now()
    stage.save(update_fields=['status', 'finished_at'])

    run.status = 'success' if all_success else 'failed'
    run.finished_at = timezone.now()
    run.save(update_fields=['status', 'finished_at'])

    run.task.mark_last_run(run.finished_at)

    if run.task.is_periodic:
        _update_task_schedule(run.task)


def start_run_async(run: ExecutionRun):
    """后台线程执行 run。"""

    if run.status == 'scheduled':
        run.status = 'queued'
        run.save(update_fields=['status'])

    thread = threading.Thread(target=_execute_run, args=(run.id,), daemon=True)
    thread.start()


def has_active_run(task: ExecutionTask) -> bool:
    return task.runs.filter(status__in=['queued', 'running']).exists()


def get_task_servers(task: ExecutionTask) -> list[Server]:
    return [target.server for target in task.targets.select_related('server').order_by('order', 'id')]
