import base64
from django.db import models


class Server(models.Model):
    """
    服务器模型

    这是CMDB系统的核心模型，用于存储服务器的基本信息和连接配置。
    每台服务器都对应这个模型的一条记录，包括硬件标识、网络配置、
    SSH连接信息以及Agent部署状态等。
    """
    # 服务器状态选择项
    # Django的choices字段会在管理后台生成下拉选择框
    STATUS_CHOICES = [
        ('online', '在线'),   # 服务器正常在线，Agent能够正常上报数据
        ('offline', '离线'),  # 服务器离线或Agent停止上报
        ('unknown', '未知'),  # 初始状态或无法确定状态
    ]

    # ==================== 基本信息字段 ====================

    # 服务器序列号 (Service Number/Serial Number)
    # 唯一标识服务器的硬件序列号，通常来自服务器制造商
    sn = models.CharField('序列号', max_length=100, db_index=True)

    # 主机名 (Hostname)
    # 服务器的操作系统主机名，可以为空
    hostname = models.CharField('主机名', max_length=100, blank=True)

    # 管理IP地址
    # 用于远程管理和服务器的IP地址，设置unique=True确保唯一性
    # GenericIPAddressField支持IPv4和IPv6格式
    management_ip = models.GenericIPAddressField(
        '管理IP',
        unique=True,  # 唯一约束，避免重复IP
        db_index=True  # 添加数据库索引，提高查询性能
    )

    # 服务器当前状态
    # 使用choices字段限制可选值，默认为'unknown'
    status = models.CharField(
        '状态',
        max_length=20,
        choices=STATUS_CHOICES,
        default='unknown'
    )

    # ==================== SSH连接信息字段 ====================

    # SSH登录用户名
    # 用于远程连接服务器的用户名，通常为root或普通用户
    ssh_username = models.CharField('SSH用户名', max_length=50, blank=True)

    # SSH登录密码
    # 存储Base64编码的密码，提高安全性（虽然不是最佳实践）
    ssh_password = models.CharField('SSH密码', max_length=200, blank=True)

    # SSH连接端口
    # SSH服务监听的端口，默认为22
    ssh_port = models.IntegerField('SSH端口', default=22)

    # ==================== Agent部署信息字段 ====================

    # Agent部署状态标记
    # 标记是否已成功在该服务器上部署数据采集Agent
    agent_deployed = models.BooleanField('Agent已部署', default=False)

    # Agent版本信息
    # 记录当前部署的Agent版本号，用于版本管理和升级
    agent_version = models.CharField('Agent版本', max_length=20, blank=True)

    # ==================== 时间戳字段 ====================

    # 最后数据上报时间
    # Agent最后一次成功上报硬件信息的时间，用于监控Agent活跃度
    last_report_time = models.DateTimeField(
        '最后上报时间',
        null=True,
        blank=True,
        db_index=True  # 添加索引，便于查询超时服务器
    )

    # 记录创建时间
    # auto_now_add=True：记录创建时自动设置当前时间，之后不再修改
    created_at = models.DateTimeField('创建时间', auto_now_add=True, db_index=True)

    # 记录更新时间
    # auto_now=True：每次保存记录时自动更新为当前时间
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    # ==================== Meta类配置 ====================

    class Meta:
        """
        模型元数据配置
        Django使用Meta类来定义模型的行为和显示信息
        """
        verbose_name = '服务器'          # 单数形式的模型名称
        verbose_name_plural = '服务器'    # 复数形式的模型名称
        ordering = ['-created_at']       # 默认排序：按创建时间倒序

    # ==================== 字符串表示方法 ====================

    def __str__(self):
        """
        模型的字符串表示
        在Django管理后台和其他地方显示此模型的文本
        格式：序列号 - 主机名（如果主机名为空则显示'Unknown'）
        """
        return f"{self.sn} - {self.hostname or 'Unknown'}"

    # ==================== 密码处理方法 ====================

    def set_ssh_password(self, password):
        """
        设置SSH密码（Base64编码）

        Args:
            password (str): 原始密码字符串

        Note:
            虽然使用了Base64编码，但这不是安全的密码存储方式。
            生产环境建议使用Django的加密字段或专门的密钥管理系统。
        """
        if password:
            # 将密码转换为bytes，然后进行Base64编码，最后转换回字符串
            self.ssh_password = base64.b64encode(password.encode()).decode()

    def get_ssh_password(self):
        """
        获取SSH密码（Base64解码）

        Returns:
            str: 解码后的原始密码，如果解码失败则返回空字符串

        Note:
            包含异常处理，防止存储的数据损坏时导致程序崩溃
        """
        if self.ssh_password:
            try:
                # 将Base64字符串转换为bytes，解码后再转换回字符串
                return base64.b64decode(self.ssh_password.encode()).decode()
            except Exception:
                # 如果解码失败（如数据损坏），返回空字符串
                return ''
        return ''


