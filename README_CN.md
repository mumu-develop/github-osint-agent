# GitHub OSINT Agent

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.x-4FC08D.svg)](https://vuejs.org/)

基于 DeepAgents + LangGraph + OpenSandbox 的 GitHub 开源情报系统。

**[English](./README.md)**

## 功能特性

- **技术趋势分析**: 分析组织仓库的 Star 增长趋势，识别高潜力项目
- **安全风控分析**: 通过 OSV.dev API 扫描依赖漏洞（CVE），检测敏感信息泄露
- **社区健康分析**: 分析 Issue/PR 响应速度、贡献者活跃度
- **合规审计分析**: 检查许可证合规性和版权声明
- **实时预警**: 钉钉/飞书 Webhook 集成，高危风险实时推送
- **分层扫描**: L1（轻量/每日）→ L2（标准/触发）→ L3（深度/每周）

## 快速开始

### 前置要求

- Python 3.12+
- Node.js 18+
- MySQL 8.0+
- Redis（可选，用于分布式锁）

### 1. 克隆项目

```bash
git clone https://github.com/miaomiaoLmm/github-osint-agent.git
cd github-osint-agent
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填入：
# - GITHUB_TOKEN: GitHub Personal Access Token
# - MYSQL_*: MySQL 连接配置
# - LLM_*: LLM API 配置（OpenAI/Anthropic）
```

### 3. 启动依赖服务

```bash
docker-compose up -d
```

### 4. 安装依赖

```bash
pip install -r requirements.txt
cd frontend && npm install && cd ..
```

### 5. 启动服务

```bash
python run.py
```

访问 http://localhost:8000 查看界面。

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/osint/chat/stream` | POST | SSE 流式对话 |
| `/api/scanner/trigger` | POST | 触发扫描 |
| `/api/scanner/status/{run_id}` | GET | 查询扫描状态 |
| `/api/findings` | GET | 发现列表 |
| `/api/orgs` | GET/POST | 组织配置管理 |

## 扫描类型

| 类型 | 频率 | 覆盖范围 | 大模型调用 |
|------|------|----------|-----------|
| **L1 轻量** | 每日 | 全部仓库 | 无 |
| **L2 标准** | 触发时 | 高危仓库 | 中等 |
| **L3 深度** | 每周 | Top 仓库 | 全量分析 |

## 项目结构

```
github-osint-agent/
├── app/                      # 后端应用
│   ├── main.py               # FastAPI 入口
│   ├── agent.py              # DeepAgents 主 Agent
│   ├── scanner/              # 扫描模块
│   ├── tools/                # Agent 工具
│   ├── routes/               # API 路由
│   └── alert/                # 预警通知
├── frontend/                 # Vue3 前端
├── subagents/                # 子 Agent 配置
├── skills/                   # 技能模块
└── docker/                   # Docker 配置
```

## 贡献指南

参见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

Apache License 2.0，详见 [LICENSE](LICENSE) 文件。