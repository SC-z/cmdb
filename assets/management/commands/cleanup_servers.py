"""
自动清理过期服务器命令
"""
from datetime import timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from assets.models import Server


class Command(BaseCommand):
    help = '清理长时间未上报的服务器'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days',
            type=int,
            default=14,
            help='清理N天未上报的服务器（默认14天）'
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='预览模式,不实际删除'
        )
        parser.add_argument(
            '--force',
            action='store_true',
            help='强制删除,不需要确认'
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        force = options['force']

        self.stdout.write(self.style.WARNING(f'开始扫描{days}天未上报的服务器...'))

        # 计算截止时间
        cutoff_time = timezone.now() - timedelta(days=days)

        # 查找符合条件的服务器
        # 条件1: 有上报记录,但超过N天
        condition1 = Server.objects.filter(
            last_report_time__lt=cutoff_time
        )

        # 条件2: 从未上报,且创建超过N天
        condition2 = Server.objects.filter(
            last_report_time__isnull=True,
            created_at__lt=cutoff_time
        )

        # 合并查询
        servers_to_delete = condition1 | condition2

        count = servers_to_delete.count()

        if count == 0:
            self.stdout.write(self.style.SUCCESS('没有需要清理的服务器'))
            return

        # 显示清理列表
        self.stdout.write(self.style.WARNING(f'\n找到 {count} 台服务器需要清理：\n'))

        for server in servers_to_delete:
            last_report = server.last_report_time.strftime('%Y-%m-% d %H:%M:%S') if server.last_report_time else '从未上报'
            self.stdout.write(
                f'  - SN: {server.sn:30s} | IP: {server.management_ip or "N/A":15s} | 最后上报: {last_report}'
            )

        # 预览模式
        if dry_run:
            self.stdout.write(self.style.SUCCESS('\n[预览模式] 未执行实际删除操作'))
            return

        # 确认删除
        if not force:
            confirm = input(f'\n确定要删除这 {count} 台服务器吗？(yes/no): ')
            if confirm.lower() != 'yes':
                self.stdout.write(self.style.WARNING('操作已取消'))
                return

        # 执行删除
        self.stdout.write(self.style.WARNING('\n开始删除...'))

        success_count = 0
        for server in servers_to_delete:
            try:
                sn = server.sn
                server.delete()  # 会级联删除HardwareInfo
                self.stdout.write(self.style.SUCCESS(f'[已删除] {sn}'))
                success_count += 1
            except Exception as e:
                self.stdout.write(self.style.ERROR(f'[删除失败] {server.sn}: {str(e)}'))

        self.stdout.write(
            self.style.SUCCESS(f'\n清理完成：成功删除 {success_count}/{count} 台服务器')
        )
