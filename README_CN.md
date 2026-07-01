# GitHub OSINT Agent

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.x-4FC08D.svg)](https://vuejs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.x-FF6B6B.svg)](https://github.com/langchain-ai/langgraph)

基于 LangGraph + DeepAgents + OpenSandbox 的智能 GitHub 开源情报系统，实现自动化安全扫描、趋势分析和合规审计。

**[English](./README.md)**

## 功能特性

- **技术趋势分析**: 分析组织仓库的 Star 增长趋势，识别高潜力项目
- **安全风险分析**: 通过 OSV.dev API 扫描依赖漏洞（CVE），检测敏感信息泄露
- **社区健康分析**: 分析 Issue/PR 响应速度、贡献者活跃度
- **合规审计分析**: 检查许可证合规性和版权声明
- **实时预警**: 支持钉钉、飞书、Slack、Discord、Email 等多种通知渠道
- **分层扫描**: L1（轻量/每日）→ L2（标准/触发）→ L3（深度/每周）

## 系统架构

```
┌─────────────────────────────────────────────────────────────────┐
│                    前端控制台 (Vue3)                              │
│         对话界面 │ 情报看板 │ 预警列表 │ 配置管理                   │
└─────────────────────────────────┬───────────────────────────────┘
                                  │ SSE 流式传输
┌─────────────────────────────────▼───────────────────────────────┐
│                     FastAPI 服务层                                │
│          流式对话 │ 扫描触发 │ 状态查询 │ 健康检查                   │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────┐
│                DeepAgents 主 Agent                                │
│    ┌────────────┬────────────┬────────────┬────────────┐        │
│    │ 趋势       │ 安全       │ 社区       │ 合规       │        │
│    │ 分析师     │ 分析师     │ 分析师     │ 分析师     │        │
│    └─────┬──────┴─────┬──────┴─────┬──────┴─────┬──────┘        │
└─────────────────────────────────┬───────────────────────────────┘
                                  │ OpenSandbox 安全执行
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
   ┌─────────────┐        ┌─────────────┐        ┌─────────────┐
   │ GitHub API  │        │ OSV.dev API │        │ 预警        │
   │             │        │ (CVE数据)   │        │ 渠道        │
   └─────────────┘        └─────────────┘        └─────────────┘
```

## 技术栈

| 组件 | 技术 |
|------|------|
| **后端** | FastAPI, Python 3.12+ |
| **前端** | Vue3, Vite |
| **AI框架** | DeepAgents, LangChain, LangGraph |
| **数据库** | MySQL 8.0+, Redis |
| **沙箱** | OpenSandbox |
| **调度** | APScheduler |

## 快速开始

### 前置要求

- Python 3.12+
- Node.js 18+
- MySQL 8.0+
- Redis（可选，用于分布式部署）
- GitHub Personal Access Token

### 1. 克隆项目

```bash
git clone https://github.com/miaomiaoLmm/github-osint-agent.git
cd github-osint-agent
```

### 2. 配置环境变量

```bash
# 复制配置模板
cp .env.example .env

# 编辑 .env 文件，填入你的凭证：
# - GITHUB_TOKEN: GitHub Personal Access Token
# - MYSQL_*: MySQL 连接配置
# - LLM_*: 大模型 API 配置（OpenAI/Anthropic）
```

### 3. 启动依赖服务

```bash
# 使用 Docker Compose（推荐）
docker-compose up -d

# 或手动启动 MySQL 和 Redis
```

### 4. 安装依赖

```bash
# Python 依赖
pip install -r requirements.txt

# 前端依赖
cd frontend
npm install
cd ..
```

### 5. 启动应用

```bash
# 启动后端服务
python run.py

# 启动前端开发模式
cd frontend
npm run dev
```

### 6. 访问应用

- 前端界面: http://localhost:5173
- 后端 API: http://localhost:8000
- API 文档: http://localhost:8000/docs

## API 接口

| 接口 | 方法 | 说明 |
|------|------|------|
| `/api/osint/chat/stream` | POST | SSE 流式对话接口 |
| `/api/scanner/trigger` | POST | 触发仓库扫描 |
| `/api/scanner/status/{run_id}` | GET | 查询扫描任务状态 |
| `/api/findings` | GET | 发现列表（分页筛选） |
| `/api/orgs` | GET/POST | 组织配置管理 |
| `/api/channel` | GET/POST | 告警渠道管理 |
| `/health` | GET | 健康检查 |

## 配置说明

### 扫描类型

| 类型 | 频率 | 覆盖范围 | 大模型调用 |
|------|------|----------|-----------|
| **L1 轻量** | 每日 | 全部仓库 | 无 |
| **L2 标准** | 触发时 | 高危仓库 | 中等 |
| **L3 深度** | 每周 | Top 仓库 | 全量分析 |

### 告警渠道

| 渠道 | 区域 | 配置项 |
|------|------|--------|
| **钉钉** | 中国 | `DINGTALK_WEBHOOK`, `DINGTALK_SECRET` |
| **飞书/Lark** | 中国 | `FEISHU_WEBHOOK` |
| **Slack** | 国际 | `SLACK_WEBHOOK`, `SLACK_CHANNEL` |
| **Discord** | 国际 | `DISCORD_WEBHOOK` |
| **Email** | 国际 | `SMTP_HOST`, `SMTP_PORT`, `EMAIL_TO` |

在 `.env` 中配置一个或多个渠道。CRITICAL 和 HIGH 级别的告警会立即发送到所有已配置的渠道。

## 项目结构

```
github-osint-agent/
├── app/                      # 后端应用
│   ├── main.py               # FastAPI 入口
│   ├── agent.py              # DeepAgents 主 Agent
│   ├── scanner/              # 扫描模块
│   ├── tools/                # Agent 工具
│   ├── routes/               # API 路由
│   ├── database/             # 数据库操作
│   └── alert/                # 预警通知
├── frontend/                 # Vue3 前端
│   └── src/
│       ├── components/       # UI 组件
│       └── styles/           # CSS 样式
├── subagents/                # 子 Agent YAML 配置
├── skills/                   # 技能模块
├── docker/                   # Docker 配置
├── scripts/                  # 工具脚本
├── tests/                    # 测试文件
├── requirements.txt          # Python 依赖
├── docker-compose.yml        # Docker Compose 配置
├── pyproject.toml            # 包配置
├── Makefile                  # 便捷命令
└── .env.example              # 环境变量模板
```

## 贡献指南

详见 [CONTRIBUTING.md](CONTRIBUTING.md)。

## 许可证

本项目采用 Apache License 2.0 许可证，详见 [LICENSE](LICENSE) 文件。

## 致谢

- [LangGraph](https://github.com/langchain-ai/langgraph) - Agent 编排框架
- [OpenSandbox](https://github.com/alibaba) - 安全代码执行沙箱
- [OSV.dev](https://osv.dev) - 开源漏洞数据库