# Query Write-Back Rules

## When to read this file

Read this file when the answer may need to be saved back into the knowledge base.

## Write back only if

- the user explicitly asks to save the conclusion
- the answer resolves a recurring question
- the answer clarifies an important boundary, decision, pattern, constraint, glossary term, engineering recommendation, or failure mode
- the answer uncovers stale or contradictory knowledge
- the answer creates a useful project seed, implementation guide, or evaluation plan for future software work

## If writing back

- update existing pages first
- avoid creating a new page unless the topic is clearly durable and distinct
- add related links
- preserve uncertainty markers where needed
- record `answer_status` in the page when evidence is weak
- update `outputs/engineering-brief.md`, `outputs/implementation-guide.md`, `outputs/decision-brief.md`, or `outputs/backlog.md` when the answer is software-development guidance

## Durable Answer Policy

A query answer has durable value when it changes or clarifies one of these:

- A decision or trade-off.
- A module boundary, architecture constraint, test strategy, or release risk.
- A reusable pattern, method, checklist, or glossary term.
- A graph relationship between themes or canonical nodes.
- A source-backed conclusion, contradiction, or uncertainty.
- A future project seed, experiment, or acceptance signal.

When durable value exists but evidence is weak, write back a tentative note with an evidence gap instead of overstating the conclusion.

## Do not

- answer with fake confidence when the wiki is incomplete
- rely on outside knowledge as if it came from the wiki
- silently edit the wiki after a query unless the task clearly calls for it
- store software guidance only in chat when an output page is the durable home

## Report Fields

Every substantial query should expose these fields in the answer or activity log:

- `answer_status: confirmed | inferred | insufficient`
- `writeback_candidate: yes | no`
- `writeback_target: <existing page, proposed page, or none>`
- `graph_gap`, `output_gap`, or `evidence_gap` when relevant

## Common query patterns

Typical prompts include:
- “这个主题当前的关键结论是什么”
- “这个项目为什么这样设计”
- “我们以前怎么处理类似故障”
- “这个研究方向目前有哪些假设和证据”
- “有哪些跨主题都适用的模式”
