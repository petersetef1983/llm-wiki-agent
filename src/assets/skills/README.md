# Skills Guide

这份文档给出 `ingest`、`synthesize`、`query`、`lint`、`reset`、`bootstrap` 六个核心技能，以及 `project-reverse` 辅助分析器的：
- 触发判断规则
- 典型用户表达
- 标准提示词模板
- 推荐组合方式

在日常使用中，优先按“任务意图”选择技能，而不是按文件位置选择。

## 目录结构

当前 skill 树以 `.agents/skills/` 为唯一可编辑源，并镜像到各平台运行目录，供 Codex、Claude、Trae、OpenCode、OpenClaw、Hermes 在进入 `kb/` 后自动加载。以下以 `.agents/skills/` 作为规范示例路径：

```text
.agents/skills/
├── ingest/
│   ├── SKILL.md
│   ├── evals/
│   ├── references/
│   └── scripts/
├── project-reverse/
│   ├── SKILL.md
│   ├── references/
│   └── scripts/
├── synthesize/
│   ├── SKILL.md
│   ├── references/
│   └── scripts/
├── query/
│   ├── SKILL.md
│   ├── evals/
│   └── references/
├── lint/
    ├── SKILL.md
    ├── evals/
    ├── references/
    └── scripts/
└── reset/
    ├── SKILL.md
    ├── agents/
    └── scripts/
└── bootstrap/
    ├── SKILL.md
    ├── agents/
    ├── assets/
    └── scripts/
```

- `SKILL.md`：技能入口、触发说明、最短工作流和 references 导航
- `evals/`：测试提示与 triggering 样例，便于后续验证 skill 效果与 description 命中率
- `references/`：按需读取的详细说明，承载长工作流、输出规则、命令清单等
- `scripts/`：该技能绑定的确定性脚本

说明：
- 知识库整体规约由 `AGENTS.md` 提供；进入知识库目录后应默认继承，无需在每个 skill 内重复显式指定调用路径
- `.agents/skills/` 是唯一可编辑源；平台目录中的 `skills/` 是自动同步镜像
- 所有工具脚本按运行时顺序执行：优先 `KB_PYTHON`，其次 `python`、`py -3`、`python3`，仅在没有更简单解释器时才回退到 `conda run -n llm-wiki python`
- 修改 `.agents/skills/` 后，运行 `<PYTHON_CMD> tools/sync_agent_skills.py`
- 提交前可运行 `<PYTHON_CMD> tools/sync_agent_skills.py --check` 校验镜像是否漂移
- 不要手工修改平台 `skills/` 镜像，否则下次同步会被覆盖

## 一、如何判断触发哪个技能

### `ingest`

适合处理“新资料进入知识库”的任务。

典型触发词：
- 导入
- 整理进知识库
- 吸收资料
- 处理 inbox
- 根据资料更新 wiki
- 沉淀
- 归档并更新主题
- ingest GitHub/GitLab/local Git repo

适用问题：
- 新增了原始资料，想放入正确主题
- 想把文章、会议纪要、故障记录整理成 wiki
- 想让 LLM 根据新资料更新已有主题页面
- 想把开源或自建 Git 项目逆向分析后沉淀进 `project` 主题；此时先调用 `project-reverse` 生成证据，再由 `ingest` 编译 wiki
- 想把需求文档结构化为目标项目的 `outputs/requirement-analysis.md`

### `synthesize`

适合处理“新需求如何复用历史项目和开源项目资产”的任务。它从已 ingest 的 `requirement-analysis.md` 出发，先运行确定性 `match-assets/check-license/assess-reuse/generate-outputs` 流水线，再生成目标项目侧的工程输出。

典型触发词：
- 综合历史项目
- 复用开源项目
- 生成实施方案
- asset-match
- implementation guide
- decision brief

适用问题：
- 需要把新项目需求和历史 `reuse-candidates.md`、`shared/assets/`、开源 evidence 做匹配
- 需要生成 `asset-match-brief.md`、`engineering-brief.md`、`implementation-guide.md`、`decision-brief.md`
- 需要明确复用方式、复用成本、许可证/耦合/漏洞风险、验证任务和证据链接

### `project-reverse`

适合处理“Git 项目源码逆向分析证据生成”的辅助任务。它不是独立入库模式，而是 `ingest` 的分析器。

典型触发词：
- GitHub 项目逆向
- GitLab 项目分析
- API 参数和源码位置
- 模块依赖
- 构建部署
- freshness / commit diff

适用问题：
- 需要从源码提取架构、模块、API、配置、部署、数据存储、风险、复用评估
- 需要为 `ingest` 生成 `outputs/document-intake/project-reverse-analysis.json`
- 需要检查已摄取项目是否落后于远端 commit
- 需要生成 `old_commit..new_commit` 的增量变更证据

