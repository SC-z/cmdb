import logging
import os
import sys
import threading

from django.apps import AppConfig
from django.core.management import call_command


logger = logging.getLogger(__name__)


class AssetsConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'assets'

    _startup_check_started = False

    def ready(self):
        super().ready()

        if not self._should_trigger_startup_check():
            return

        if AssetsConfig._startup_check_started:
            return

        AssetsConfig._startup_check_started = True

        threading.Thread(
            target=self._run_startup_status_check,
            name='cmdb-startup-status-check',
            daemon=True,
        ).start()

    def _should_trigger_startup_check(self):
        if os.environ.get('CMDB_SKIP_STARTUP_STATUS_CHECK') == '1':
            return False

        command = sys.argv[1] if len(sys.argv) > 1 else None

        skip_commands = {
            'migrate',
            'makemigrations',
            'collectstatic',
            'shell',
            'test',
            'check',
            'loaddata',
            'dumpdata',
            'createsuperuser',
            'check_servers',
            'cleanup_servers',
            'process_execution_tasks',
        }

        if command in skip_commands:
            return False

        if command == 'runserver' and os.environ.get('RUN_MAIN') != 'true':
            return False

        return True

    def _run_startup_status_check(self):
        try:
            call_command('check_servers')
        except Exception:  # pragma: no cover
            logger.exception('Failed to run startup server status check')
