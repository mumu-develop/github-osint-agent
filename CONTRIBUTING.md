# Contributing to GitHub OSINT Agent

Thank you for your interest in contributing to GitHub OSINT Agent! This document provides guidelines and instructions for contributing.

## Table of Contents

- [Code of Conduct](#code-of-conduct)
- [Getting Started](#getting-started)
- [Development Setup](#development-setup)
- [How to Contribute](#how-to-contribute)
- [Pull Request Process](#pull-request-process)
- [Coding Standards](#coding-standards)

## Code of Conduct

This project and everyone participating in it is governed by the [Apache Code of Conduct](https://www.apache.org/foundation/policies/conduct). By participating, you are expected to uphold this code.

## Getting Started

1. Fork the repository on GitHub
2. Clone your fork locally
3. Create a branch for your changes

## Development Setup

### Prerequisites

- Python 3.12+
- Node.js 18+
- MySQL 8.0+
- Redis (optional)

### Setup Steps

```bash
# 1. Clone your fork
git clone https://github.com/YOUR_USERNAME/github-osint-agent.git
cd github-osint-agent

# 2. Create a virtual environment
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# 3. Install Python dependencies
pip install -r requirements.txt

# 4. Install frontend dependencies
cd frontend
npm install
cd ..

# 5. Configure environment
cp .env.example .env
# Edit .env with your test credentials

# 6. Start dependencies
docker-compose up -d

# 7. Run the application
python run.py
```

## How to Contribute

### Reporting Bugs

If you find a bug, please create an issue with:
- A clear title
- Steps to reproduce
- Expected behavior
- Actual behavior
- Environment details (OS, Python version, etc.)

### Suggesting Features

Feature suggestions are welcome! Please create an issue with:
- A clear description of the feature
- Why it would be useful
- Possible implementation approach (optional)

### Adding New Sub-Agents

1. Create a new YAML file in `subagents/` directory
2. Implement corresponding tool class in `app/tools/`
3. Register in `loader.py` TOOL_CLASS_MAP
4. Add tests and documentation

### Adding New Tools

1. Add the method to an existing tool class in `app/tools/`
2. Include it in the YAML `methods` list
3. Add unit tests
4. Update documentation

## Pull Request Process

1. **Create a branch**: Create a feature branch from `main`
   ```bash
   git checkout -b feature/your-feature-name
   ```

2. **Make changes**: Implement your changes following coding standards

3. **Test your changes**: Ensure all tests pass
   ```bash
   # Run tests (when available)
   pytest
   ```

4. **Commit changes**: Use clear commit messages
   ```bash
   git commit -m "Add: brief description of changes"
   ```

5. **Push to your fork**:
   ```bash
   git push origin feature/your-feature-name
   ```

6. **Create Pull Request**: Open a PR against the `main` branch

7. **Code Review**: Address any feedback from reviewers

8. **Merge**: Once approved, your PR will be merged

## Coding Standards

### Python

- Follow [PEP 8](https://pep8.org/) style guide
- Use type hints where appropriate
- Write docstrings for functions and classes
- Maximum line length: 120 characters

### Vue/JavaScript

- Follow [Vue style guide](https://vuejs.org/style-guide/)
- Use Composition API with `<script setup>`
- Component names: PascalCase
- Props: use type definitions

### General

- Write clear, self-documenting code
- Add comments only where necessary
- Keep functions small and focused
- Use meaningful variable names

## Questions?

If you have questions, feel free to:
- Create an issue with the label `question`
- Start a discussion in the Discussions section

Thank you for contributing!