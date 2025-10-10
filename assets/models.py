import base64
from django.db import models


class Server(models.Model):
    """服务器模型"""
    STATUS_CHOICES = [
        ('online', '在线'),
        ('offline', '离线'),
        ('unknown', '未知'),
    ]

    # 基本信息
    sn = models.CharField('序列号', max_length=100, db_index=True)
    hostname = models.CharField('主机名', max_length=100, blank=True)
    management_ip = models.GenericIPAddressField('管理IP', unique=True, db_index=True)  # 唯一约束，避免重复
    status = models.CharField('状态', max_length=20, choices=STATUS_CHOICES, default='unknown')

    # SSH信息
    ssh_username = models.CharField('SSH用户名', max_length=50, blank=True)
    ssh_password = models.CharField('SSH密码', max_length=200, blank=True)
    ssh_port = models.IntegerField('SSH端口', default=22)

    # Agent信息
    agent_deployed = models.BooleanField('Agent已部署', default=False)
    agent_version = models.CharField('Agent版本', max_length=20, blank=True)

    # 时间戳
    last_report_time = models.DateTimeField('最后上报时间', null=True, blank=True, db_index=True)
    created_at = models.DateTimeField('创建时间', auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '服务器'
        verbose_name_plural = '服务器'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.sn} - {self.hostname or 'Unknown'}"

    def set_ssh_password(self, password):
        """设置SSH密码（Base64编码）"""
        if password:
            self.ssh_password = base64.b64encode(password.encode()).decode()

    def get_ssh_password(self):
        """获取SSH密码（Base64解码）"""
        if self.ssh_password:
            try:
                return base64.b64decode(self.ssh_password.encode()).decode()
            except Exception:
                return ''
        return ''


class HardwareInfo(models.Model):
    """硬件信息模型 v2.0"""
    server = models.OneToOneField(
        Server,
        on_delete=models.CASCADE,
        related_name='hardware',
        verbose_name='服务器'
    )

    # CPU信息（JSON格式）
    # 结构: {model, architecture, physical_cores, logical_cores, sockets}
    cpu_info = models.JSONField('CPU信息', default=dict, blank=True)

    # 内存信息
    # memory_modules结构: [{slot, size, speed, sn, vendor}, ...]
    memory_modules = models.JSONField('内存条信息', default=list, blank=True)
    memory_total_gb = models.IntegerField('系统总内存(GB)', null=True, blank=True)

    # 磁盘信息（JSON格式）
    # 结构: [{device, type, size, serial, pcie_slot}, ...]
    disks = models.JSONField('磁盘信息', default=list, blank=True)

    # 原始数据备份
    raw_data = models.JSONField('原始数据', default=dict, blank=True)

    # 采集时间
    collected_at = models.DateTimeField('采集时间', auto_now=True)

    class Meta:
        verbose_name = '硬件信息'
        verbose_name_plural = '硬件信息'

    def __str__(self):
        return f"{self.server.sn} 的硬件信息"

    def get_cpu_model(self):
        """获取CPU型号"""
        return self.cpu_info.get('model', 'Unknown') if self.cpu_info else 'Unknown'

    def get_total_disk_size(self):
        """计算磁盘总容量"""
        if not self.disks:
            return 0
        # 简单累加（实际应该解析GB/TB单位）
        return len(self.disks)


class SystemConfig(models.Model):
    """系统配置模型（单例）"""

    # 白名单配置
    allowed_networks = models.TextField(
        '允许的IP/网段',
        default='10.0.0.0/8\n172.16.0.0/12\n192.168.0.0/16',
        help_text='每行一个IP地址或网段（CIDR格式），如：10.10.90.0/24'
    )

    # 定时任务配置
    cron_expression = models.CharField(
        'Cron表达式',
        max_length=100,
        default='0 * * * *',
        help_text='格式：分 时 日 月 周，如：0 * * * *（每小时）'
    )

    cron_description = models.CharField(
        '定时任务描述',
        max_length=200,
        default='每小时执行一次',
        blank=True
    )

    updated_at = models.DateTimeField('更新时间', auto_now=True)

    class Meta:
        verbose_name = '系统配置'
        verbose_name_plural = '系统配置'

    def __str__(self):
        return f"系统配置 - 更新于 {self.updated_at.strftime('%Y-%m-%d %H:%M:%S')}"

    @classmethod
    def get_config(cls):
        """获取配置（单例模式）"""
        config, created = cls.objects.get_or_create(pk=1)
        return config

    def is_ip_allowed(self, ip_address):
        """检查IP是否在白名单中"""
        import ipaddress
        try:
            ip = ipaddress.ip_address(ip_address)
            for line in self.allowed_networks.strip().split('\n'):
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                try:
                    network = ipaddress.ip_network(line, strict=False)
                    if ip in network:
                        return True
                except ValueError:
                    continue
            return False
        except ValueError:
            return False
