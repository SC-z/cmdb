"""
服务器状态检查命令
"""
import subprocess
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from assets.models import Server


class Command(BaseCommand):
    help = '检查服务器在线状态'

    def add_arguments(self, parser):
        parser.add_argument(
            '--timeout',
            type=int,
            default=5,
            help='Ping超时时间（秒）'
        )

    def handle(self, *args, **options):
        timeout = options['timeout']

        self.stdout.write(self.style.SUCCESS('开始检查服务器状态...'))

        servers = Server.objects.all()
        online_count = 0
        offline_count = 0

        for server in servers:
            old_status = server.status

            # 检查Ping状态
            ping_ok = self.check_ping(server.management_ip, timeout)

            # 检查Agent心跳
            now = timezone.now()
            if server.last_report_time:
                time_diff = now - server.last_report_time
                agent_ok = time_diff < timedelta(minutes=30)
            else:
                agent_ok = False

            # 确定状态
            if ping_ok and agent_ok:
                new_status = 'online'
                online_count += 1
            elif server.last_report_time is None:
                new_status = 'unknown'
            else:
                new_status = 'offline'
                offline_count += 1

            # 更新状态
            if old_status != new_status:
                server.status = new_status
                server.save()
                self.stdout.write(
                    f'[UPDATE] {server.sn}: {old_status} -> {new_status}'
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS(f'[OK] {server.sn}: {new_status}')
                )

        self.stdout.write(
            self.style.SUCCESS(
                f'\n检查完成：在线 {online_count} 台,离线 {offline_count} 台'
            )
        )

    def check_ping(self, ip, timeout):
        """
        Ping检测

        Args:
            ip: IP地址
            timeout: 超时时间

        Returns:
            bool: True表示Ping通
        """
        try:
            result = subprocess.run(
                ['ping', '-c', '1', '-W', str(timeout), ip],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                timeout=timeout + 1
            )
            return result.returncode == 0
        except Exception:
            return False
