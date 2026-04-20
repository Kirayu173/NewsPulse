# Requirements Document

## Introduction

本方案用于把 GitHub Trending 当前“只有 repo 标题”的薄输入，升级为一套可复用的“源上下文结构化增强”能力。
目标不是只给 GitHub 打补丁，而是在 crawler -> storage -> snapshot -> selection 主链路中建立统一的 `summary + metadata` 契约，让 GitHub 先接入，其他源后续也能复用。

## Requirements

### Requirement 1

**User Story:** 作为 Selection 阶段的维护者，我希望所有热点源都能通过统一契约携带结构化上下文，这样后续语义召回和 LLM 质量闸门就不需要为单一数据源写特判逻辑。

#### Acceptance Criteria

1. WHEN crawler 产出热点条目 THEN 系统 SHALL 允许条目携带通用 `summary` 与 `metadata` 字段。
2. WHEN 不同 source 产出各自的补充上下文 THEN 系统 SHALL 通过统一字段承载，而不是新增 GitHub 专用主链路模型。
3. IF 某条新闻没有结构化增强信息 THEN 系统 SHALL 回退到仅使用标题的兼容模式，而不能中断主链路。

### Requirement 2

**User Story:** 作为存储与 snapshot 阶段的维护者，我希望增强上下文可以稳定落盘并投影到 workflow 契约中，这样 Selection、Render、Review 都能消费同一份数据。

#### Acceptance Criteria

1. WHEN `SourceItem` 携带 `summary` 与 `metadata` THEN 系统 SHALL 在归一化、存储、读取、snapshot 投影过程中完整保留这些字段。
2. WHEN 历史数据库没有增强字段 THEN 系统 SHALL 提供兼容迁移或默认值处理，而不是要求手工清库。
3. WHEN `HotlistItem` 进入 workflow THEN 系统 SHALL 保留与源上下文相关的可消费字段。

### Requirement 3

**User Story:** 作为 GitHub Trending 的使用者，我希望系统不仅抓到 `owner/repo`，还能够抓到仓库简介、语言、stars 和 topics 等信息，这样 Selection 可以更可靠地判断项目质量。

#### Acceptance Criteria

1. WHEN 抓取 GitHub Trending HTML 成功 THEN 系统 SHALL 提取至少 `full_name`、`description`、`language`、`stars_today`、`stars_total` 等字段。
2. WHEN GitHub API 可用 THEN 系统 SHALL 对榜单前 N 个仓库补充 `topics`、`created_at`、`pushed_at`、`archived`、`fork` 等结构化字段。
3. IF GitHub API 不可用或超时 THEN 系统 SHALL 回退到 HTML-only 结果，并继续输出可用的榜单数据。

### Requirement 4

**User Story:** 作为 Selection 阶段的维护者，我希望 semantic 与 LLM 都通过统一的 context builder 消费增强后的上下文，这样可以在不扩大逻辑分叉的前提下提升筛选质量。

#### Acceptance Criteria

1. WHEN semantic 层生成 embedding 文本 THEN 系统 SHALL 使用统一 context builder，而不再只拼接 `title + source`。
2. WHEN LLM 质量闸门生成 batch prompt THEN 系统 SHALL 使用统一 context builder 输出的精简上下文，而不是仅喂标题。
3. WHEN 其他 source 后续补充结构化字段 THEN 系统 SHALL 复用同一 builder 扩展逻辑，而不需要修改 semantic/LLM 主流程接口。

### Requirement 5

**User Story:** 作为项目维护者，我希望这次结构化改造对其他源具备明确的复用路径，这样后续 HN、Juejin、新闻热榜也能按同样方式增强。

#### Acceptance Criteria

1. WHERE source metadata 需要扩展 THEN 系统 SHALL 采用“通用层 + source 专有层”的规范化结构。
2. WHEN 新 source 接入结构化增强 THEN 系统 SHALL 只需要在 source 抓取器与 context builder 中增量接入，而不需要改写 workflow 主链路契约。
3. IF 某个 source 只提供少量上下文 THEN 系统 SHALL 允许部分字段为空，并继续参与统一筛选流程。

### Requirement 6

**User Story:** 作为审阅与回归测试的使用者，我希望 outbox 和测试能直观看到增强后的上下文，这样可以验证改造是否真正提升了输入质量。

#### Acceptance Criteria

1. WHEN 导出 stage4 review / audit 产物 THEN 系统 SHALL 在相关 JSON/Markdown 中展示 `summary` 与关键元信息摘要。
2. WHEN 新增或修改结构化增强逻辑 THEN 系统 SHALL 补充 crawler、storage、snapshot、selection、review 的回归测试。
3. WHEN GitHub Trending 结构增强完成 THEN 系统 SHALL 能通过一轮真实 stage4 outbox 展示前后输入质量差异。