class HardwareInfo(models.Model):
    """
    硬件信息模型 v2.0

    存储服务器的详细硬件信息，包括CPU、内存、磁盘等组件的规格数据。
    与Server模型建立一对一关系，每台服务器对应一条硬件信息记录。

    v2.0版本采用JSON字段存储结构化数据，比v1.0的纯文本格式更加规范。
    """
    # ==================== 关联字段 ====================

    # 与Server模型的一对一关系
    # OneToOneField确保每台服务器只能有一条硬件信息记录
    server = models.OneToOneField(
        Server,                           # 关联的模型
        on_delete=models.CASCADE,         # 级联删除：删除服务器时同时删除硬件信息
        related_name='hardware',          # 反向关系名称：server.hardware
        verbose_name='服务器'              # 在管理后台显示的字段名称
    )

    # ==================== CPU信息字段 ====================

    # CPU详细信息（JSON格式）
    # 存储CPU的完整规格信息，结构示例：
    # {
    #   "model": "Intel Xeon E5-2680 v4",
    #   "architecture": "x86_64",
    #   "physical_cores": 14,
    #   "logical_cores": 28,
    #   "sockets": 2,
    #   "cache_size": "35MB",
    #   "frequency": "2.4GHz"
    # }
    cpu_info = models.JSONField('CPU信息', default=dict, blank=True)

    # ==================== 内存信息字段 ====================

    # 内存条详细信息列表（JSON格式）
    # 存储每个内存条的详细信息，结构示例：
    # [
    #   {
    #     "slot": "DIMM1",
    #     "size": "16GB",
    #     "speed": "2400MHz",
    #     "sn": "SN123456",
    #     "vendor": "Kingston",
    #     "type": "DDR4"
    #   },
    #   ...
    # ]
    memory_modules = models.JSONField('内存条信息', default=list, blank=True)

    # 系统总内存容量（GB）
    # 方便快速查询总内存大小，避免每次都解析JSON数据
    memory_total_gb = models.IntegerField('系统总内存(GB)', null=True, blank=True)

    # ==================== 磁盘信息字段 ====================

    # 磁盘设备信息列表（JSON格式）
    # 存储所有磁盘设备的详细信息，结构示例：
    # [
    #   {
    #     "device": "/dev/sda",
    #     "type": "SSD",
    #     "size": "500GB",
    #     "serial": "ABC123456",
    #     "pcie_slot": "PCIe 0:1:0",
    #     "model": "Samsung 970 EVO"
    #   },
    #   ...
    # ]
    disks = models.JSONField('磁盘信息', default=list, blank=True)

    # ==================== 原始数据字段 ====================

    # 原始采集数据备份
    # 保存Agent上报的原始JSON数据，用于调试和数据恢复
    raw_data = models.JSONField('原始数据', default=dict, blank=True)

    # ==================== 时间戳字段 ====================

    # 数据采集时间
    # auto_now=True：每次保存记录时自动更新为当前时间
    # 用于跟踪硬件信息的最后更新时间
    collected_at = models.DateTimeField('采集时间', auto_now=True)

    # ==================== Meta类配置 ====================

    class Meta:
        """模型元数据配置"""
        verbose_name = '硬件信息'
        verbose_name_plural = '硬件信息'

    # ==================== 字符串表示方法 ====================

    def __str__(self):
        """模型的字符串表示，显示关联服务器的序列号"""
        return f"{self.server.sn} 的硬件信息"

    # ==================== 实用方法 ====================

    def get_cpu_model(self):
        """
        获取CPU型号

        Returns:
            str: CPU型号名称，如果不存在则返回'Unknown'

        使用场景：
        - 在服务器列表中快速显示CPU信息
        - 生成硬件报表
        """
        return self.cpu_info.get('model', 'Unknown') if self.cpu_info else 'Unknown'

    def get_total_disk_size(self):
        """
        计算磁盘总容量

        Returns:
            int: 磁盘设备总数（简化版本）

        Note:
            当前实现只是简单返回磁盘数量，
            实际生产环境中应该解析size字段并累加容量。
            例如：将"500GB"、"1TB"等转换为统一单位进行计算。
        """
        if not self.disks:
            return 0
        # 简单累加磁盘数量（实际应该解析GB/TB单位计算总容量）
        return len(self.disks)


