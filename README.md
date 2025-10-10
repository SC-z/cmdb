# CMDB 资产管理系统

基于 Django 的轻量级 IT 资产管理系统，支持自动化硬件信息采集和管理。

## ✨ 核心特性

- **自动化采集**：Agent 自动采集服务器硬件信息（CPU、内存、磁盘）
- **远程脚本执行**：Agent 脚本集中管理，节点通过 `curl | python3` 远程执行
- **IP 白名单**：支持 IP/CIDR 网段访问控制
- **定时任务管理**：Web 界面统一配置和批量更新所有节点 cron 任务
- **NVMe/NVMeoF 支持**：完整支持 PCIe NVMe 和 RDMA NVMeoF 磁盘识别
- **轻量级部署**：SQLite 数据库，Docker 一键部署

## 🏗️ 架构设计

### 远程脚本执行模式

```
┌─────────────────┐         HTTP GET          ┌─────────────────┐
│  CMDB Server    │ ◄──────────────────────── │  Managed Node   │
│  (Django)       │                            │                 │
│                 │                            │  Cron Task:     │
│ /api/agent/     │ ──────────────────────►   │  curl | python3 │
│   script/       │   返回 agent.py 内容       │                 │
│                 │                            │                 │
│                 │ ◄──────────────────────── │                 │
│ /api/agent/     │   POST 硬件信息            │                 │
│   report/       │                            │                 │
└─────────────────┘                            └─────────────────┘
```

**优势：**
- ✅ 脚本集中存储在 CMDB 服务器
- ✅ 更新脚本后所有节点自动使用新版本
- ✅ 删除节点只需清理 `/etc/cron.d/cmdb_agent` 文件
- ✅ 节点无需存储任何脚本文件

## 🚀 快速开始

### 方式一：Docker 部署（推荐）

1. **克隆项目**

```bash
git clone https://github.com/your-username/cmdb.git
cd cmdb
```

2. **配置环境变量**

```bash
cp .env.example .env
# 编辑 .env 文件，修改配置
vim .env
```

3. **启动服务**

```bash
docker-compose up -d
```

4. **访问系统**

```
http://localhost:8000
默认账号：admin / admin123
```

### 方式二：手动部署

1. **安装依赖**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

2. **初始化数据库**

```bash
python manage.py migrate
python manage.py createsuperuser
```

3. **启动服务**

```bash
python manage.py runserver 0.0.0.0:8000
```

## 📖 使用指南

### 1. 系统设置

访问 **系统设置** 页面配置：

- **IP 白名单**：允许访问 Agent 脚本下载 API 的 IP/网段
  ```
  10.10.90.0/24
  172.16.0.0/12
  192.168.1.100
  ```

- **Cron 定时任务**：配置采集频率
  ```
  0 * * * *      # 每小时执行
  */30 * * * *   # 每 30 分钟执行
  0 */2 * * *    # 每 2 小时执行
  ```

### 2. 添加服务器

1. 点击 **添加服务器**
2. 填写服务器信息：
   - 管理 IP
   - SSH 用户名/密码/端口
   - 主机名（可选）
3. 系统自动：
   - 测试 SSH 连接
   - 检查 Python3 和 curl
   - 创建定时任务 `/etc/cron.d/cmdb_agent`
   - 立即执行一次采集

### 3. 查看硬件信息

点击服务器详情页面，查看：

- **CPU 信息**：型号、架构、核心数、Socket 数
- **内存信息**：每条内存的插槽、容量、频率、序列号、厂商
- **磁盘信息**：设备名、类型（NVMe/SSD/HDD/RDMA）、容量、序列号、PCIe 槽位

### 4. 批量更新定时任务

修改 Cron 表达式后，点击 **一键更新所有主机定时任务** 批量推送配置。

## 🔧 Agent 脚本

### 节点定时任务示例

```bash
# /etc/cron.d/cmdb_agent
0 * * * * root curl -s http://cmdb-server:8000/api/agent/script/ | python3 - --server http://cmdb-server:8000 >> /var/log/cmdb_agent.log 2>&1
```

### 手动执行 Agent

```bash
curl -s http://cmdb-server:8000/api/agent/script/ | python3 - --server http://cmdb-server:8000
```

### Agent 采集信息

- **基本信息**：SN、主机名、管理 IP
- **CPU**：lscpu + dmidecode
- **内存**：dmidecode -t memory
- **磁盘**：
  - 容量：lsblk（批量获取）
  - 类型：/sys/block/*/queue/rotational
  - NVMe 序列号：nvme list -o json（批量获取）
  - PCIe 槽位：nvme list-subsys（批量获取，支持 RDMA 识别）
  - SATA/SAS 序列号：smartctl

### 优化特性

- ✅ 批量命令调用（减少约 92% 的命令执行次数）
- ✅ 支持 NVMeoF（RDMA）磁盘识别
- ✅ 自动区分物理 PCIe 和远程 RDMA 连接

## 📁 项目结构

```
cmdb/
├── assets/                 # 核心应用
│   ├── models.py          # 数据模型（Server, HardwareInfo, SystemConfig）
│   ├── views.py           # Web 视图
│   ├── api_views.py       # API 接口（脚本下载、数据上报）
│   ├── utils.py           # 工具函数（SSH 部署）
│   ├── agent.py           # Agent 采集脚本
│   └── migrations/        # 数据库迁移
├── templates/             # HTML 模板
│   ├── base.html
│   ├── server_list.html
│   ├── server_detail.html
│   ├── add_server.html
│   └── system_settings.html
├── cmdb/                  # Django 项目配置
│   ├── settings.py
│   ├── urls.py
│   └── wsgi.py
├── Dockerfile
├── docker-compose.yml
├── requirements.txt
└── README.md
```

## 🛠️ 技术栈

- **后端**：Django 4.2 + Django REST Framework 3.14
- **数据库**：SQLite（可扩展为 PostgreSQL/MySQL）
- **SSH**：Paramiko 3.3.1
- **前端**：Bootstrap 5 + Bootstrap Icons
- **容器化**：Docker + Docker Compose

## 📊 数据模型

### Server（服务器）

- `sn`：序列号
- `hostname`：主机名
- `management_ip`：管理 IP（唯一）
- `status`：状态（online/offline/unknown）
- `ssh_username/password/port`：SSH 连接信息
- `agent_deployed`：Agent 是否已部署
- `agent_version`：Agent 版本
- `last_report_time`：最后上报时间

### HardwareInfo（硬件信息）

- `cpu_info`：JSONField - CPU 信息
- `memory_modules`：JSONField - 内存条列表
- `memory_total_gb`：系统总内存
- `disks`：JSONField - 磁盘列表
- `raw_data`：JSONField - 原始数据备份
- `collected_at`：采集时间

### SystemConfig（系统配置）

- `allowed_networks`：IP 白名单（支持 CIDR）
- `cron_expression`：Cron 表达式
- `cron_description`：定时任务描述
- `updated_at`：更新时间

## 🔐 安全特性

- ✅ IP 白名单访问控制
- ✅ SSH 密码 Base64 编码存储
- ✅ CSRF 保护
- ✅ 输入验证（IP 格式、端口范围、重复检查）

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

## 📄 许可证

MIT License

## 📧 联系方式

如有问题，请提交 Issue 或联系维护者。

---

**⭐ 如果这个项目对你有帮助，请给个 Star！**
