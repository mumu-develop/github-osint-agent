# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- Initial open source release preparation
- English README with badges
- CONTRIBUTING.md guide
- Issue and PR templates
- GitHub Actions CI/CD workflows
- Makefile for common commands
- Unit test framework setup

## [1.0.0] - 2024-07-01

### Added
- Multi-agent architecture with DeepAgents + LangGraph
- Technical trend analysis module
- Security vulnerability scanning (CVE via OSV.dev)
- Community health analysis module
- License compliance checking
- Real-time alert system (DingTalk/Feishu)
- Tiered scanning: L1/L2/L3
- Vue3 frontend with chat interface
- FastAPI backend with SSE streaming
- MySQL persistence for scan results
- APScheduler for scheduled scanning
- Docker Compose for local development

### Features
- SSE streaming chat interface
- Organization configuration management
- Repository monitoring with priority tiers
- Automated daily/weekly scanning
- Alert severity classification (CRITICAL/HIGH/MEDIUM/LOW)
- Scan task status tracking
- Finding acknowledgment workflow

### Technical
- OpenSandbox integration for secure code execution
- LangGraph checkpoint memory system
- Rate limiting for GitHub API
- Redis distributed lock support