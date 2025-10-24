# CMDB 资产管理系统 - 开发需求文档

**版本**: 1.0 MVP
**更新日期**: 2025-10-09
**项目类型**: Demo/最小可行产品

---

## 目录

1. [项目概述](#项目概述)
2. [核心功能需求](#核心功能需求)
3. [数据模型设计](#数据模型设计)
4. [Agent设计规范](#agent设计规范)
5. [业务逻辑规则](#业务逻辑规则)
6. [API接口设计](#api接口设计)
7. [Web界面设计](#web界面设计)
8. [项目结构](#项目结构)
9. [技术栈](#技术栈)
10. [开发计划](#开发计划)
11. [部署说明](#部署说明)
12. [安全考虑](#安全考虑)

---

## 项目概述

### 1.1 项目定位

CMDB（Configuration Management Database）是一个轻量级的服务器资产管理和生命周期跟踪系统,专为公司内网环境设计。

**核心特点**：
- 基于Django的Web应用
- 自动化Agent部署和信息采集
- 实时服务器状态监控
- 简单实用的Web界面
- RESTful API接口

### 1.2 使用场景

- **环境**: 公司内网
- **规模**: 几十台服务器
- **用户**: 运维团队
- **目标**: 快速部署、核心功能完整、界面简单实用

### 1.3 项目范围（MVP）

**包含功能**:
- ✅ 服务器基本信息管理
- ✅ SSH自动部署Agent
- ✅ 硬件信息自动采集
- ✅ 服务器状态监控（在线/离线）
- ✅ 简单的Web界面
- ✅ 基础API接口
- ✅ 14天自动清理机制

**不包含功能**:
- ❌ 用户认证和权限管理（内网信任环境）
- ❌ 服务器分组和标签
- ❌ 实时性能监控（CPU使用率、内存使用率）
- ❌ 告警通知
- ❌ 数据导出（Excel/CSV）
- ❌ 完整的CRUD API
- ❌ 前后端分离（Vue3 SPA）

---

## 核心功能需求

### 2.1 服务器管理

#### 2.1.1 添加服务器
- **功能**: 手动录入服务器基本信息
- **必填字段**:
  - 管理IP
  - SSH用户名
  - SSH密码
- **可选字段**:
  - SSH端口（默认22）
- **行为**:
  - 添加后自动尝试SSH连接
  - 自动部署Agent
  - 记录部署状态

#### 2.1.2 服务器列表
- **显示字段**:
  - SN（序列号,唯一标识）
  - 主机名
  - 管理IP
  - 状态（在线/离线）
  - 最后上报时间
  - Agent部署状态
- **功能**:
  - 搜索（按SN、主机名、IP）
  - 状态筛选
  - 手动刷新状态
  - 点击查看详情

#### 2.1.3 服务器详情
- **基本信息**:
  - SN、主机名、IP
  - 创建时间、最后更新时间
  - 最后上报时间
- **硬件信息**:
  - CPU: 型号、核心数、架构
  - 内存: 总大小、条数、sn、speed 、Locator
  - 磁盘: 总大小、总数量、每磁盘的大小、类型、sn
  - 网卡: MAC地址、接口名
- **原始数据**: 显示完整的JSON数据

#### 2.1.4 删除服务器
- **触发方式**:
  - 手动删除
  - 自动清理（14天未上报）
- **行为**: 级联删除关联的HardwareInfo

### 2.2 Agent自动部署

#### 2.2.1 部署流程
1. 通过SSH连接到目标服务器
2. 检查Python3环境
3. 创建目录 `/opt/cmdb_agent/`
4. 上传Agent脚本 `cmdb_agent.py`
5. 创建配置文件 `config.json`
6. 配置crontab定时任务（15分钟执行一次）
7. 立即执行一次采集

#### 2.2.2 部署要求
- 目标服务器已安装Python 3.x
- SSH用户具有sudo权限（或具有写入/opt权限）
- 网络连接正常

#### 2.2.3 失败处理
- 记录部署失败原因
- 允许手动重试部署
- 在界面显示部署状态

### 2.3 硬件信息采集

#### 2.3.1 必须采集（优先级P0）

**服务器IP**:
- 说明: 获取默认路由的IP地址
- 场景: 服务器可能有多网卡
- 方法: 解析默认路由接口的IP
- 要求: 必须准确,不能为空
- 兜底: 如果无法获取默认路由IP,使用hostname -I的第一个IP

**服务器SN**:
- 说明: 服务器序列号,作为唯一标识
- 方法: dmidecode -s system-serial-number
- 要求: 必须唯一,不能为空
- 兜底策略:
  1. dmidecode获取物理机SN
  2. /sys/class/dmi/id/product_serial（虚拟机）
  3. system-uuid（虚拟机）
  4. MAC地址生成（最后兜底）

#### 2.3.2 尽力采集（优先级P1）

**如果采集失败,使用"Unknown"**:

- **主机名**: hostname命令
- **CPU信息**:
  - 型号: lscpu | grep 'Model name'
  - 核心数: nproc
  - 架构: uname -m
- **内存信息**:
  - 总大小: /proc/meminfo
  - 条数: dmidecode -t memory（可选）
- **磁盘信息**:
  - 总大小: lsblk -b
  - 数量: 磁盘设备数量
- **网卡信息**:
  - MAC地址: ip link
  - 接口名: ip link
  - 速率: ethtool（可选）

#### 2.3.3 不采集（超出MVP范围）

- ❌ 实时性能数据（CPU使用率、内存使用率）
- ❌ IPMI/BMC信息
- ❌ BIOS版本
- ❌ 操作系统详细版本
- ❌ 已安装软件列表
- ❌ 进程和端口信息

### 2.4 服务器状态监控

#### 2.4.1 状态检测
- **在线检测**: Ping ICMP检测
- **Agent心跳**: 通过last_report_time判断
- **状态定义**:
  - 在线: Ping通 且 最近15分钟内有上报
  - 离线: Ping不通 或 超过30分钟未上报

#### 2.4.2 状态更新
- 手动刷新: Web界面点击刷新按钮
- 自动更新: Agent上报时自动更新为在线
- 定时检查: 通过crontab每5分钟执行一次

### 2.5 自动清理机制

#### 2.5.1 清理规则
- **触发条件**: 超过14天未上报数据
- **判断依据**:
  - 有上报记录: last_report_time < 14天前
  - 无上报记录: created_at < 14天前 且 last_report_time为空
- **清理方式**: 硬删除（级联删除HardwareInfo）

#### 2.5.2 实现方式
- Django管理命令: `python manage.py cleanup_servers`
- 参数:
  - `--days N`: 清理N天未上报的服务器（默认14）
  - `--dry-run`: 预览模式,不实际删除
  - `--force`: 强制删除,不需要确认
- Crontab定时: 每天凌晨3点自动执行

#### 2.5.3 安全措施
- 删除前记录详细日志
- 支持预览模式
- 交互式确认
- 统计和报告

---

## 数据模型设计

### 3.1 Server（服务器）

#### 字段定义

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | BigAutoField | PRIMARY KEY | 主键 |
| sn | CharField(100) | UNIQUE, INDEX | 序列号（唯一标识） |
| hostname | CharField(100) | - | 主机名 |
| management_ip | GenericIPAddressField | - | 管理IP（可变,不唯一） |
| status | CharField(20) | - | 状态（online/offline） |
| ssh_username | CharField(50) | - | SSH用户名 |
| ssh_password | CharField(200) | - | SSH密码（简单加密） |
| ssh_port | IntegerField | DEFAULT 22 | SSH端口 |
| agent_deployed | BooleanField | DEFAULT False | Agent是否已部署 |
| agent_version | CharField(20) | - | Agent版本 |
| last_report_time | DateTimeField | NULL | 最后上报时间 |
| created_at | DateTimeField | AUTO_NOW_ADD | 创建时间 |
| updated_at | DateTimeField | AUTO_NOW | 更新时间 |

#### 索引设计
- PRIMARY KEY: id
- UNIQUE INDEX: sn
- INDEX: created_at, last_report_time

#### 关键设计
1. **SN为唯一标识**: 数据库唯一约束,用于判断同一台服务器
2. **IP可变**: 不加唯一约束,允许服务器IP变化
3. **密码加密**: SSH密码使用Base64简单编码（内网环境）
4. **时间戳**:
   - created_at: 首次发现时间,不变
   - updated_at: 任何字段更新时间
   - last_report_time: Agent最后上报时间

### 3.2 HardwareInfo（硬件信息）

#### 字段定义

| 字段名 | 类型 | 约束 | 说明 |
|--------|------|------|------|
| id | BigAutoField | PRIMARY KEY | 主键 |
| server | ForeignKey(Server) | CASCADE, UNIQUE | 服务器（一对一） |
| cpu_model | CharField(200) | - | CPU型号 |
| cpu_cores | IntegerField | - | CPU核心数 |
| cpu_arch | CharField(50) | - | CPU架构 |
| memory_total | IntegerField | - | 内存总大小（GB） |
| memory_count | IntegerField | - | 内存条数 |
| disk_total | IntegerField | - | 磁盘总大小（GB） |
| disk_count | IntegerField | - | 磁盘数量 |
| network_cards | JSONField | - | 网卡信息（JSON数组） |
| raw_data | JSONField | - | 原始数据备份 |
| collected_at | DateTimeField | AUTO_NOW | 采集时间 |

#### 关系设计
- OneToOne关系: server -> HardwareInfo
- 级联删除: Server删除时,HardwareInfo自动删除
- related_name: 'hardware'

#### 简化设计说明
- 采用单表设计,不分拆CPU/Memory/Disk多表
- 详细信息存储在raw_data的JSON字段
- 满足快速查看需求,简化查询逻辑

### 3.3 数据关系图

```
Server (1) ←→ (1) HardwareInfo
  ↓ CASCADE DELETE
  删除Server时自动删除HardwareInfo
```

---

## Agent设计规范

### 4.1 Agent架构

#### 4.1.1 设计原则
- 独立运行: 单个Python脚本,无外部依赖
- 轻量级: 脚本大小 < 10KB
- 健壮性: 采集失败不影响其他项
- 兼容性: 支持主流Linux发行版

#### 4.1.2 运行模式
```bash
# 模式1: 定时采集上报（crontab）
*/15 * * * * /usr/bin/python3 /opt/cmdb_agent/cmdb_agent.py

# 模式2: 手动执行
python3 /opt/cmdb_agent/cmdb_agent.py

# 模式3: 输出到文件（调试）
python3 /opt/cmdb_agent/cmdb_agent.py --output /tmp/hardware.json
```

### 4.2 IP地址采集

#### 4.2.1 采集方法（按优先级）

**方法1: 默认路由接口IP（推荐）**
```bash
# 获取默认路由接口
interface=$(ip route | grep default | awk '{print $5}' | head -n1)

# 获取接口IP
ip=$(ip addr show $interface | grep 'inet ' | awk '{print $2}' | cut -d/ -f1)
```

**方法2: hostname -I**
```bash
ip=$(hostname -I | awk '{print $1}')
```

**方法3: Python socket**
```python
import socket
s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
# 连接到内网网关
gateway = subprocess.check_output("ip route | grep default | awk '{print $3}'", shell=True)
s.connect((gateway.strip(), 80))
ip = s.getsockname()[0]
```

#### 4.2.2 特殊场景处理
- **多网卡**: 优先取默认路由接口
- **无外网**: 不依赖外网地址（8.8.8.8）
- **虚拟机**: 同样适用
- **容器**: 取容器内的IP

### 4.3 SN序列号采集

#### 4.3.1 采集方法（按优先级）

**方法1: dmidecode（物理机）**
```bash
dmidecode -s system-serial-number
```

**方法2: sysfs（虚拟机）**
```bash
cat /sys/class/dmi/id/product_serial
```

**方法3: UUID**
```bash
dmidecode -s system-uuid
# 结果: UUID-xxxxx
```


#### 4.3.2 无效值过滤
需要过滤以下无效值：
- "Not Specified"
- "To Be Filled By O.E.M."
- "Default string"
- "System Serial Number"
- 空字符串
- "0"

#### 4.3.3 验证规则
- SN不能为空
- SN长度 > 3
- 必须是可打印字符

### 4.4 其他信息采集

#### 4.4.1 主机名
```bash
hostname
```

#### 4.4.2 CPU信息
```bash
# 型号
lscpu | grep 'Model name' | cut -d: -f2 | xargs

# 核心数
nproc

# 架构
uname -m
```

#### 4.4.3 内存信息
```bash
# 总大小（GB）
grep MemTotal /proc/meminfo | awk '{print int($2/1024/1024)}'

# 条数（可选,需要dmidecode）
dmidecode -t memory | grep "Size:" | grep -v "No Module" | wc -l
```

#### 4.4.4 磁盘信息
```bash
# 总大小（GB）
lsblk -b -d -n -o SIZE,TYPE | grep disk | awk '{sum+=$1} END {print int(sum/1024/1024/1024)}'

# 数量
lsblk -d -n -o TYPE | grep disk | wc -l
```

#### 4.4.5 网卡信息
```bash
# 列出所有接口（排除lo）
ip -o link show | awk -F': ' '{print $2}' | grep -v lo

# 每个接口的MAC
ip link show eth0 | grep ether | awk '{print $2}'
```

### 4.5 数据上报格式

#### 4.5.1 JSON格式
```json
{
  "sn": "ABC123456789",
  "management_ip": "192.168.1.100",
  "hostname": "web-server-01",
  "hardware_info": {
    "cpu_model": "Intel(R) Xeon(R) CPU E5-2680 v4 @ 2.40GHz",
    "cpu_cores": 16,
    "cpu_arch": "x86_64",
    "memory_total": 64,
    "memory_count": 4,
    "disk_total": 1000,
    "disk_count": 2,
    "network_cards": [
      {
        "interface": "eth0",
        "mac": "00:0c:29:6e:41:8a"
      },
      {
        "interface": "eth1",
        "mac": "00:0c:29:6e:41:94"
      }
    ]
  },
  "collected_at": "2025-10-09T10:30:00"
}
```

#### 4.5.2 上报接口
```
POST /api/agent/report/
Content-Type: application/json
```

#### 4.5.3 错误处理
- 上报失败: 记录到本地日志
- 网络超时: 30秒超时
- 重试机制: 不重试（等待下次定时任务）

### 4.6 Agent配置文件

#### config.json
```json
{
  "cmdb_server": "http://192.168.1.10:8000",
  "report_interval": 15,
  "timeout": 30,
  "log_file": "/var/log/cmdb_agent.log"
}
```

---

## 业务逻辑规则

### 5.1 服务器唯一性判断

#### 5.1.1 核心规则
- **唯一标识**: SN（序列号）
- **判断逻辑**: 通过SN查找服务器,存在则更新,不存在则创建

#### 5.1.2 SN唯一性保证
- 数据库层: UNIQUE约束
- 应用层: get_or_create逻辑
- Agent层: SN采集必须准确

### 5.2 IP变更处理

#### 5.2.1 场景1: 服务器重装系统
```
第一次: SN=ABC123, IP=192.168.1.100
重装后: SN=ABC123, IP=192.168.1.150

处理:
1. 通过SN=ABC123找到现有记录
2. 更新IP: 192.168.1.100 -> 192.168.1.150
3. 更新其他字段（hostname等可能变化）
4. 保持created_at不变
5. 更新updated_at和last_report_time
```

#### 5.2.2 场景2: 运行中修改IP
```
第一次: SN=DEF456, IP=192.168.1.200
修改后: SN=DEF456, IP=10.0.0.100

处理:
1. 通过SN=DEF456找到现有记录
2. 更新IP: 192.168.1.200 -> 10.0.0.100
3. 记录日志: "服务器DEF456 IP变化"
4. 更新last_report_time
```

#### 5.2.3 场景3: 正常上报（无变化）
```
上报: SN=GHI789, IP=192.168.1.50

处理:
1. 通过SN=GHI789找到现有记录
2. IP未变化,不记录日志
3. 更新硬件信息
4. 更新last_report_time
```

### 5.3 数据更新策略

#### 5.3.1 更新时机
- Agent每次上报时更新
- 判断依据: SN一致
- 更新范围: 所有字段（除created_at）

#### 5.3.2 更新逻辑
```python
# 伪代码
try:
    server = Server.objects.get(sn=agent_sn)
    # 服务器已存在,更新
    server.management_ip = agent_ip
    server.hostname = agent_hostname
    server.status = 'online'
    server.last_report_time = now()
    server.save()
except Server.DoesNotExist:
    # 新服务器,创建
    server = Server.objects.create(
        sn=agent_sn,
        management_ip=agent_ip,
        hostname=agent_hostname,
        status='online',
        last_report_time=now()
    )
```

#### 5.3.3 并发控制
- 使用Django ORM的事务
- update_or_create原子操作
- 数据库级别的UNIQUE约束保证

### 5.4 自动清理逻辑

#### 5.4.1 清理条件（OR关系）
```python
# 条件1: 有上报记录,但超过14天
last_report_time < (now - 14 days)

# 条件2: 从未上报,且创建超过14天
last_report_time IS NULL AND created_at < (now - 14 days)
```

#### 5.4.2 清理流程
1. 查询符合条件的服务器
2. 显示清理列表（预览模式）
3. 确认删除（交互模式）
4. 记录删除日志
5. 执行级联删除（Server + HardwareInfo）
6. 输出删除报告

#### 5.4.3 安全保护
- 预览模式: --dry-run
- 交互确认: 需输入"yes"
- 详细日志: 记录每条删除记录
- 统计报告: 成功/失败数量

### 5.5 状态管理

#### 5.5.1 在线状态判断
```python
# 条件（AND关系）
1. Ping通（ICMP响应）
2. 最近15分钟内有上报（last_report_time > now - 15min）

# 结果
status = 'online'
```

#### 5.5.2 离线状态判断
```python
# 条件（OR关系）
1. Ping不通
2. 超过30分钟未上报（last_report_time < now - 30min）

# 结果
status = 'offline'
```

#### 5.5.3 未知状态
```python
# 条件
从未上报（last_report_time IS NULL）

# 结果
status = 'unknown'
```

---

## API接口设计

### 6.1 Agent上报接口

#### 6.1.1 接口信息
```
POST /api/agent/report/
Content-Type: application/json
```

#### 6.1.2 请求参数
```json
{
  "sn": "ABC123456789",           // 必填,服务器SN
  "management_ip": "192.168.1.100", // 必填,管理IP
  "hostname": "web-server-01",     // 选填
  "hardware_info": {               // 选填
    "cpu_model": "Intel Xeon",
    "cpu_cores": 16,
    "cpu_arch": "x86_64",
    "memory_total": 64,
    "memory_count": 4,
    "disk_total": 1000,
    "disk_count": 2,
    "network_cards": [
      {
        "interface": "eth0",
        "mac": "00:0c:29:6e:41:8a"
      }
    ]
  },
  "collected_at": "2025-10-09T10:30:00"
}
```

#### 6.1.3 响应格式
```json
{
  "status": "success",
  "is_new": false,
  "server_id": 123,
  "message": "数据已更新"
}
```

#### 6.1.4 错误响应
```json
{
  "error": "SN is required",
  "status": "error"
}
```

#### 6.1.5 状态码
- 200: 成功
- 400: 参数错误
- 500: 服务器错误

### 6.2 获取服务器列表

#### 6.2.1 接口信息
```
GET /api/servers/
```

#### 6.2.2 响应格式
```json
{
  "count": 10,
  "results": [
    {
      "id": 1,
      "sn": "ABC123",
      "hostname": "web-01",
      "management_ip": "192.168.1.100",
      "status": "online",
      "last_report_time": "2025-10-09T10:30:00",
      "agent_deployed": true
    }
  ]
}
```

### 6.3 获取服务器详情

#### 6.3.1 接口信息
```
GET /api/servers/{server_id}/
```

#### 6.3.2 响应格式
```json
{
  "id": 1,
  "sn": "ABC123",
  "hostname": "web-01",
  "management_ip": "192.168.1.100",
  "status": "online",
  "last_report_time": "2025-10-09T10:30:00",
  "created_at": "2025-09-01T08:00:00",
  "hardware": {
    "cpu_model": "Intel Xeon",
    "cpu_cores": 16,
    "memory_total": 64,
    "disk_total": 1000,
    "network_cards": [...]
  }
}
```

---

## Web界面设计

### 7.1 页面结构

#### 7.1.1 页面清单
1. 服务器列表页（首页）: `/`
2. 添加服务器页: `/add/`
3. 服务器详情页: `/server/<id>/`
4. Django Admin后台: `/admin/`

#### 7.1.2 布局设计
- 基于Bootstrap 5
- 响应式设计
- 顶部导航栏
- 内容区域
- 简洁的配色

### 7.2 服务器列表页

#### 7.2.1 功能
- 显示所有服务器
- 状态指示（在线/离线）
- 搜索框（SN、主机名、IP）
- 手动刷新按钮
- 添加服务器按钮

#### 7.2.2 表格字段
- SN（唯一标识）
- 主机名
- 管理IP
- 状态（徽章显示）
- 最后上报时间
- 操作（查看详情、删除）

#### 7.2.3 样式
```html
<table class="table table-striped table-hover">
  <thead>
    <tr>
      <th>SN</th>
      <th>主机名</th>
      <th>管理IP</th>
      <th>状态</th>
      <th>最后上报</th>
      <th>操作</th>
    </tr>
  </thead>
  <tbody>
    <!-- 服务器列表 -->
  </tbody>
</table>
```

### 7.3 添加服务器页

#### 7.3.1 表单字段
- 管理IP（必填）
- SSH用户名（必填）
- SSH密码（必填,密码输入框）
- SSH端口（选填,默认22）
- 主机名（选填）

#### 7.3.2 功能
- 表单验证
- 提交后自动部署Agent
- 显示部署结果
- 成功后跳转到列表页

### 7.4 服务器详情页

#### 7.4.1 信息展示
**基本信息**:
- SN
- 主机名
- 管理IP
- 状态
- 创建时间
- 最后更新时间
- 最后上报时间

**硬件信息**:
- CPU: 型号、核心数、架构
- 内存: 总大小、条数
- 磁盘: 总大小、数量
- 网卡: 接口、MAC地址

**原始数据**:
- JSON格式显示
- 代码高亮

#### 7.4.2 操作
- 返回列表
- 刷新状态
- 删除服务器

### 7.5 Django Admin后台

#### 7.5.1 Server模型
- list_display: sn, hostname, management_ip, status, last_report_time
- list_filter: status, agent_deployed
- search_fields: sn, hostname, management_ip
- readonly_fields: created_at, updated_at

#### 7.5.2 自定义操作
- 批量清理非活跃服务器
- 批量刷新状态

---

## 项目结构

### 8.1 目录结构

```
cmdb/
├── manage.py                      # Django管理脚本
├── requirements.txt               # Python依赖
├── start.sh                       # 一键启动脚本
├── README.md                      # 项目说明
├── PROJECT_STRUCTURE.md           # 项目结构说明
├── REQUIREMENTS.md                # 开发需求文档（本文档）
│
├── cmdb/                          # Django项目配置
│   ├── __init__.py
│   ├── settings.py                # 项目配置
│   ├── urls.py                    # 主URL路由
│   ├── wsgi.py                    # WSGI配置
│   └── asgi.py                    # ASGI配置
│
├── assets/                        # 资产管理应用
│   ├── __init__.py
│   ├── apps.py                    # 应用配置
│   ├── models.py                  # 数据模型（Server, HardwareInfo）
│   ├── views.py                   # Web视图
│   ├── urls.py                    # Web URL路由
│   ├── api_views.py               # API视图
│   ├── api_urls.py                # API URL路由
│   ├── utils.py                   # 工具函数（SSH、Agent部署）
│   ├── agent.py                   # Agent模板脚本
│   ├── admin.py                   # Django Admin配置
│   │
│   ├── management/                # Django管理命令
│   │   ├── __init__.py
│   │   └── commands/
│   │       ├── __init__.py
│   │       ├── check_servers.py   # 服务器状态检查
│   │       └── cleanup_servers.py # 自动清理服务器
│   │
│   ├── migrations/                # 数据库迁移
│   │   ├── __init__.py
│   │   └── 0001_initial.py
│   │
│   └── templates/                 # 应用模板（可选）
│
├── templates/                     # HTML模板
│   ├── base.html                  # 基础模板
│   ├── server_list.html           # 服务器列表
│   ├── server_detail.html         # 服务器详情
│   └── add_server.html            # 添加服务器
│
├── static/                        # 静态文件
│   ├── css/
│   │   └── style.css              # 自定义样式
│   ├── js/
│   │   └── main.js                # 自定义脚本（可选）
│   └── img/
│
└── db.sqlite3                     # SQLite数据库（运行后生成）
```

### 8.2 核心文件说明

#### 8.2.1 配置文件
- **settings.py**: Django配置,数据库、应用、静态文件等
- **urls.py**: URL路由,连接Web和API
- **requirements.txt**: Python依赖包

#### 8.2.2 数据模型
- **models.py**: Server、HardwareInfo两个核心模型

#### 8.2.3 视图层
- **views.py**: Web界面视图（4个页面）
- **api_views.py**: REST API视图（3个接口）
- **utils.py**: SSH连接、Agent部署等工具函数

#### 8.2.4 前端
- **templates/**: HTML模板（Bootstrap 5）
- **static/**: CSS、JS、图片

#### 8.2.5 Agent
- **agent.py**: Agent模板脚本,部署到目标服务器

#### 8.2.6 管理命令
- **check_servers.py**: 检查服务器状态
- **cleanup_servers.py**: 清理过期服务器

---

## 技术栈

### 9.1 后端技术

| 技术 | 版本 | 用途 |
|------|------|------|
| Python | 3.11+ | 编程语言 |
| Django | 4.2 | Web框架 |
| Django REST Framework | 3.14.0 | API框架 |
| Paramiko | 3.3.1 | SSH连接 |
| SQLite | 3.x | 数据库（默认） |

### 9.2 前端技术

| 技术 | 版本 | 用途 |
|------|------|------|
| Bootstrap | 5.3 | UI框架 |
| jQuery | 3.7 | DOM操作（少量） |
| HTML5 | - | 页面结构 |
| CSS3 | - | 样式 |

### 9.3 运维工具

| 工具 | 用途 |
|------|------|
| UV | Python包管理器（推荐） |
| pip | Python包管理器（备选） |
| Cron | 定时任务 |
| systemd | 服务管理（可选） |

### 9.4 依赖包（requirements.txt）

```txt
Django==4.2
djangorestframework==3.14.0
paramiko==3.3.1
```

**说明**: 只包含核心依赖,无冗余包

---

## 开发计划

### 10.1 开发阶段

#### 阶段1: 基础框架（2-3小时）

**任务**:
1. 创建Django项目
2. 配置settings.py
3. 定义数据模型（Server, HardwareInfo）
4. 数据库迁移
5. 配置Django Admin

**验收标准**:
- Django项目可以启动
- Admin后台可以访问
- 可以手动创建Server记录

#### 阶段2: Agent脚本（2小时）

**任务**:
1. 编写Agent采集脚本
2. 实现IP采集（默认路由）
3. 实现SN采集（多种方法）
4. 实现其他硬件信息采集
5. 实现HTTP上报功能

**验收标准**:
- Agent可以独立运行
- 能够准确采集IP和SN
- 能够生成正确的JSON数据

#### 阶段3: API接口（1-2小时）

**任务**:
1. 实现Agent上报接口
2. 实现SN唯一性判断
3. 实现数据更新逻辑
4. 实现服务器列表接口
5. 实现服务器详情接口

**验收标准**:
- Agent可以成功上报数据
- 数据正确存储到数据库
- 可以通过API查询服务器

#### 阶段4: SSH部署（1-2小时）

**任务**:
1. 实现SSH连接工具
2. 实现Agent文件上传
3. 实现Crontab配置
4. 实现部署状态记录
5. 错误处理和日志

**验收标准**:
- 可以SSH连接到目标服务器
- Agent自动部署成功
- Crontab配置正确

#### 阶段5: Web界面（2-3小时）

**任务**:
1. 创建基础模板（base.html）
2. 实现服务器列表页
3. 实现添加服务器页
4. 实现服务器详情页
5. 集成Bootstrap样式

**验收标准**:
- 界面美观、响应式
- 可以添加服务器
- 可以查看服务器列表和详情

#### 阶段6: 状态监控（1小时）

**任务**:
1. 实现Ping检测
2. 实现状态更新逻辑
3. 创建check_servers命令
4. 配置Crontab定时任务

**验收标准**:
- 可以检测服务器在线状态
- 状态显示正确

#### 阶段7: 自动清理（1小时）

**任务**:
1. 创建cleanup_servers命令
2. 实现清理逻辑
3. 实现预览模式
4. 实现日志记录

**验收标准**:
- 可以正确清理过期服务器
- 预览模式工作正常

#### 阶段8: 测试和优化（2小时）

**任务**:
1. 完整流程测试
2. 边界条件测试
3. 性能优化
4. 文档完善

**验收标准**:
- 所有功能正常工作
- 没有明显bug
- 文档完整

### 10.2 时间估算

| 阶段 | 预计时间 | 说明 |
|------|----------|------|
| 阶段1 | 2-3小时 | 基础框架 |
| 阶段2 | 2小时 | Agent脚本 |
| 阶段3 | 1-2小时 | API接口 |
| 阶段4 | 1-2小时 | SSH部署 |
| 阶段5 | 2-3小时 | Web界面 |
| 阶段6 | 1小时 | 状态监控 |
| 阶段7 | 1小时 | 自动清理 |
| 阶段8 | 2小时 | 测试优化 |
| **总计** | **12-16小时** | **约2个工作日** |

### 10.3 优先级

**P0（必须有）**:
- 数据模型
- Agent采集（IP、SN）
- API上报接口
- 简单Web界面

**P1（应该有）**:
- SSH自动部署
- 状态监控
- 完整Web界面

**P2（可以有）**:
- 自动清理
- Admin增强
- 日志完善

---

## 部署说明

### 11.1 环境要求

#### 11.1.1 CMDB服务器
- Python 3.8+ （推荐3.11+）
- 2GB+ 内存
- 10GB+ 磁盘空间
- Linux系统（CentOS/Ubuntu）

#### 11.1.2 被管理服务器
- Python 3.x
- 支持SSH连接
- 500MB+ 可用磁盘空间

### 11.2 快速安装

#### 11.2.1 使用UV安装（推荐）

```bash
# 1. 克隆或下载项目
cd /opt/cmdb

# 2. 安装UV
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"

# 3. 创建虚拟环境
uv venv

# 4. 激活虚拟环境
source .venv/bin/activate

# 5. 安装依赖
uv pip install -r requirements.txt

# 6. 数据库迁移
python manage.py makemigrations assets
python manage.py migrate

# 7. 创建超级用户
python manage.py createsuperuser

# 8. 启动服务
python manage.py runserver 0.0.0.0:8000
```

#### 11.2.2 一键启动脚本

创建 `start.sh`:
```bash
#!/bin/bash

# 检查UV
if ! command -v uv &> /dev/null; then
    echo "安装UV..."
    curl -LsSf https://astral.sh/uv/install.sh | sh
    export PATH="$HOME/.local/bin:$PATH"
fi

# 创建虚拟环境
if [ ! -d ".venv" ]; then
    uv venv
fi

# 激活虚拟环境
source .venv/bin/activate

# 安装依赖
uv pip install -r requirements.txt

# 数据库迁移
python manage.py makemigrations assets
python manage.py migrate

# 创建默认超级用户（如果不存在）
python manage.py shell -c "
from django.contrib.auth import get_user_model;
User = get_user_model();
if not User.objects.filter(username='admin').exists():
    User.objects.create_superuser('admin', 'admin@example.com', 'admin123')
    print('默认账号: admin / admin123')
"

# 启动服务
python manage.py runserver 0.0.0.0:8000
```

### 11.3 Crontab配置

#### 11.3.1 服务器状态检查
```bash
# 每5分钟检查一次
*/5 * * * * cd /opt/cmdb && source .venv/bin/activate && python manage.py check_servers >> /var/log/cmdb_check.log 2>&1
```

#### 11.3.2 自动清理过期服务器
```bash
# 每天凌晨3点执行
0 3 * * * cd /opt/cmdb && source .venv/bin/activate && python manage.py cleanup_servers --days 14 --force >> /var/log/cmdb_cleanup.log 2>&1
```

### 11.4 访问系统

- Web界面: `http://服务器IP:8000`
- Admin后台: `http://服务器IP:8000/admin`
- 默认账号: `admin / admin123`

---

## 安全考虑

### 12.1 认证和授权

#### 12.1.1 MVP阶段
- 内网信任环境,暂不实现用户认证
- Django Admin使用默认认证

#### 12.1.2 未来增强
- 实现用户登录
- 基于角色的权限控制
- API Token认证

### 12.2 SSH密码存储

#### 12.2.1 当前方案
- Base64简单编码
- 内网环境可接受

#### 12.2.2 未来增强
- AES加密
- 使用SSH密钥替代密码
- 密钥托管

### 12.3 网络安全

#### 12.3.1 当前方案
- 内网部署,防火墙保护
- HTTP协议（内网）

#### 12.3.2 未来增强
- HTTPS加密传输
- IP白名单
- API限流

### 12.4 数据安全

#### 12.4.1 当前方案
- SQLite本地存储
- 定期备份

#### 12.4.2 未来增强
- 数据库加密
- 访问审计日志
- 备份加密

---

## 附录

### A. 术语表

| 术语 | 说明 |
|------|------|
| CMDB | Configuration Management Database,配置管理数据库 |
| SN | Serial Number,序列号 |
| Agent | 部署在被管理服务器上的采集脚本 |
| MVP | Minimum Viable Product,最小可行产品 |
| SSH | Secure Shell,安全外壳协议 |
| IPMI | Intelligent Platform Management Interface |
| Crontab | Unix/Linux定时任务 |

### B. 参考资料

- Django官方文档: https://docs.djangoproject.com/
- Django REST Framework: https://www.django-rest-framework.org/
- Bootstrap 5: https://getbootstrap.com/
- Paramiko: https://www.paramiko.org/

### C. 常见问题

#### Q1: Agent采集SN失败怎么办？
A: Agent会尝试多种方法（dmidecode、sysfs、UUID、MAC）,确保能获取到唯一标识。

#### Q2: 服务器IP变化后会创建新记录吗？
A: 不会。系统通过SN判断同一台服务器,IP变化只会更新现有记录。

#### Q3: 如何手动清理某台服务器？
A: 可以在Admin后台直接删除,或使用cleanup_servers命令。

#### Q4: Agent采集频率可以调整吗？
A: 可以,修改crontab的定时配置即可。

#### Q5: 支持虚拟机和容器吗？
A: 支持虚拟机,容器需要额外配置（取容器内IP）。

### D. 更新日志

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.0 | 2025-10-09 | 初始版本,MVP需求 |

---

**文档结束**
