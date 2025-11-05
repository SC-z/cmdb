# CMDB 资产管理系统需求概览

本文件描述当前版本的业务范围、技术约束与上线要求,供产品、研发与运维协同使用。

## 1. 目标与范围
- 面向 50 台以内服务器的 IT 团队,提供可快速部署的 CMDB+Agent 方案。
- 聚焦硬件资产盘点、Agent 自动部署、批量执行与 IP 白名单等核心能力。
- 不包含告警、分组/标签、实时性能监控以及复杂权限体系。

## 2. 功能需求
### 2.1 服务器管理
- 录入服务器(管理 IP 唯一),存储 SSH 用户名/密码/端口,可选主机名、BMC IP。
- 列表页支持 SN/主机名/管理 IP/BMC 搜索与状态过滤,展示 CPU/内存汇总、Agent 状态。
- 详情页展示基础信息、Agent 信息、硬件明细(JSON),支持删除归档。
- 14 天未上报自动归档到 `ArchivedServer` 并保存硬件快照。

### 2.2 Agent 采集
- `/api/agent/script/` 返回最新 `assets/agent.py`, 节点通过 `curl | python3` 拉取执行。
- 采集 SN、主机名、管理 IP、BMC IP、CPU、内存、磁盘,失败项回落到 `Unknown/null`。
- `/api/agent/report/` 校验 `sn`、`management_ip`, 根据 SN/IP 归档旧记录或更新现有记录,落库 `HardwareInfo`。
- Agent 默认 15 分钟执行,命令超时 10s,上报超时 30s,失败仅记录本地日志等待下次。

### 2.3 定时/批量执行
- SystemConfig 维护 Cron 表达式与 IP 白名单, Web 端可一键推送所有节点任务。
- ExecutionTask/Run/Stage/Job 组成批量命令执行链路,支持一次性与 Cron 任务,跟踪每台服务器状态与输出。

## 3. 技术与非功能要求
- **技术栈**: Django 4.2 + DRF 3.14, Python 3.12+, Bootstrap 5, Paramiko, SQLite(默认)。
- **依赖管理**: 推荐 `uv venv && source .venv/bin/activate`、`uv pip sync` 同步依赖。
- **部署**: 支持 `docker-compose up --build -d` 与 `python manage.py runserver`; Docker 模式挂载 `./data`、`./logs` 持久化。
- **性能**: 分钟级心跳、单实例部署即可满足; 无水平扩展与 HA 目标。
- **可维护性**: 代码遵循 4 空格缩进、snake_case; 业务逻辑沉淀到 `assets/utils.py` 等辅助模块。

## 4. 数据模型摘要
| 模型 | 关键字段 | 说明 |
| --- | --- | --- |
| `Server` | `sn`(唯一), `management_ip`, `bmc_ip`, `ssh_*`, `agent_*`, `last_report_time` | 服务器主表 |
| `HardwareInfo` | `cpu_info`, `memory_modules`, `memory_total_gb`, `disks`, `raw_data` | 一对一硬件快照 |
| `ArchivedServer`/`ArchivedHardwareInfo` | 与现役同结构,附 `archived_reason`, `archived_at` | 历史快照 |
| `ExecutionTask`/`ExecutionRun`/`ExecutionStage`/`ExecutionJob` | 任务配置、运行状态、阶段输出 | 远程批量执行 |
| `SystemConfig` | `allowed_networks`, `cron_expression`, `cron_description` | 白名单与 Cron 配置 |

## 5. API 约束
- **下载脚本** `GET /api/agent/script/`: 结合 IP 白名单校验请求源; 返回脚本文本,节点直接 `python3 -` 执行。
- **上报数据** `POST /api/agent/report/`: `Content-Type: application/json`; `bmc_ip` 支持空值或无效占位(`"null"`, `0.0.0.0`)时忽略。
- 接口需记录归档原因(`sn_ip_changed`, `ip_reused_by_new_sn` 等)并持久化 `raw_data` 便于审计。

## 6. 运维与安全要求
- 基于 `.env.example` 生成 `.env`, 替换 `DJANGO_SECRET_KEY`, 合理设置 `DJANGO_ALLOWED_HOSTS`。
- Docker 部署需设置 `DJANGO_SUPERUSER_*` 环境变量,首登后修改默认密码。
- Agent 下载接口绑定 IP 白名单; 如果公网暴露,需结合反向代理或 VPN。
- 定时运行 `python manage.py cleanup_servers --days 14` 或在容器中配置相应 cron,保持资产干净。

## 7. 非目标
- 不支持多租户、细粒度 RBAC、分布式任务队列、实时监控与报表导出。
- 暂不覆盖 Windows/非 Linux 节点,无 GUI Agent。
