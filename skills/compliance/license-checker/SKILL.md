---
name: license-checker
description: "许可证检查技能 - 检查 GitHub 仓库的许可证合规性、评估兼容性、扫描版权声明"
author: OSINT Team
version: 2.0.0
dependencies:
  - requests
metadata:
  openclaw:
    emoji: ⚖️
    tags: [compliance, license, copyright, legal]
---

# 许可证检查技能

检查 GitHub 仓库的许可证合规性，评估许可证兼容性，扫描版权声明。

## Tool 与 Script 协作

本技能采用 **Tool + Script 分离** 设计：

| 场景 | 使用 Tool | 使用 Script |
|------|-----------|-------------|
| **单仓库** | `scan_repo` (license维度) | `generate_compliance_report()` |
| **多仓库** | `batch_check_license` | `generate_multi_repo_compliance_report()` |
| **组织级** | `batch_scan_org` | 直接输出（Tool 已包含报告） |

---

## 场景一：单仓库分析

### Tool 调用

```python
result = scan_repo(
    owner="sofastack",
    repo="sofa-rpc",
    dimensions="license"
)
```

### Script 调用

```python
from skills.compliance.license_checker.check import (
    assess_compliance_risk,
    generate_compliance_report,
)

risk = assess_compliance_risk(
    license_info=result.get("license_info", {}),
    copyright_info=result.get("copyright_info", {})
)

report = generate_compliance_report(
    license_info=result.get("license_info", {}),
    copyright_info=result.get("copyright_info", {}),
    risk_assessment=risk,
    owner="sofastack",
    repo="sofa-rpc"
)
```

---

## 场景二：多仓库分析

### Tool 调用

```python
license_data = batch_check_license(
    repos="sofastack/sofa-rpc,sofastack/sofa-boot,sofastack/sofa-node"
)
```

### Script 调用

```python
from skills.compliance.license_checker.check import (
    aggregate_multi_repo_compliance,
    generate_multi_repo_compliance_report,
)

# 组装数据
findings_by_repo = {}
for repo in ["sofastack/sofa-rpc", "sofastack/sofa-boot"]:
    findings_by_repo[repo] = {
        "license_info": license_data.get("findings_by_repo", {}).get(repo, {}),
        "copyright_info": {}
    }

aggregated = aggregate_multi_repo_compliance(findings_by_repo)
report = generate_multi_repo_compliance_report(
    aggregated=aggregated,
    repos=["sofastack/sofa-rpc", "sofastack/sofa-boot"]
)
```

---

## 场景三：组织级分析

```python
result = batch_scan_org(
    org_name="sofastack",
    dimensions="license"
)
# 返回结果已包含汇总数据
```

---

## 许可证类型分类

| 许可证 | 类型 | 商用兼容 | 主要限制 |
|--------|------|----------|----------|
| MIT | 开放 | ✅ | 需保留声明 |
| Apache-2.0 | 开放 | ✅ | 需保留声明、专利授权 |
| BSD-3-Clause | 开放 | ✅ | 需保留声明 |
| LGPL | 半开放 | ✅ 部分 | 动态链接可商用 |
| GPL-3.0 | 限制 | ❌ | 必须开源 |
| AGPL-3.0 | 限制 | ❌ | 网络服务也需开源 |
| 无许可证 | 未知 | ❌ | 默认版权保护 |

---

## 可用函数

| 函数 | 场景 | 说明 |
|------|------|------|
| `analyze_license_compatibility` | 兼容性分析 | 分析上游下游许可证兼容性 |
| `assess_compliance_risk` | 单仓库 | 评估合规风险等级 |
| `aggregate_multi_repo_compliance` | 多仓库 | 按仓库聚合合规数据 |
| `generate_compliance_report` | 单仓库 | 生成单仓库报告 |
| `generate_multi_repo_compliance_report` | 多仓库 | 生成多仓库汇总报告 |

---

*让合规检查更专业 ⚖️*