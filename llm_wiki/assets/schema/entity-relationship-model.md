# Entity Relationship Model

## 目标

这份规范用于让知识库同时满足两件事：

- 对 LLM 来说，可沿着稳定的实体关系检索和综合知识
- 对 Obsidian 来说，可在 graph view 中看到可维护的知识图谱

它补充主题优先结构，而不是替代主题结构。

## 核心原则

1. 主题目录仍然是知识组织的第一入口。
2. 实体、概念、模式等跨页面对象必须尽量使用稳定 wikilink，而不是只保留纯文本提及。
3. 只要一个对象会被跨两个及以上页面反复引用，就应考虑给它稳定页面。
4. 关系要尽量显式写在 frontmatter 和正文里，不只依赖 Obsidian 的隐式 backlink。
5. 主题内知识优先落在主题页；一旦变成跨主题复用对象，再提升到 `shared/`。

## LLM Wiki 五层模型

本知识库按五层维护，避免把临时抽取结果误当成最终知识：

1. `raw source`
   - 原始资料，通常位于 `sources/` 或 `inbox/`。
   - 不修改、不重写，只作为事实来源。
2. `evidence artifact`
   - 由工具转换出的 markdown/json 证据层，通常位于 `outputs/document-intake/`。
   - 可读、可引用，但不是最终 wiki 页面。
3. `durable wiki`
   - LLM 维护的稳定综合层，位于 theme 的 `wiki/`、`README.md`、`meta.md`。
   - 负责沉淀结论、边界、权衡、未知项和来源链路。
4. `canonical graph`
   - `shared/entities/`、`shared/concepts/`、`shared/patterns/`、`shared/methods/`、`shared/assets/` 等稳定节点。
   - 负责跨主题导航和显式关系，不替代 theme 页面。
5. `engineering outputs`
   - `outputs/` 下从 wiki 编译出的行动视图，例如工程简报、实现指南、决策简报和 backlog。
   - 负责服务后续软件开发，但不作为新的事实来源。

`ingest` 的最终目标不是生成 evidence artifact，而是把新证据合并进 durable wiki，并在材料影响软件开发、架构、评估、工具链或项目规划时同步更新 engineering outputs。

## 运行时索引与状态报告

以下目录和文件服务 query、lint、freshness 检查和多源接入编排，不属于 durable wiki，也不应被当作 canonical graph 节点：

- `.qmd/` 或 qmd 本地索引目录：由 `qmd` 生成的本地检索索引。
- `.query-index/frontmatter.json`：由 `tools/kb_query_index.py` 生成的 frontmatter 查询索引。
- `.data-sources/registry.json`：由 `tools/kb_source_registry.py` 维护的 source registry 本地状态。
- `outputs/freshness/latest.json` 与 `outputs/freshness/latest.md`：由 `tools/kb_freshness_check.py` 生成的项目来源 freshness 报告。
- `outputs/document-intake/graphify/global-cross-project-report.*` 与各主题 `outputs/document-intake/graphify/` 下的 Graphify 图谱证据：由 `tools/kb_graphify_bridge.py` 生成，用于结构关系路由和跨项目连接审阅。
- `outputs/document-intake/graphify/runtime/`、`graphify-cache/`、`graph.html` 与 MCP 服务状态：运行态辅助产物，不属于 durable wiki，也不应进入 canonical graph。

这些产物可以作为 LLM 读写 wiki 时的辅助证据或路由线索，但不能自动覆盖 durable wiki。`freshness` 标记为 `stale` 时，只表示需要审阅 diff evidence；是否更新 wiki 页面仍由 ingest 阶段的语义判断决定。

## 节点类型

知识图谱中的主要节点分为五类：

- `theme`
  - 对应 `themes/<category>/<nn-theme-name>/`
  - 负责承载某一主题下的全量上下文
- `entity`
  - 具体对象，如系统、组件、角色、工具、协议、模型、数据集
- `concept`
  - 抽象概念，如评测维度、架构原则、模式定义、术语
- `pattern`
  - 可复用做法，如排障模式、设计模式、操作流程
- `method`
  - 更偏步骤或方法论的沉淀，如实验方法、分析方法、检查方法
- `asset`
  - 可复用技术资产，如可迁移能力、模块方案、工程实践、工具链模式、API 文档模式或观测面板模式

## 目录约定

跨主题知识统一放在 `shared/` 下，推荐目录如下：

