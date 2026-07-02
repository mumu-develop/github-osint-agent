# Frequently Asked Questions (FAQ)

## General Questions

### What is GitHub OSINT Agent?

GitHub OSINT Agent is an intelligent multi-agent system for automated GitHub repository monitoring. It analyzes security vulnerabilities (CVE), technical trends, community health, and license compliance across multiple repositories.

### Who should use this tool?

- **Open Source Maintainers**: Monitor your projects' security and health
- **Security Teams**: Automate vulnerability scanning across repositories
- **Enterprise OSINT Teams**: Gather intelligence on open-source dependencies
- **AI/ML Developers**: Learn multi-agent architecture patterns with LangGraph

### Is this tool free?

Yes! This project is open source under the Apache 2.0 license. You can use, modify, and distribute it freely.

---

## Installation & Setup

### What are the prerequisites?

- Python 3.12+
- Node.js 18+ (for frontend)
- MySQL 8.0+
- Redis (optional, for distributed deployments)
- GitHub Personal Access Token

### How do I get a GitHub Token?

1. Go to GitHub Settings → Developer settings → Personal access tokens
2. Create a new token with `repo` and `public_repo` scopes
3. Add it to your `.env` file as `GITHUB_TOKEN`

### Why is MySQL required?

MySQL stores:
- Scan history and results
- Agent conversation checkpoints (LangGraph memory)
- Organization configurations
- Alert channel settings

You can use the provided `docker-compose.yml` to start MySQL locally.

### Can I run without Docker?

Yes. Install MySQL and Redis directly on your system, then:
```bash
pip install -r requirements.txt
python run.py
```

---

## Configuration

### What environment variables are required?

See `.env.example` for all options. Key variables:

| Variable | Required | Description |
|----------|----------|-------------|
| `GITHUB_TOKEN` | Yes | GitHub API access |
| `MYSQL_HOST` | Yes | MySQL server host |
| `MYSQL_PASSWORD` | Yes | MySQL password |
| `LLM_API_KEY` | For L2/L3 | OpenAI/Anthropic API key |

### How do I configure alert channels?

1. **DingTalk**: Create a robot in DingTalk group, get webhook URL and optional sign key
2. **Feishu**: Create a bot in Feishu/Lark, get webhook URL

Add them to `.env` or configure in the Organization Config UI.

### What scan types are available?

| Type | Frequency | Description |
|------|-----------|-------------|
| L1 Light | Daily | CVE + License check (no LLM) |
| L2 Standard | Triggered | LLM analysis for high-risk findings |
| L3 Deep | Weekly | Full LLM analysis on top repos |

---

## Usage

### How do I trigger a scan?

**API**:
```bash
curl -X POST http://localhost:8000/api/scanner/trigger \
  -H "Content-Type: application/json" \
  -d '{"scan_type": "L1_LIGHT", "org_name": "your-org"}'
```

**UI**: Go to Organization Config → Click "Scan Now"

### How do I check scan progress?

**API**: `GET /api/scanner/status/{run_id}`

**UI**: Dashboard shows real-time scan progress

### What vulnerability databases are used?

We use **OSV.dev** - an open-source vulnerability database that aggregates:
- CVE data
- GitHub Security Advisories
- PyPI, npm, Maven, Go ecosystem advisories

### How are severity levels determined?

| Level | CVSS Score | Examples |
|-------|------------|----------|
| CRITICAL | ≥9.0 | RCE, log4j |
| HIGH | 7.0-8.9 | SQL injection, auth bypass |
| MEDIUM | 4.0-6.9 | Info disclosure |
| LOW | 1.0-3.9 | Minor issues |

---

## Troubleshooting

### "GitHub API rate limit exceeded"

**Solution**:
- Wait 1 hour (5000 requests/hour for authenticated users)
- Add multiple tokens in `.env`: `GITHUB_TOKEN_1`, `GITHUB_TOKEN_2`
- Use GraphQL API (more efficient)

### "MySQL connection failed"

**Check**:
1. MySQL is running: `docker ps`
2. Credentials in `.env` match docker-compose.yml
3. Port 3306 is not blocked

### "LLM analysis not working"

**Requirements for L2/L3 scans**:
- Set `LLM_API_KEY` (OpenAI or Anthropic)
- Set `LLM_MODEL` (e.g., `gpt-4`, `claude-sonnet-4-5-20250929`)
- Ensure API key has sufficient quota

### "Alerts not being sent"

**Check**:
1. Webhook URL is correct
2. DingTalk requires sign key for security-enabled robots
3. Check `app/alert/` logs for errors

### "Frontend shows blank page"

**Solution**:
```bash
cd frontend
npm install
npm run dev
```

Ensure backend is running on port 8000.

---

## Architecture & Development

### What AI framework is used?

- **DeepAgents**: Agent orchestration layer
- **LangGraph**: State machine for multi-agent workflows
- **LangChain**: LLM integration

### How does the tiered scanning work?

```
L1 (Daily) → Fast, rule-based checks → Find high-risk items
                ↓
L2 (Triggered) → LLM analysis on high-risk → Deep investigation
                ↓
L3 (Weekly) → Full LLM analysis on top repos → Strategic insights
```

### How do I add a new analyzer?

1. Create YAML in `subagents/your-analyzer.yaml`
2. Implement tools in `app/tools/your_analyzer.py`
3. Register in `loader.py` TOOL_CLASS_MAP
4. Add tests in `tests/test_your_analyzer.py`

### Can I use a different LLM?

Yes! Supported providers:
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)
- Local models via LangChain integrations

Set `LLM_MODEL` in `.env`:
```
LLM_MODEL=openai:gpt-4
LLM_MODEL=anthropic:claude-sonnet-4-5-20250929
```

---

## Security & Privacy

### Is my data sent to external services?

- **GitHub API**: Repository metadata (public only)
- **OSV.dev**: Package names and versions for CVE lookup
- **LLM**: Only for L2/L3 scans, limited to findings context

No source code or secrets are sent externally.

### How do you protect sensitive configurations?

- `.env` is excluded from git (see `.gitignore`)
- Pre-commit hooks detect potential secret leaks
- Secrets never appear in logs

### Can I run this in a private network?

Yes. All components can run locally:
- MySQL: local or private instance
- Redis: local instance
- No external API calls required for L1 scans

---

## Contributing

### How do I contribute?

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

Quick steps:
1. Fork the repository
2. Create a feature branch
3. Make changes + add tests
4. Submit a Pull Request

### Where do I report bugs?

Open an issue using the [Bug Report template](.github/ISSUE_TEMPLATE/bug_report.md).

### How do I request a feature?

Open an issue using the [Feature Request template](.github/ISSUE_TEMPLATE/feature_request.md).

---

## More Questions?

If your question isn't answered here:
- Open an issue with the `question` label
- Check the [Documentation](README.md)
- Review existing [Issues](https://github.com/mumu-develop/github-osint-agent/issues)