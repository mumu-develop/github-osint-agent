---
name: contributor-stats
description: "贡献者统计技能 - 分析 GitHub 仓库的社区健康度、贡献者活跃度、Issue/PR 响应效率"
author: OSINT Team
version: 2.0.0
dependencies:
  - requests
metadata:
  openclaw:
    emoji: 👥
    tags: [community, contributor, issue, pr, health]
---

# 贡献者统计技能

分析 GitHub 仓库的社区健康度，包括贡献者活跃度、Issue/PR 响应效率等指标。

## Tool 与 Script 协作

本技能采用 **Tool + Script 分离** 设计：

| 场景 | 使用 Tool | 使用 Script |
|------|-----------|-------------|
| **单仓库** | `scan_repo` (community维度) | `generate_community_report()` |
| **多仓库** | `batch_check_community` | `generate_multi_repo_community_report()` |
| **组织级** | `batch_scan_org` | 直接输出（Tool 已包含报告） |

---

## 场景一：单仓库分析

### Tool 调用

```python
result = scan_repo(
    owner="sofastack",
    repo="sofa-rpc",
    dimensions="community"
)
```

### Script 调用

```python
from skills.community.contributor_stats.analyze import (
    calculate_health_score,
    generate_improvement_suggestions,
    generate_community_report,
)

health = calculate_health_score(
    issue_metrics=result.get("issue_metrics", {}),
    pr_metrics=result.get("pr_metrics", {}),
    contributor_activity=result.get("contributor_activity", {})
)

suggestions = generate_improvement_suggestions(health)
report = generate_community_report(health, "sofastack", "sofa-rpc", suggestions)
```

---

## 场景二：多仓库分析

### Tool 调用

```python
community_data = batch_check_community(
    repos="sofastack/sofa-rpc,sofastack/sofa-boot,sofastack/sofa-node"
)
```

### Script 调用

```python
from skills.community.contributor_stats.analyze import (
    aggregate_multi_repo_community,
    generate_multi_repo_community_report,
)

# 组装数据
findings_by_repo = {}
for repo in ["sofastack/sofa-rpc", "sofastack/sofa-boot"]:
    findings_by_repo[repo] = community_data.get("findings_by_repo", {}).get(repo, {})

aggregated = aggregate_multi_repo_community(findings_by_repo)
report = generate_multi_repo_community_report(
    aggregated=aggregated,
    repos=["sofastack/sofa-rpc", "sofastack/sofa-boot"]
)
```

---

## 可用函数

| 函数 | 场景 | 说明 |
|------|------|------|
| `calculate_health_score` | 单仓库 | 计算社区健康评分 |
| `generate_improvement_suggestions` | 单仓库 | 生成改进建议 |
| `aggregate_multi_repo_community` | 多仓库 | 按仓库聚合健康数据 |
| `generate_community_report` | 单仓库 | 生成单仓库报告 |
| `generate_multi_repo_community_report` | 多仓库 | 生成多仓库汇总报告 |

---

*让社区分析更全面 👥*