- `shared/entities/`
- `shared/concepts/`
- `shared/patterns/`
- `shared/methods/`
- `shared/tools/`
- `shared/glossary/`
- `shared/assets/`

主题内仍可保留本地页，例如：

- `themes/<category>/<nn-theme-name>/wiki/concepts/`
- `themes/<category>/<nn-theme-name>/wiki/patterns/`
- `themes/<category>/<nn-theme-name>/wiki/checklists/`

使用规则：

- 如果只服务一个主题，先写主题内页面
- 如果跨两个及以上主题复用，提升到 `shared/`
- 提升后保留主题页，但要互相链接

## 技术资产节点

`shared/assets/` 用于承载可以服务未来项目的可复用能力资产。它不是源码归档，也不是泛泛经验总结，而是把历史项目、开源项目或研究材料中已被证据支持的能力沉淀成可匹配对象。

技术资产最低需要说明：

- 它提供什么能力
- 来源项目和证据链是什么
- 适合哪些新项目场景
- 不适合或不能直接复用的边界
- 技术栈、依赖、许可证和耦合风险
- `license_compatibility`：与常见许可证的工程兼容性标签，至少标出 MIT、Apache-2.0、GPL 和 ELv2 相关风险
- 复用级别：`direct | adapt | reference | reject`
- 适配成本：`low | medium | high`
- 置信度：`confirmed | inferred | tentative`

技术资产与其他节点的分工：

- `entity` 描述具体对象或组件本身。
- `concept` 描述抽象概念。
- `pattern` 描述可重复做法。
- `asset` 描述面向未来项目可评估、可匹配、可验证的复用能力。

当一个项目只有局部复用价值时，先写入该项目 `wiki/reuse-assessment.md` 和 `outputs/reuse-candidates.md`。只有当能力足够稳定、可被未来项目复用，并且有来源证据时，再提升为 `shared/assets/`。

## 何时创建实体页

出现以下任一情况时，应考虑创建稳定实体页：

- 同一对象在两个及以上主题中出现
- 一个对象在同一主题中被两个及以上页面引用
- 它会成为用户反复 query 的对象
- 它与多个决策、模式、故障或实验有关
- 如果没有独立页面，术语会在多个页面中漂移失真

不建议创建实体页的情况：

- 只出现一次且上下文很短
- 仍然高度不确定，尚无稳定命名
- 更适合保留在 `open-questions.md` 中

## LLM Decision Boundaries

这份 schema 的作用是约束 LLM 如何维护 wiki，而不是让脚本提前替 LLM 做所有语义判断。

因此在 ingest 时，LLM 应优先回答以下问题：

1. 这份新证据是否足以改变 durable knowledge？
2. 应该先修订现有主题页，还是确实需要新建页面？
3. 这个对象是否已经稳定到值得 canonicalize？
4. 这个对象是否已经跨主题到值得进入 `shared/`？
5. 如果证据不足，是否应先写入 `open-questions.md` 而不是强行沉淀？

## When Not To Canonicalize

出现以下任一情况时，不应急于创建 canonical page：

- 术语尚无稳定命名
- 证据质量低，或提取结果主要是噪声
- 该对象只在一个来源中短暂出现
- 它更像当前主题的临时工作概念，而不是长期复用节点
- 现有页面只需补一小段解释即可容纳该信息

在这些情况下，优先：

- 更新当前 theme 的 `wiki/*`
- 将不确定项写入 `wiki/open-questions.md`
- 等待更多来源后再决定是否 canonicalize

## When To Stay Inside Theme

满足以下情况时，优先保留在主题内：

- 信息只影响一个 theme
- 结论依赖具体项目或局部上下文
- 当前 source 只是补充某个已有主题页，而不是形成跨主题稳定定义
- 若过早进入 `shared/`，会让定义脱离上下文

推荐落点包括：

- `README.md`
- `wiki/overview.md`
- `wiki/glossary.md`
- `wiki/open-questions.md`
- `wiki/concepts/`
- `wiki/patterns/`

## When To Escalate To Shared

只有当以下条件同时满足时，才应考虑提升到 `shared/`：

- 该对象会被多个 theme 复用
- 定义已经相对稳定
- 当前 source 明确增强了跨主题理解，而不是只补局部细节
- 若继续只留在 theme 内，会导致多个主题重复维护同一说明