class SystemConfig(models.Model):
    """
    系统配置模型（单例模式）

    用于存储系统的全局配置参数，采用单例模式设计。
    主要配置项包括：
    1. IP白名单：控制哪些IP可以访问Agent脚本
    2. 定时任务配置：控制Agent数据采集的频率

    单例模式确保全局只有一条配置记录，通过get_config()类方法获取。
    """

    # ==================== 白名单配置字段 ====================

    # 允许访问的IP地址和网段
    # 每行一个IP或CIDR格式的网段，用于安全控制
    # 默认包含私有网络地址段：
    # - 10.0.0.0/8: A类私有网络
    # - 172.16.0.0/12: B类私有网络
    # - 192.168.0.0/16: C类私有网络
    allowed_networks = models.TextField(
        '允许的IP/网段',
        default='10.0.0.0/8\n172.16.0.0/12\n192.168.0.0/16',
        help_text='每行一个IP地址或网段（CIDR格式），如：10.10.90.0/24'
    )

    # ==================== 定时任务配置字段 ====================

    # Cron表达式
    # 定义Agent数据采集的执行频率
    # 格式：分 时 日 月 周
    # 示例：'0 * * * *' 表示每小时的第0分钟执行
    cron_expression = models.CharField(
        'Cron表达式',
        max_length=100,
        default='0 * * * *',  # 默认每小时执行一次
        help_text='格式：分 时 日 月 周，如：0 * * * *（每小时）'
    )

    # 定时任务描述
    # 用自然语言描述定时任务的执行频率，便于管理员理解
    cron_description = models.CharField(
        '定时任务描述',
        max_length=200,
        default='每小时执行一次',
        blank=True  # 允许为空
    )

    # ==================== 时间戳字段 ====================

    # 配置更新时间
    # 记录配置最后一次被修改的时间
    updated_at = models.DateTimeField('更新时间', auto_now=True)

    # ==================== Meta类配置 ====================

    class Meta:
        """模型元数据配置"""
        verbose_name = '系统配置'
        verbose_name_plural = '系统配置'

    # ==================== 字符串表示方法 ====================

    def __str__(self):
        """
        模型的字符串表示，包含最后更新时间
        格式：系统配置 - 更新于 2024-01-01 12:00:00
        """
        return f"系统配置 - 更新于 {self.updated_at.strftime('%Y-%m-%d %H:%M:%S')}"

    # ==================== 单例模式方法 ====================

    @classmethod
    def get_config(cls):
        """
        获取系统配置（单例模式实现）

        Returns:
            SystemConfig: 系统配置实例

        工作原理：
        1. 尝试获取主键为1的配置记录
        2. 如果不存在，则创建一条新的默认配置记录
        3. 返回配置实例

        使用场景：
        - 获取白名单配置进行IP验证
        - 获取定时任务配置
        - 在系统初始化时创建默认配置
        """
        config, created = cls.objects.get_or_create(pk=1)
        return config

    # ==================== IP白名单验证方法 ====================

    def is_ip_allowed(self, ip_address):
        """
        检查IP地址是否在白名单中

        Args:
            ip_address (str): 要检查的IP地址

        Returns:
            bool: True表示IP在白名单中，False表示不在

        工作流程：
        1. 解析输入的IP地址
        2. 逐行解析白名单配置
        3. 检查IP是否属于配置的网段
        4. 返回验证结果

        支持的格式：
        - 单个IP：192.168.1.100
        - 网段：192.168.1.0/24
        - 注释行：以#开头的行会被忽略

        异常处理：
        - 无效的IP地址格式返回False
        - 无效的网段格式会被跳过
        """
        import ipaddress  # Python标准库，用于IP地址和网络操作

        try:
            # 将输入字符串转换为IP地址对象
            ip = ipaddress.ip_address(ip_address)

            # 逐行处理白名单配置
            for line in self.allowed_networks.strip().split('\n'):
                line = line.strip()

                # 跳过空行和注释行
                if not line or line.startswith('#'):
                    continue

                try:
                    # 将网段字符串转换为网络对象
                    # strict=False允许非严格的CIDR表示法（如192.168.1.0/24）
                    network = ipaddress.ip_network(line, strict=False)

                    # 检查IP是否属于该网络
                    if ip in network:
                        return True
                except ValueError:
                    # 如果网段格式无效，跳过该行继续处理下一行
                    continue

            # 所有网段都不匹配，IP不在白名单中
            return False

        except ValueError:
            # 输入的IP地址格式无效
            return False
