# CMDB 资产管理系统

基于 Django 的轻量级 CMDB,内置 Agent 采集、批量执行与 IP 白名单控制,适合中小规模环境的快速落地。

## ✨ 核心特性
- 自动化采集: Agent 统一下发,采集 SN、管理 IP、BMC IP、CPU/内存/磁盘等硬件信息。
- 远程脚本执行: ExecutionTask 支持一次性/周期任务,追踪运行阶段和日志。
- Cron 与白名单管理: Web 端集中配置 Agent 调度频率与访问网段。
- NVMe/NVMeoF 识别: 批量命令减少 90% 以上调用,支持 PCIe/RDMA 场景。
- 轻量部署: 单体 Django + SQLite,可 `docker-compose` 或直接 `manage.py runserver`。

## 🏗 架构概览
```
┌─────────────────┐         GET /api/agent/script/        ┌──────────────────┐
│  CMDB Server    │ ◄──────────────────────────────────── │  Managed Node    │
│  (Django)       │                                        │  cron: curl|python│
│                 │ ────────────────────────────────────► │                  │
│ /api/agent/report/  ←  POST 硬件及 BMC 数据            │                  │
└─────────────────┘                                        └──────────────────┘
```

## 🚀 快速开始
### 方式一: Docker
```bash
git clone <repo>
cd cmdb
cp .env.example .env  # 更新 DJANGO_SECRET_KEY / 允许的 HOST
# 首次构建
docker-compose up --build -d
```
访问 `http://localhost:8000`, 使用创建的超级管理员账号登录。

### 方式二: 本地开发
```bash
uv venv && source .venv/bin/activate
uv pip install -e .
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver 0.0.0.0:8000
```
常用命令:
```bash
python manage.py test assets
python manage.py cleanup_servers --days 14 --dry-run
uv pip sync  # 按 pyproject 同步依赖
```

## 📁 项目结构
```
cmdb/
├── assets/                 # 业务代码: models/views/api/agent/utils
│   ├── agent.py            # Agent 采集脚本(节点 curl 获取)
│   ├── api_views.py        # /api/agent/script/ 与 /api/agent/report/
│   ├── models.py           # Server/HardwareInfo/ExecutionTask 等
│   └── management/commands # cleanup_servers 等定时任务
├── templates/              # Bootstrap 模板 (server_list/detail 等)
├── static/                 # CSS/JS/Icons
├── cmdb/                   # Django 配置(settings/urls)
├── docker-compose.yml / Dockerfile
└── start.sh                # 进程启动脚本
```

## 🛰 Agent 工作方式
- 节点定时任务示例:
  ```bash
  # /etc/cron.d/cmdb_agent
  0 * * * * root curl -s http://cmdb:8000/api/agent/script/ | python3 - --server http://cmdb:8000 \
    >> /var/log/cmdb_agent.log 2>&1
  ```
- 采集逻辑: 优先解析默认路由接口 IP,并通过 `ipmitool lan print` 获取 BMC IP; CPU/内存/磁盘批量命令减少执行次数。
- 上报结构: `sn`, `management_ip`, 可选 `bmc_ip`, 以及 `hardware_info` JSON; 无效 `bmc_ip`(如 `0.0.0.0`/`"null"`) 会被忽略。

## 🔐 运维与安全提示
- 基于 `.env.example` 生成 `.env`, 替换 `DJANGO_SECRET_KEY`, 设置 `DJANGO_ALLOWED_HOSTS`。
- Docker 模式建议通过环境变量配置 `DJANGO_SUPERUSER_*`, 首次登录后立即修改密码。
- 在系统设置中维护 IP 白名单; 若公网暴露,建议配合 VPN/反向代理。
- 定期运行 `python manage.py cleanup_servers` 清理 14 天未上报资产,保持数据准确。

## 🤝 贡献
欢迎提交 Issue / PR。提交前请确保通过 `python manage.py test assets` 并遵循 4 空格缩进与 snake_case 命名。

## 📄 许可证
MIT License
