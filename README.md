# GitHub OSINT Agent

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Python](https://img.shields.io/badge/Python-3.12%2B-brightgreen.svg)](https://www.python.org/)
[![Vue](https://img.shields.io/badge/Vue-3.x-4FC08D.svg)](https://vuejs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.x-FF6B6B.svg)](https://github.com/langchain-ai/langgraph)

An intelligent multi-agent OSINT (Open Source Intelligence) system for automated GitHub repository security scanning, trend analysis, and compliance auditing powered by LangGraph and DeepAgents.

**[中文文档](./README_CN.md)**

## Features

- **Technical Trend Analysis**: Analyze Star growth trends across organization repositories, identify high-potential projects
- **Security Risk Analysis**: Scan dependency vulnerabilities (CVE) via OSV.dev API, detect sensitive information leakage
- **Community Health Analysis**: Analyze Issue/PR response times, contributor activity metrics
- **Compliance Audit**: Check license compliance, scan copyright declarations
- **Real-time Alerts**: Webhook integration with DingTalk, Feishu, Slack, Discord, Email
- **Tiered Scanning**: L1 (Light/Daily) → L2 (Standard/Triggered) → L3 (Deep/Weekly)

## Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    Frontend Console (Vue3)                       │
│         Chat Interface │ Dashboard │ Alerts │ Config             │
└─────────────────────────────────┬───────────────────────────────┘
                                  │ SSE Streaming
┌─────────────────────────────────▼───────────────────────────────┐
│                     FastAPI Service Layer                        │
│          Streaming Chat │ Scan Trigger │ Status Query            │
└─────────────────────────────────┬───────────────────────────────┘
                                  │
┌─────────────────────────────────▼───────────────────────────────┐
│                DeepAgents Main Agent                             │
│    ┌────────────┬────────────┬────────────┬────────────┐        │
│    │ Trend      │ Security   │ Community  │ Compliance │        │
│    │ Analyzer   │ Analyzer   │ Analyzer   │ Analyzer   │        │
│    └─────┬──────┴─────┬──────┴─────┬──────┴─────┬──────┘        │
└─────────────────────────────────┬───────────────────────────────┘
                                  │ OpenSandbox Execution
          ┌───────────────────────┼───────────────────────┐
          ▼                       ▼                       ▼
   ┌─────────────┐        ┌─────────────┐        ┌─────────────┐
   │ GitHub API  │        │ OSV.dev API │        │ Alert       │
   │             │        │ (CVE Data)  │        │ Channels    │
   └─────────────┘        └─────────────┘        └─────────────┘
```

## Tech Stack

| Component | Technology |
|-----------|------------|
| **Backend** | FastAPI, Python 3.12+ |
| **Frontend** | Vue3, Vite |
| **AI Framework** | DeepAgents, LangChain, LangGraph |
| **Database** | MySQL 8.0+, Redis |
| **Sandbox** | OpenSandbox |
| **Scheduling** | APScheduler |

## Quick Start

### Prerequisites

- Python 3.12+
- Node.js 18+
- MySQL 8.0+
- Redis (optional, for distributed deployments)
- GitHub Personal Access Token

### 1. Clone the repository

```bash
git clone https://github.com/miaomiaoLmm/github-osint-agent.git
cd github-osint-agent
```

### 2. Configure environment

```bash
# Copy example config
cp .env.example .env

# Edit .env with your credentials:
# - GITHUB_TOKEN: Your GitHub Personal Access Token
# - MYSQL_*: MySQL connection settings
# - LLM_*: LLM API settings (OpenAI/Anthropic)
```

### 3. Start dependencies

```bash
# Using Docker Compose (recommended)
docker-compose up -d

# Or manually start MySQL and Redis
```

### 4. Install dependencies

```bash
# Python dependencies
pip install -r requirements.txt

# Frontend dependencies
cd frontend
npm install
cd ..
```

### 5. Run the application

```bash
# Start backend server
python run.py

# Start frontend (development mode)
cd frontend
npm run dev
```

### 6. Access the application

- Frontend: http://localhost:5173
- Backend API: http://localhost:8000
- API Docs: http://localhost:8000/docs

## API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/osint/chat/stream` | POST | SSE streaming chat interface |
| `/api/scanner/trigger` | POST | Trigger repository scan |
| `/api/scanner/status/{run_id}` | GET | Query scan task status |
| `/api/findings` | GET | List findings with filters |
| `/api/orgs` | GET/POST | Organization configuration CRUD |
| `/api/channel` | GET/POST | Alert channel management |
| `/health` | GET | Health check |

## Configuration

### Scan Types

| Type | Frequency | Coverage | LLM Usage |
|------|-----------|----------|-----------|
| **L1 Light** | Daily | All repos | None |
| **L2 Standard** | Triggered | High-risk repos | Moderate |
| **L3 Deep** | Weekly | Top repos | Full analysis |

### Alert Channels

| Channel | Region | Configuration |
|---------|--------|---------------|
| **DingTalk** | China | `DINGTALK_WEBHOOK`, `DINGTALK_SECRET` |
| **Feishu/Lark** | China | `FEISHU_WEBHOOK` |
| **Slack** | Global | `SLACK_WEBHOOK`, `SLACK_CHANNEL` |
| **Discord** | Global | `DISCORD_WEBHOOK` |
| **Email** | Global | `SMTP_HOST`, `SMTP_PORT`, `EMAIL_TO` |

Configure one or multiple channels in `.env`. CRITICAL and HIGH severity alerts are sent immediately to all configured channels.

## Project Structure

```
github-osint-agent/
├── app/                      # Backend application
│   ├── main.py               # FastAPI entry point
│   ├── agent.py              # DeepAgents main agent
│   ├── scanner/              # Scanning modules
│   ├── tools/                # Agent tools
│   ├── routes/               # API routes
│   ├── database/             # Database operations
│   └── alert/                # Alert notifications
├── frontend/                 # Vue3 frontend
│   └── src/
│       ├── components/       # UI components
│       └── styles/           # CSS styles
├── subagents/                # Sub-agent YAML configs
├── skills/                   # Skill modules
├── docker/                   # Docker configurations
├── scripts/                  # Utility scripts
├── tests/                    # Test files
├── requirements.txt          # Python dependencies
├── docker-compose.yml        # Docker Compose config
├── pyproject.toml            # Package configuration
├── Makefile                  # Convenience commands
└── .env.example              # Environment template
```

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for details.

## License

This project is licensed under the Apache License 2.0 - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [LangGraph](https://github.com/langchain-ai/langgraph) - Agent orchestration framework
- [OpenSandbox](https://github.com/alibaba) - Secure code execution sandbox
- [OSV.dev](https://osv.dev) - Open source vulnerability database