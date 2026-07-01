---
name: skill-management
description: "技能管理核心技能 - 提供技能下载、安全扫描、验证和分配能力"
author: OSINT Team
version: 1.0.0
dependencies:
  - requests
metadata:
  openclaw:
    emoji: 🔧
    tags: [skill, management, core]
---

# 技能管理核心技能

此技能是系统内置技能，用于管理其他技能的生命周期。

## 功能

1. **下载技能**: 从指定 URL 下载技能 ZIP 包
2. **安全扫描**: 检查技能是否包含危险代码或敏感文件
3. **验证技能**: 验证 SKILL.md 格式和依赖
4. **分配技能**: 将技能分配给子智能体

## 使用方法

主智能体调用 `download_skill` 工具下载技能，系统会自动执行安全扫描和验证流程。

## 安全规则

- 禁止使用 `exec()`, `eval()`, `os.system()` 等危险函数
- 禁止包含 `.env`, `.credentials`, `*.pem` 等敏感文件
- 网络连接仅允许白名单域名