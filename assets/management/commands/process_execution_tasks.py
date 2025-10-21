from django.core.management.base import BaseCommand
from django.utils import timezone

from ...execution import (
    calculate_next_run,
    create_run_for_task,
    has_active_run,
    start_run_async,
)
from ...models import ExecutionRun, ExecutionTask


class Command(BaseCommand):
    help = '处理计划执行的远程批量任务，并调度周期任务。'

    def handle(self, *args, **options):
        now = timezone.now()
        self._dispatch_scheduled_runs(now)
        self._dispatch_cron_tasks(now)

    def _dispatch_scheduled_runs(self, now):
        runs = ExecutionRun.objects.filter(status='scheduled', scheduled_for__lte=now)
        for run in runs:
            self.stdout.write(self.style.NOTICE(f'启动计划任务: {run.id} ({run.task.name})'))
            run.status = 'queued'
            run.save(update_fields=['status'])
            start_run_async(run)

    def _dispatch_cron_tasks(self, now):
        tasks = ExecutionTask.objects.filter(task_type='cron', is_enabled=True)
        for task in tasks:
            if has_active_run(task):
                continue

            if not task.next_run_at:
                next_time = calculate_next_run(task.cron_expression, reference=now)
                if next_time:
                    task.next_run_at = next_time
                    task.save(update_fields=['next_run_at'])
                continue

            if task.next_run_at > now:
                continue

            try:
                run = create_run_for_task(task, manual=False)
            except ValueError as exc:
                self.stderr.write(str(exc))
                continue

            self.stdout.write(self.style.WARNING(f'触发周期任务: {task.name} (run={run.id})'))
            start_run_async(run)

            next_time = calculate_next_run(task.cron_expression, reference=task.next_run_at or now)
            if next_time:
                task.next_run_at = next_time
                task.save(update_fields=['next_run_at'])