如果仍不满足这些条件，优先先在 theme 内沉淀，再等待后续资料触发 shared 提升。

## Canonical Link 规则

所有高频对象都应有一个 canonical page，并遵守以下规则：

1. 页面名使用稳定 ASCII slug。
2. 正文第一次出现该对象时，优先使用带显示文本的 wikilink。
3. 后续重复出现时，可以继续使用短链接，但不要频繁改名。
4. 不要为同一对象创建多个近义路径。
5. 若对象有别名，把别名写入 frontmatter 的 `aliases`。

示例：

```md
shared/concepts/agent-evaluation -> Agent Evaluation
shared/entities/llm-judge -> LLM Judge
themes/project/03-payment-platform/README -> 03-payment-platform
```

## Frontmatter 字段规范

实体页与概念页建议使用以下字段：

```yaml
---
title: Agent Evaluation
node_type: concept
status: active
aliases:
  - agent eval
tags:
  - evaluation
  - agents
themes:
  - themes/general/02-agent-evaluation
related_entities:
  - shared/entities/llm-judge
related_concepts:
  - shared/concepts/evaluation-metrics
related_patterns:
  - shared/patterns/eval-loop
related_methods:
  - shared/methods/benchmark-design
related_assets:
  - shared/assets/api-source-location-registry
related_themes:
  - themes/research/01-agent-observability
source_pages:
  - themes/general/02-agent-evaluation/wiki/overview
  - themes/research/01-agent-observability/wiki/overview
evidence_from:
  - themes/general/02-agent-evaluation/sources/docs/example.pdf
supersedes: []
contradicts: []
updated: 2026-05-12
---
```

字段解释：

- `title`
  - 人类可读标题
- `node_type`
  - 仅允许 `entity | concept | pattern | method | glossary | asset`
- `status`
  - 推荐使用 `active | tentative | deprecated | archived`
- `aliases`
  - 同义词、旧名称、缩写
- `tags`
  - 主题标签，不替代关系字段
- `themes`
  - 这个对象当前关联到哪些主题
- `related_entities`
  - 指向其他实体页
- `related_concepts`
  - 指向概念页
- `related_patterns`
  - 指向模式页
- `related_methods`
  - 指向方法页
- `related_assets`
  - 指向技术资产页
- `related_themes`
  - 指向主题入口页
- `source_pages`
  - 当前 wiki 中直接讨论该对象的页面
- `evidence_from`
  - 支撑它的原始资料路径
- `supersedes`
  - 明确覆盖了哪些旧结论
- `contradicts`
  - 与哪些已有页面或结论冲突
- `updated`
  - 最近更新时间

技术资产页还必须包含结构化许可证兼容性字段：

```yaml
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
```

该字段是工程复用风险标签，不是法律意见。复杂许可证、混合许可证或代码复制场景应使用 `review_required` 或更具体的条件说明。

## 正文结构规范

除 frontmatter 外，正文建议包含这些部分：

- `## 一句话定义`
- `## 为什么重要`
- `## 核心关系`
- `## 证据与来源`
- `## 当前结论`
- `## 未决问题`
- `## 相关页面`

其中：

- `核心关系` 必须出现显式 wikilink
- `证据与来源` 应尽量写到具体来源或主题页
- `相关页面` 用于增强 Obsidian 图谱可见性

## Canonical Node 最低质量标准

非 README 的 canonical node 页面至少应满足：

- `title`、`node_type`、`status`、`themes`、`source_pages`、`updated` 字段存在。
- `node_type` 只能是 `entity | concept | pattern | method | glossary | asset`。
- 正文有真实的一句话定义，而不是模板占位。
- `核心关系` 或 `相关页面` 至少包含一个有效 wikilink。
- `证据与来源` 指向实际来源页、证据 artifact 或原始资料。
- `当前结论` 写出可复用判断；如果证据不足，应明确写在 `未决问题`。
- 如果节点引用其他 shared node，frontmatter 的 `related_*` 字段应和正文 wikilink 保持一致。

不满足这些条件的 canonical node 只能算图谱占位，不应被 query 当成高置信知识。

## Engineering Outputs 规则

`outputs/` 是从 wiki 编译出的行动层，面向未来项目，尤其是软件开发工作。

推荐输出页：

- `engineering-brief.md`
  - 用于快速回答目标、边界、约束、工程影响、风险和来源。
- `implementation-guide.md`
  - 用于记录模块建议、接口边界、数据流、测试策略和落地步骤。
