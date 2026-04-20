# Implementation Plan

说明：
- 本任务聚焦“源上下文结构化增强”，优先落 GitHub Trending，但所有主链路设计必须可被其他 source 复用。
- 实施顺序遵循：先契约和持久化，再 source 增强，再 selection 接入，最后做 outbox 与回归验证。
- 每个阶段完成后先补测试，再做真实 stage4 验证。

- [ ] 1. 打通通用 source context 契约
  - [ ] 1.1 扩展 crawler / storage / workflow 共享模型
    - 修改 `newspulse/crawler/sources/base.py`
    - 修改 `newspulse/storage/base.py`
    - 修改 `newspulse/workflow/shared/contracts.py`
    - 为 `SourceItem` / `NewsItem` / `HotlistItem` 增加 `summary`、`metadata`
    - 补齐 `to_dict()/from_dict()` 等序列化逻辑
  - [ ] 1.2 让 snapshot 主链路透传增强上下文
    - 修改 `normalize_crawl_batch()`
    - 修改 `newspulse/workflow/snapshot/projector.py`
    - 验证 current/daily/incremental 三种模式下字段不丢失
  - [ ] 1.3 为契约透传补单元测试
    - 新增或修改 storage / snapshot roundtrip 测试
    - 验证无 metadata 时仍能兼容运行

- [ ] 2. 为存储层增加 summary / metadata 持久化能力
  - [ ] 2.1 扩展 SQLite schema
    - 修改 `newspulse/storage/schema.sql`
    - 为 `news_items` 增加 `summary`、`source_metadata_json`
  - [ ] 2.2 修改 repository 读写逻辑
    - 修改 `newspulse/storage/repos/news.py`
    - 保存时写入新列，读取时还原 metadata JSON
    - 对坏数据或空值做默认回退
  - [ ] 2.3 补 schema / persistence 回归测试
    - 覆盖新列存在与历史库兼容场景

- [ ] 3. 抽取统一的 Selection Context Builder
  - [ ] 3.1 新建 `newspulse/workflow/selection/context_builder.py`
    - 定义 `SelectionContext`
    - 提供通用 `build_selection_context(item)`
  - [ ] 3.2 设计通用属性渲染规则
    - 默认规则：title + summary + source
    - source 专有规则：按 `source_kind` 扩展属性摘要
    - 保证 token 可控，避免 metadata 全量透传
  - [ ] 3.3 补 context builder 单元测试
    - 覆盖 GitHub 和 generic source 两类输入

- [ ] 4. 改造 GitHub Trending 为结构化 source
  - [ ] 4.1 增强 HTML 解析
    - 修改 `newspulse/crawler/sources/tech.py`
    - 提取 `full_name`、`description`、`language`、`stars_total`、`forks_total`、`stars_today`
    - 统一 `title` 为 `owner/repo`
    - 写入 `summary + metadata`
  - [ ] 4.2 增加 GitHub API enrich
    - 设计前 N 项 enrich 流程
    - 有 token 时补 `topics`、`created_at`、`pushed_at`、`archived`、`fork`
    - 无 token 或失败时降级为 HTML-only
  - [ ] 4.3 补 crawler 级测试
    - HTML-only
    - HTML + API enrich
    - HTML 失败 fallback 到 search API

- [ ] 5. 让 semantic 与 LLM 统一消费增强上下文
  - [ ] 5.1 改造 semantic 输入
    - 修改 `newspulse/workflow/selection/semantic.py`
    - 使用 `SelectionContext.embedding_text`
  - [ ] 5.2 改造 LLM batch 输入
    - 修改 `newspulse/workflow/selection/models.py`
    - 修改 `newspulse/workflow/selection/ai_classifier.py`
    - 使用 `SelectionContext.llm_text`
  - [ ] 5.3 补 selection 回归测试
    - 验证 prompt 中包含 summary / key attributes
    - 验证 GitHub 项目与 generic 项目判定差异

- [ ] 6. 扩展 review / audit / outbox 展示能力
  - [ ] 6.1 修改 `newspulse/workflow/selection/review.py`
    - 在 JSON 里输出 summary 和关键 metadata 摘要
  - [ ] 6.2 修改 `newspulse/workflow/selection/audit.py`
    - 在 markdown 审阅文档中展示结构化上下文样本
  - [ ] 6.3 补 review / audit 测试
    - 验证 stage4 产物中可以看到 GitHub 结构化字段

- [ ] 7. 做真实链路验证与审阅
  - [ ] 7.1 跑 selection 相关测试
    - crawler / storage / semantic / ai / review
  - [ ] 7.2 跑全量测试
    - 验证结构化增强没有破坏其他环节
  - [ ] 7.3 生成真实 stage4 outbox
    - 对比 GitHub Trending 条目在增强前后的可读性和可判定性
    - 记录是否需要继续微调 context builder 的属性输出

- [ ] 8. 为其他 source 复用预留扩展点
  - [ ] 8.1 定义 source metadata 命名空间规范
    - `metadata["github"]`
    - `metadata["hackernews"]`
    - `metadata["juejin"]`
  - [ ] 8.2 在 design / code comments 中明确扩展约定
    - 新 source 不允许改主链路契约
    - 只允许在 source 抓取器和 context builder 中增量接入
  - [ ] 8.3 为后续 HN / Juejin 扩展记录候选字段
    - HN：domain / post type / points / comments
    - Juejin：tag / column / author / series marker

## Exit Criteria

- GitHub Trending 条目不再只有 repo slug 可供 Selection 判断
- `summary + metadata` 已贯穿 crawler -> storage -> snapshot -> selection
- semantic 与 LLM 共用统一 context builder
- review/outbox 可见结构化增强后的输入
- 设计与实现路径对其他 source 可复用
