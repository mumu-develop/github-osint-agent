# Security Policy

## Supported Versions

| Version | Supported          |
| ------- | ------------------ |
| 1.0.x   | :white_check_mark: |
| < 1.0   | :x:                |

## Reporting a Vulnerability

We take security vulnerabilities seriously. If you discover a security issue, please report it responsibly.

### How to Report

**Please do NOT report security vulnerabilities through public GitHub issues.**

Instead, please report them via:

1. **Email**: Send details to the maintainer (preferably encrypted)
2. **GitHub Security Advisory**: Use the [Security Advisories](https://github.com/mumu-develop/github-osint-agent/security/advisories) feature

### What to Include

Please include the following information:

- Type of vulnerability (e.g., SQL injection, XSS, authentication bypass)
- Full paths of source file(s) related to the manifestation of the vulnerability
- The location of the affected source code (tag/branch/commit or direct URL)
- Any special configuration required to reproduce the issue
- Step-by-step instructions to reproduce the issue
- Proof-of-concept or exploit code (if possible)
- Impact of the issue, including how an attacker might exploit it

### Response Timeline

- **Initial Response**: Within 48 hours
- **Status Update**: Within 7 days
- **Fix Release**: Depends on severity (typically within 14 days for critical issues)

### Security Best Practices

When using this project:

1. **Never commit `.env` files** - Always use `.env.example` as a template
2. **Use strong GitHub tokens** - Limit token scope to minimum required permissions
3. **Secure your MySQL credentials** - Use strong passwords and restrict access
4. **Keep dependencies updated** - Regularly update to patch known vulnerabilities
5. **Enable Redis authentication** - If using Redis, set a strong password

### Known Security Considerations

- This project accesses GitHub API - ensure your tokens are properly scoped
- CVE scanning depends on OSV.dev API - verify API responses before acting
- Alert webhooks may contain sensitive information - secure your webhook endpoints

## Security Features

This project includes:

- Rate limiting for GitHub API calls
- Distributed lock via Redis to prevent concurrent scans
- Secure sandbox execution via OpenSandbox
- Sensitive file exclusion via `.gitignore`
- Structured logging without sensitive data leakage