### `query`

适合处理“从现有知识库中回答问题”的任务。

典型触发词：
- 这个主题是什么
- 为什么这样设计
- 当前重点是什么
- 总结一下
- 对比一下
- 以前怎么做
- 帮我回答

适用问题：
- 想从已有 wiki 得到 grounded answer
- 想做跨主题总结
- 想基于现有沉淀快速理解项目或研究方向

### `lint`

适合处理“知识库质量检查”的任务。

典型触发词：
- 检查
- 体检
- 审查结构
- 找死链
- 看看缺了什么
- 找重复页面
- 补齐入口页

适用问题：
- 想知道知识库结构是否健康
- 想在大规模 ingest 前先做检查
- 想在长期积累后做一次质量巡检

### `reset`

适合处理“清空整个知识库，只保留基本骨架”的任务。这是破坏性维护模式。

典型触发词：
- 重置知识库
- 清空所有 wiki 和日志
- 只保留骨架
- 恢复为空白模板
- 重新开始

适用问题：
- 想删除所有具体主题、shared 节点、index 历史、inbox 内容和 `log.md`
- 想保留 `AGENTS.md`、`schema/`、`tools/`、agent skills、三类 theme 容器、shared 基础目录和 index 空入口
- 想先 dry-run 查看清理计划，再确认执行

### `bootstrap`

适合处理“在空目录中创建完整 LLM Wiki 骨架”的任务。这是创建模式，不用于清空已有知识库。

典型触发词：
- 初始化知识库
- 创建 skeleton
- bootstrap 空目录
- 新建 LLM Wiki
- 把空目录变成知识库

适用问题：
- 想在真正空目录中创建 `AGENTS.md`、`schema/`、`tools/`、skills、themes、shared、index、inbox
- 想在只包含安全平台运行时目录的等效空目录中创建知识库
- 想先 dry-run 查看创建计划，再确认执行

## 二、标准提示词

下面这些提示词可以直接复制给 Trae / Claude / Codex / OpenCode / OpenClaw / Hermes。

### 1. `ingest` 标准提示词

```text
请使用 `ingest` 技能处理这次知识库更新。

任务目标：
- 将新的原始资料归类到正确的主题或 `shared/`
- 优先更新已有 wiki 页面，而不是重复创建新页面
- 保留来源信息
- 标记不确定内容

执行要求：
1. 默认遵循知识库总体规约
2. 如主题不明确，先运行或模拟 `python .agents/skills/ingest/scripts/kb_ingest_helper.py inventory --root .`
3. 判断资料属于哪个主题、是否应进入 `shared/`，或是否应暂存到 `inbox/to-be-filed/`
4. 更新相关的 `README.md`、`meta.md`、`wiki/overview.md` 及必要的主题页面
5. 如果这次 ingest 有明确价值，请更新 `index/recent-updates.md`

输出请包含：
- 处理了哪些资料
- 放到了哪里
- 更新了哪些页面
- 哪些结论是高置信度
- 哪些内容仍待确认
```

### 2. `query` 标准提示词

```text
请使用 `query` 技能回答这个知识库问题。

任务目标：
- 从现有知识库中给出 grounded answer
- 区分已确认结论、合理推断和证据缺口
- 如有必要，建议把答案回写为 durable knowledge

执行要求：
1. 默认遵循知识库总体规约
2. 先从 `index/themes.md` 和 `index/cross-theme-map.md` 判断相关主题
3. 再读取对应主题的 `README.md`、`meta.md`、`wiki/overview.md`
4. 只读取回答问题所需的最小页面集合
5. 如果知识库证据不足，请明确说明

输出请包含：
- 简短回答
- 支撑依据
- 不确定点或缺失信息
- 如果适合沉淀，建议更新哪些 wiki 页面
```

### 3. `lint` 标准提示词

```text
请使用 `lint` 技能检查这个知识库的结构和内容质量。

任务目标：
- 发现结构问题、缺失文件、死链、占位符、索引遗漏和主题完整度问题
- 区分高优先级问题和一般维护建议
- 如用户允许，只修复低风险问题

执行要求：
1. 默认遵循知识库总体规约
2. 运行或模拟 `python .agents/skills/lint/scripts/kb_lint.py --root .`
3. 按 `error / warning / info` 归类问题
4. 先指出最影响可导航性和可维护性的问题
5. 如果用户要求修复，只处理低风险项

输出请包含：
- 问题统计
- 最重要的问题列表
- 哪些可以自动修复
- 哪些需要人工判断
```

### 4. `reset` 标准提示词

