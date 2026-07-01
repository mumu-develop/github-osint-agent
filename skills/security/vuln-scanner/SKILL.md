---
name: vuln-scanner
description: "漏洞扫描技能 - 检查依赖包的 CVE 漏洞、评估安全风险等级、提供修复建议"
author: OSINT Team
version: 2.0.0
dependencies:
  - requests
metadata:
  openclaw:
    emoji: 🛡️
    tags: [security, vulnerability, cve, scan]
---

# 漏洞扫描技能

检查 GitHub 仓库的依赖包是否存在已知 CVE 漏洞，评估安全风险并提供修复建议。

## Tool 与 Script 协作

本技能采用 **Tool + Script 分离** 设计：

| 场景 | 使用 Tool | 使用 Script |
|------|-----------|-------------|
| **单仓库** | `scan_repo` | `generate_security_report()` |
| **多仓库** | `batch_check_cve`, `batch_scan_secrets` | `generate_multi_repo_report()` |
| **组织级** | `batch_scan_org` | 直接输出（Tool 已包含报告） |

---

## 场景一：单仓库分析

### Tool 调用

```python
# 单仓库多维度扫描
result = scan_repo(
    owner="sofastack",
    repo="sofa-rpc",
    dimensions="cve,secret"
)
```

### Script 调用

```python
from skills.security.vuln_scanner.analyze import (
    aggregate_vulnerabilities,
    generate_security_report,
)

# 聚合数据
aggregated = aggregate_vulnerabilities(
    vulnerabilities=result.get("cve_findings", []),
    secrets_found=result.get("secret_findings", [])
)

# 生成单仓库报告
report = generate_security_report(aggregated, "sofastack", "sofa-rpc")
```

---

## 场景二：多仓库分析（推荐）

### Tool 调用

```python
# 批量获取多个仓库的数据
cve_data = batch_check_cve(
    repos="sofastack/sofa-rpc,sofastack/sofa-boot,sofastack/sofa-node"
)

secret_data = batch_scan_secrets(
    repos="sofastack/sofa-rpc,sofastack/sofa-boot,sofastack/sofa-node"
)
```

### Script 调用

```python
from skills.security.vuln_scanner.analyze import (
    aggregate_multi_repo_vulnerabilities,
    generate_multi_repo_report,
)

# 组装按仓库分组的数据
findings_by_repo = {}
for repo in ["sofastack/sofa-rpc", "sofastack/sofa-boot", "sofastack/sofa-node"]:
    findings_by_repo[repo] = {
        "cve_findings": cve_data.get("findings_by_repo", {}).get(repo, []),
        "secret_findings": secret_data.get("findings_by_repo", {}).get(repo, [])
    }

# 聚合多仓库数据
aggregated = aggregate_multi_repo_vulnerabilities(findings_by_repo)

# 生成多仓库汇总报告
report = generate_multi_repo_report(
    aggregated=aggregated,
    repos=["sofastack/sofa-rpc", "sofastack/sofa-boot", "sofastack/sofa-node"]
)
```

---

## 场景三：组织级分析（最高效）

### Tool 调用

```python
# 一键扫描整个组织（Tool 内部已包含聚合）
result = batch_scan_org(
    org_name="sofastack",
    dimensions="cve,secret"
)

# 返回结果已包含汇总数据，无需额外 Script 处理
# 直接输出报告即可
```

---

## 风险等级定义

| 级别 | CVSS 评分 | 条件 | 处理建议 |
|------|-----------|------|----------|
| 🔴 严重 | ≥ 9.0 | 存在可利用漏洞 | 立即升级修复 |
| 🟠 高危 | ≥ 7.0 | 存在潜在风险 | 72小时内修复 |
| 🟡 中危 | ≥ 4.0 | 影响较小 | 下版本修复 |
| 🟢 低危 | < 4.0 | 影响很小 | 记录关注 |
| ✅ 安全 | 无 | 无已知漏洞 | 无需处理 |

---

## 报告路径

- 单仓库：`/reports/security/{owner}-{repo}-{timestamp}.md`
- 多仓库：`/reports/security/multi-repo-{timestamp}.md`

---

## 可用函数

| 函数 | 场景 | 说明 |
|------|------|------|
| `aggregate_vulnerabilities` | 单仓库 | 按风险等级分类 |
| `aggregate_multi_repo_vulnerabilities` | 多仓库 | 按仓库+风险等级双重分类 |
| `generate_security_report` | 单仓库 | 生成单仓库 Markdown 报告 |
| `generate_multi_repo_report` | 多仓库 | 生成多仓库汇总报告 |

---

*让安全扫描更全面 🛡️*