- `decision-brief.md`
  - 用于比较候选方案、权衡、推荐结论、反例和适用条件。
- `backlog.md`
  - 用于记录可执行项目机会、实验任务、原型建议和验收标准。
- `reuse-candidates.md`
  - 用于记录当前主题可输出或可匹配的技术资产候选。
- `asset-match-brief.md`
  - 用于把新项目需求点映射到历史项目或开源项目技术资产，并标注复用级别、适配成本、风险和验证任务。

维护规则：

1. outputs 必须链接回支撑它的 wiki 页面或 shared node。
2. outputs 中的建议要标注置信度，例如 `confirmed`、`inferred`、`tentative`。
3. outputs 不直接承载事实来源；事实来源仍是 raw source、evidence artifact 和 durable wiki。
4. 当 wiki 重要结论变化时，相关 outputs 应同步更新或明确标记为过期。
5. 如果 ingest 的材料对工程实践无影响，可以不更新 outputs，但应在报告中说明。

## 关系维护规则

当 ingest 或 query 触及某个高频对象时，应按以下顺序检查：

1. 这个对象是否已有 canonical page
2. 当前页面是否应补 wikilink
3. 是否需要把对象加入 `themes`
4. 是否需要更新 `related_*` 字段
5. 是否需要把新证据加入 `source_pages` 或 `evidence_from`
6. 是否出现 `supersedes` 或 `contradicts`

不要只在正文里提及对象而不更新它的关系字段。

## Theme Page 与 Entity Page 的分工

主题页负责：

- 当前主题的背景、上下文、结论和导航
- 主题内的优先级、当前状态、行动项

实体页负责：

- 对象的稳定定义
- 跨主题复用的关系图
- 与其他对象、主题、模式的连接

简单说：

- `README.md / overview.md` 是入口与上下文
- `shared/*/*.md` 是可复用知识节点

## Obsidian 友好链接规则

为了让 graph view 更可用，统一遵守以下规则：

1. 主题入口页必须链接到关键实体页和共享页。
2. 实体页必须至少链接回一个主题页。
3. 若一个术语已经有 canonical page，不再长期保留纯文本裸提及。
4. 使用带路径和显示名的 Obsidian wikilink，避免因为同名页面导致歧义。
5. 不依赖目录名推断关系，关系要写成显式链接。
6. 如果一个页面目前只有孤立内容，至少补 `相关页面` 一节。

## Query 使用规则

Query 需要按下面的顺序利用关系：

1. 先从 `index/themes.md`、`index/cross-theme-map.md` 与 `index/technical-assets.md` 识别候选主题和资产
2. 对复用类问题，先读 `shared/assets/`，再回到来源项目的 `reuse-assessment.md` 与 `outputs/reuse-candidates.md`
3. 再从主题页中的实体链接进入 `shared/` 或局部 `wiki/*/`
4. 使用 frontmatter 中的 `related_*`、`themes`、`source_pages` 继续扩展
5. 最后回到证据页和主题页做 grounded synthesis

换句话说，实体页是二级导航层，不替代主题入口。

## Ingest 使用规则

Ingest 在新资料入库时，至少应回答：

1. 这份资料涉及哪些高频对象？
2. 哪些对象只是当前主题局部概念？
3. 哪些对象应提升到 `shared/`？
4. 哪些现有实体页需要补关系字段？
5. 哪些主题页需要补对实体页的链接？
6. 是否形成可服务未来项目的技术资产候选，应该先进入 `outputs/reuse-candidates.md` 还是提升到 `shared/assets/`？

除此之外，还应回答：

7. 这份证据是否足以改变 durable knowledge，还是只适合保留为待验证信息？
8. 是否应优先修订已有页面，而不是创建平行新页？
9. 如果存在冲突，应在旧页中显式修订，还是先写入 `open-questions.md`？
10. 当前结论是否稳定到足以进入 `shared/`，还是仍应留在 theme 内？

## 最小落地标准

如果暂时不做全自动，至少做到：

- 每个高频概念有稳定命名
- 每个重要主题 README 能链接到关键概念页
- `shared/` 中有明确的实体层目录
- 实体页 frontmatter 能表达 `themes` 和 `related_*`
- `shared/assets/` 中的技术资产能表达来源项目、适用场景、复用级别、适配成本和证据链
- query 时优先沿实体关系补充阅读路径
