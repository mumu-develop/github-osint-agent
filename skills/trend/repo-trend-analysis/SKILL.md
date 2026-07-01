---
name: repo-trend-analysis
description: "仓库趋势分析技能 - 分析 GitHub 仓库的 Star 增长趋势、识别高潜力项目、预测技术演进方向"
author: OSINT Team
version: 1.0.0
dependencies:
  - requests
metadata:
  openclaw:
    emoji: 📊
    tags: [trend, analysis, github, stars, growth]
---

# 仓库趋势分析技能

分析 GitHub 仓库的 Star 增长趋势，识别高潜力开源项目。

## Tool 与 Script 协作

本技能采用 **Tool + Script 分离** 设计：

| 阶段 | 使用 Tool | 使用 Script |
|------|-----------|-------------|
| 数据获取 | `get_org_repos`, `get_star_history`, `get_repo_stats` | — |
| 数据处理 | — | `analyze.py` 中的函数 |
| 报告组装 | — | `generate_trend_report()` |

---

## Tool 调用（获取数据）

```python
# 1. 获取组织仓库列表
repos = get_org_repos(org_name="antgroup")

# 2. 获取仓库详情
repo_stats = get_repo_stats(owner="antgroup", repo="sofa-boot")

# 3. 获取 Star 历史
star_history = get_star_history(owner="antgroup", repo="sofa-boot", limit=100)
```

---

## Script 调用（处理数据）

Tool 返回数据后，调用 `analyze.py` 中的函数进行评分和报告组装：

```python
# 导入算法模块
from skills.trend.repo-trend-analysis.analyze import (
    calculate_potential_score,
    rank_repos_by_potential,
    predict_growth_trend,
    generate_trend_report,
)

# 计算潜力评分
score = calculate_potential_score(
    repo_data=repo_stats,
    growth_rate=3.5,  # from calculate_growth_rate tool
    activity_score=0.8
)

# 批量评分并排序
all_scores = [calculate_potential_score(r, ...) for r in repos]
ranked = rank_repos_by_potential(all_scores, top_n=10)

# 预测趋势
prediction = predict_growth_trend(star_history, days=30)

# 组装报告
report = generate_trend_report(ranked, org_name="antgroup")
```

---

## 沙箱执行方式

也可以将数据写入沙箱文件，然后执行脚本：

```bash
# 1. Tool 获取数据后写入沙箱
write_file("/data/repos.json", json.dumps(repos))

# 2. 执行脚本处理
execute("python /skills/trend/repo-trend-analysis/analyze.py --input /data/repos.json --output /analysis/report.md")

# 3. 读取结果
report = read_file("/analysis/report.md")
```

---

## 高潜力项目判定标准

| 指标 | 阈值 | 权重 | 说明 |
|------|------|------|------|
| 增长率（7天） | > 10% 为高 | 40% | 近期增长速度 |
| Star 数 | > 1000 为高 | 20% | 社区关注度 |
| Fork 数 | > 100 为高 | 15% | 使用/贡献意愿 |
| 贡献者数 | > 20 为高 | 15% | 开发活跃度 |
| 近期活跃 | 有提交 | 10% | 维护状态 |

---

## 报告路径

分析结果保存到：
- 单仓库：`/reports/trend/{owner}-{repo}-{timestamp}.md`
- 组织：`/reports/trend/{org}-{timestamp}.md`

---

*让趋势分析更精准 📊*