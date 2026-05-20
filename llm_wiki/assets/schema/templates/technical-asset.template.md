---
title: <asset-title>
node_type: asset
status: active
asset_type: capability
source_projects:
  - themes/project/<nn-source-project>
suitable_for:
  - <scenario-1>
not_suitable_for:
  - <scenario-1>
tech_stack:
  - <stack-or-tool>
dependencies:
  - <dependency-or-none>
license: <license-boundary-or-review-note>
license_compatibility:
  compatible:
    - MIT
    - Apache-2.0
  incompatible: []
  conditional:
    - license: GPL
      condition: review_required
    - license: ELv2
      condition: review_required
maturity: tentative
reuse_level: reference
reuse_cost: medium
confidence: tentative
themes:
  - themes/project/<nn-source-project>
related_assets: []
related_entities: []
related_concepts: []
related_patterns: []
related_methods: []
related_themes:
  - themes/project/<nn-source-project>/README
source_pages:
  - themes/project/<nn-source-project>/wiki/reuse-assessment
evidence_from:
  - themes/project/<nn-source-project>/outputs/document-intake/<artifact>.json
supersedes: []
contradicts: []
updated: <YYYY-MM-DD>
---

# <Asset Title>

## 一句话定义

这项技术资产提供什么可复用能力。

## 可复用能力

- 能力：
- 复用级别：`direct | adapt | reference | reject`
- 适配成本：`low | medium | high`
- 置信度：`confirmed | inferred | tentative`

## 适用边界

- 适用于：
- 不适用于：

## 实现线索

- 来源项目：
- 关键模块：
- 关键接口 / 文件：
- 依赖：

## 约束与风险

- 许可证：
- 耦合风险：
- 验证缺口：

## 证据与来源

- 来源页：
- 证据：

## 新项目使用建议

- 推荐用法：
- 下一步验证：

## 相关页面

- <link-to-source-theme>