```text
请使用 `reset` 技能重置这个知识库。

任务目标：
- 清空所有具体主题、wiki 内容、sources、outputs、shared canonical pages、inbox 内容、index 历史和 `log.md`
- 保留知识库基本骨架、schema、tools、AGENTS 规约和 agent skills
- 先 dry-run，确认后再执行

执行要求：
1. 默认遵循知识库总体规约
2. 先运行 `python .agents/skills/reset/scripts/kb_reset.py --root . --dry-run`
3. 向用户说明将删除和保留的内容
4. 只有用户明确确认后，才运行 `python .agents/skills/reset/scripts/kb_reset.py --root . --confirm RESET-KB`
5. 如果 `.agents/skills/` 有改动，运行 `python tools/sync_agent_skills.py` 和 `python tools/sync_agent_skills.py --check`

输出请包含：
- dry-run 计划摘要
- 是否已经执行
- 重置后保留的骨架
- 后续应该如何重新开始 ingest
```

### 5. `bootstrap` 标准提示词

```text
请使用 `bootstrap` 技能在目标空目录中创建一个新的 LLM Wiki。

任务目标：
- 创建完整可运行的知识库 skeleton
- 允许目标目录为空，或只包含安全的平台运行时目录
- 拒绝已有 KB root、普通文件、业务目录或未知 runtime 内容
- 先 dry-run，确认后再执行

执行要求：
1. 默认遵循知识库总体规约
2. 先运行 `python .agents/skills/bootstrap/scripts/kb_bootstrap.py --root <target-dir> --dry-run`
3. 向用户说明将创建的内容和忽略的 runtime 目录
4. 只有用户明确确认后，才运行 `python .agents/skills/bootstrap/scripts/kb_bootstrap.py --root <target-dir> --confirm CREATE-KB`
5. 创建后在新 KB 中运行 `python tools/sync_agent_skills.py --check`

输出请包含：
- dry-run 计划摘要
- 是否已经执行
- 新 KB 的入口文件和目录
- 验证结果
```

## 三、触发示例

### 示例 1：应触发 `ingest`

用户说：

```text
把 `inbox/to-be-filed/` 里的会议纪要和事故记录整理进 project-example 主题，并更新相关 wiki 页面。
```

原因：
- 任务核心是把新资料编译进知识库

### 示例 2：应触发 `query`

用户说：

```text
请基于知识库说明一下 project-example 当前最关键的架构约束，以及这些约束分别来自哪里。
```

原因：
- 任务核心是从现有沉淀中回答问题

### 示例 3：应触发 `lint`

用户说：

```text
帮我检查一下知识库现在有哪些主题缺入口页、有哪些死链、哪些页面还是占位符。
```

原因：
- 任务核心是做结构和质量检查

### 示例 4：应触发 `reset`

用户说：

```text
请重置整个知识库，清空所有 wiki 和日志，只保留基础骨架。
```

原因：
- 任务核心是破坏性地清空现有知识内容并恢复空白结构

### 示例 5：应触发 `bootstrap`

用户说：

```text
请在这个空目录里创建完整的 LLM Wiki skeleton。
```

原因：
- 任务核心是在空目录中初始化新知识库，而不是清空已有知识库

### 示例 6：组合任务，应先 `ingest` 再 `query`

用户说：

```text
先把这份新的技术方案整理到 research-example，再总结一下它对当前研究结论的影响。
```

推荐顺序：
1. `ingest`
2. `query`

### 示例 7：组合任务，应先 `lint` 再 `ingest`

用户说：

```text
我准备把一批旧笔记导入知识库，先帮我检查一下结构问题，再开始整理。
```

推荐顺序：
1. `lint`
2. `ingest`

## 四、推荐组合模式

### 日常新增资料

用 `ingest`

```text
请使用 `ingest` 技能，把今天新增的资料整理到对应主题，并更新必要的 wiki 页面。
```

### 日常问答

用 `query`

```text
请使用 `query` 技能，基于知识库回答这个问题，并指出哪些结论仍缺证据。
```

### 每周体检

用 `lint`

```text
请使用 `lint` 技能，对知识库做一次巡检，并按严重程度列出问题。
```

### 大批量导入后的收尾

先 `ingest`，后 `lint`

```text
先使用 `ingest` 技能完成这批资料的整理，再使用 `lint` 技能检查新增内容是否引入结构问题。
```

### 重新开始知识库

用 `reset`

```text
请使用 `reset` 技能，先 dry-run 展示重置计划；我确认后再清空知识库内容并保留基础骨架。
```

### 新建知识库

用 `bootstrap`

```text
请使用 `bootstrap` 技能，在目标空目录中先 dry-run 展示创建计划；我确认后再创建完整 LLM Wiki skeleton。
```
