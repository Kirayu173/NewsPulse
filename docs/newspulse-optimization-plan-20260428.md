# NewsPulse 主流程优化方案

更新日期：2026-04-28

本文整理两个子 agent 对当前 `beb2749` 基线的只读分析结论，覆盖架构优化、死代码清理、代码质量提升和验证闭环。当前阶段明确暂停移动端 / 推送方向，主线优先打磨 NewsPulse 本机运行、报告质量、失败诊断和可维护性。

## 1. 当前判断

当前主流程已经从早期的 legacy report / ai 并行结构，收敛到以下链路：

```text
CLI
  -> NewsRunner
  -> RuntimeSettings / ApplicationRuntime
  -> RuntimeContainer
  -> workflow snapshot / selection / insight / report / render / delivery
```

现有 `workflow/*` 和 provider-native AI runtime 已经是正确方向，但仍有四类问题会拖慢后续迭代：

- `NewsRunner` 职责过重，主流程、副作用和诊断混在一起。
- 配置加载与归一化存在 `loader.py` / `runtime_config.py` 双轨。
- selection / insight 失败状态主要藏在自由格式 diagnostics 中，真实 E2E 排障成本高。
- 本地生成物、旧规划、兼容层和重复 review 工具让代码树噪音偏高。

## 2. 优化原则

- 不恢复 Expo、ntfy、移动端服务、移动端计划任务或推送实现。
- 不做大爆炸式重构；每个 tranche 都要能独立验证、独立回退。
- 优先修复会影响真实运行诊断能力的边界，再做文件拆分和清理。
- 配置、路径、运行时生命周期应有唯一权威入口。
- HTML / review artifact 是主流程质量的一等输出，不应只靠单元测试证明。

## 3. 优先级总览

| 优先级 | 事项 | 类型 | 推荐阶段 |
| --- | --- | --- | --- |
| P0 | 清理本地生成物和移动端残留产物 | 代码质量 | Tranche 0 |
| P0 | 处理 `subagent-*.md` 编码和归属 | 工作区治理 | Tranche 0 |
| P0 | 收窄 `NewsRunner`，抽出主流程 Orchestrator | 架构 | Tranche 2 |
| P0 | 统一配置归一化入口 | 架构 | Tranche 3 |
| P0 | selection 失败分类标准化 | 诊断 | Tranche 1 |
| P0 | insight 质量状态标准化 | 诊断 | Tranche 1 |
| P1 | 删除未直接使用依赖 `aiohttp`、`tenacity` | 依赖清理 | Tranche 0 |
| P1 | 集中解析 storage / output 路径 | 架构 | Tranche 3 |
| P1 | 建立可诊断 stage runner / `StageResult` | 架构 | Tranche 2 |
| P1 | 合并 review / outbox 导出实现 | 代码质量 | Tranche 2 |
| P1 | 拆分 `workflow/render/models.py` | 代码质量 | Tranche 4 |
| P1 | 增加 render 语义快照测试 | 测试 | Tranche 1 |
| P1 | 扩展 `doctor --live` / `smoke` | 运维诊断 | Tranche 5 |
| P1 | 固定主流程验证矩阵 | 测试治理 | Tranche 0 |
| P2 | 精简 superseded specs / 规划文档 | 文档治理 | Tranche 0 |
| P2 | 降低 legacy cleanup 负向测试维护成本 | 测试治理 | Tranche 4 |
| P2 | 梳理 `crawler.sources.builtin` 兼容出口 | API 清理 | Tranche 4 |
| P2 | 决定 `NewsData` / `NormalizedCrawlBatch` 双模型去留 | 数据模型 | Tranche 5 |
| P2 | 为 legacy config fallback 增加显式迁移策略 | 配置治理 | Tranche 3 |

## 4. 详细事项

### 4.1 清理本地生成物和移动端残留产物

- 优先级：P0
- 证据：工作区存在 `.venv/`、`.pytest_cache/`、`.ruff_cache/`、`__pycache__/`、`outbox/`、`output/`、`logs/`、`tmp_test_work/` 等生成物；移动端回退后仍有备份 patch 和历史 APK / log 类产物。
- 影响：搜索噪音大，容易误判当前主线；仓库体积膨胀；后续 agent 分析容易把移动端实验误判为当前需求。
- 推荐方案：只清理 ignored / untracked 生成物；保留 `.env`、明确要留的 `subagent-*.md`、必要 rollback patch。
- 风险或依赖：低风险，但需要先确认 `.gitignore` 当前改动是否保留。
- 验证：`git status --short --ignored` 前后对比；确认 `mobile/`、`newspulse/mobile/` 不存在。

### 4.2 处理 `subagent-*.md` 编码和归属

- 优先级：P0
- 证据：`subagent-architect.md`、`subagent-refactor.md` 是本地指令文件；终端读取有 mojibake 风险，且它们不属于当前主线业务代码。
- 影响：后续 agent 可能误读规则；也可能被误当成仓库权威文档。
- 推荐方案：如果继续使用，重建为 UTF-8 可读版本，并明确是否纳入版本控制；如果只作为本地私有指令，保持 ignored 并移到更明确的位置。
- 风险或依赖：不应自动删除，需要用户确认。
- 验证：`Get-Content` 可读；`git status --short` 符合预期。

### 4.3 收窄 `NewsRunner`，抽出主流程 Orchestrator

- 优先级：P0
- 证据：`newspulse/runner/news_runner.py` 同时处理配置加载、日志、环境检测、代理、storage 初始化、crawl、schedule、selection、insight、render、delivery 和浏览器打开。
- 影响：失败边界不清晰；runner 测试需要大量 mock；review-only、selection-only、insight-only 或真实 E2E 都要绕过副作用。
- 推荐方案：新增纯业务编排层，例如 `ApplicationWorkflow` / `NewsPulseOrchestrator`。输入 `ApplicationRuntime + WorkflowExecutionPlan`，输出结构化 `WorkflowRunResult`。`NewsRunner` 只保留 CLI/runtime 适配、crawl 调用和浏览器打开等副作用。
- 风险或依赖：会触动 `tests/test_runner_news_runner.py` 和端到端测试。
- 验证：先加 characterization tests 固定当前 stage 调用顺序；再拆分；最后跑 runner、workflow end-to-end、`pytest -q`。

### 4.4 统一配置归一化入口

- 优先级：P0
- 证据：`newspulse/core/loader.py` 已把 YAML 映射到大写运行时配置；`newspulse/core/runtime_config.py` 又做 normalize，并保留 legacy fallback。
- 影响：默认值来源不唯一；新增配置容易漏同步；问题定位要在 loader、normalizer、RuntimeSettings 三层之间跳。
- 推荐方案：`load_config()` 只负责读取 YAML / env / `.env` 和解析路径；schema、默认值、legacy 迁移集中到一个 typed normalizer。短期先覆盖 `workflow.selection`、`workflow.insight.summary/content`。
- 风险或依赖：不能直接破坏当前 `config/config.yaml`；需要兼容窗口或迁移提示。
- 验证：`tests/test_loader.py`、`tests/test_runtime_settings.py`、`tests/test_preflight.py`、`python -m newspulse doctor`。

### 4.5 selection 失败分类标准化

- 优先级：P0
- 证据：AI selection 已有 rule -> semantic -> LLM 链路；embedding 异常、LLM 缺项、fallback keyword 目前主要散落在 diagnostics 和日志中。
- 影响：结果质量下降时，用户难以判断是 embedding 跳过、LLM 部分失败，还是完全 fallback 到 keyword。
- 推荐方案：引入 selection error taxonomy，例如 `semantic_unavailable`、`semantic_failed_passthrough`、`llm_partial_missing_decisions`、`llm_failed_fallback_keyword`。review / audit artifact 汇总这些分类。
- 风险或依赖：需要同步 `selection/review.py`、`selection/audit.py`、相关 tests。
- 验证：构造 embedding fail、LLM partial fail、LLM total fail 的 targeted tests；检查 review outbox JSON。

### 4.6 insight 质量状态标准化

- 优先级：P0
- 证据：insight 主链路包括 input、fetch、reduce、item summary、report summary、aggregate；aggregate 失败会生成 fallback section。
- 影响：fallback 产物在 HTML 中可能看起来像正常洞察，降低报告可信度。
- 推荐方案：`InsightResult` 增加 `quality_status` 或 `generation_status`，区分 `ok`、`partial`、`fallback`、`error`、`skipped`。report validator、render、review 都保留该状态。
- 风险或依赖：会影响 `workflow/report/validator.py`、`workflow/render/models.py` 和 insight tests。
- 验证：覆盖正常洞察、summary partial、aggregate fallback、skipped、error 五类状态。

### 4.7 删除未直接使用依赖 `aiohttp`、`tenacity`

- 优先级：P1
- 证据：`rg "aiohttp|tenacity" newspulse tests` 没有业务导入，仅依赖文件中出现。
- 影响：安装体积和锁文件复杂度增加，也暗示历史 async / retry 设计残留。
- 推荐方案：从 `pyproject.toml`、`requirements.txt` 移除并重锁 `uv.lock`。
- 风险或依赖：需确认没有外部脚本依赖。
- 验证：`uv sync --frozen` 或重锁后的 sync、`ruff`、`pytest -q`、`newspulse doctor`。

### 4.8 集中解析 storage / output 路径

- 优先级：P1
- 证据：config / prompt / timeline 路径已集中在 `config_paths.py`，但 storage output 仍在 settings / render adapter 中局部 `Path(...)` 或默认 `output`。
- 影响：非默认 `CONFIG_PATH`、工作目录变化、review entrypoint 和 outbox 脚本可能解释相对路径不一致。
- 推荐方案：在 `RuntimePathSettings` 中显式持有 `project_root`、`config_root`、`config_path`、`data_dir` 的绝对解析结果；workflow 模块不再假定 `output` 或 `config/`。
- 风险或依赖：需明确相对 `data_dir` 是相对 project root 还是进程 cwd。
- 验证：增加不同 cwd、不同 config path 的 loader / render / storage 测试。

### 4.9 建立可诊断 stage runner / `StageResult`

- 优先级：P1
- 证据：`newspulse/runtime/workflow.py` 是函数式 helper，返回业务对象；失败、跳过、耗时、输入数量、输出数量散落在 diagnostics 中。
- 影响：真实 E2E 失败时只能靠日志拼接，难以统一回答是哪类失败。
- 推荐方案：定义内部 `StageResult[T]`，包含 `status`、`value`、`diagnostics`、`started_at`、`elapsed_ms`、`error_category`。先包 selection、insight、render，再纳入 crawl / delivery。
- 风险或依赖：会改变内部调用面，建议先内部引入，不马上暴露为公开 API。
- 验证：stage runner 单测；workflow end-to-end 保持输出一致。

### 4.10 合并 review / outbox 导出实现

- 优先级：P1
- 证据：`crawler/review.py`、`storage/review.py`、`snapshot/review.py`、`selection/review.py`、`insight/review.py` 都有各自的 `run_*_review` / `export_*_outbox`。
- 影响：summary、JSON、Markdown、log 字段容易漂移；每个 stage 重复维护临时目录和 artifact writer。
- 推荐方案：抽一个 review harness，统一 summary schema、log 捕获、storage temp dir、artifact writer；各 stage 只实现 stage-specific payload builder。
- 风险或依赖：review entrypoint 是真实 E2E 工具，不能只靠单元测试。
- 验证：`tests/test_review_entrypoints.py` 和各 `*_review.py` targeted tests；实际生成一次 outbox artifact。

### 4.11 拆分 `workflow/render/models.py`

- 优先级：P1
- 证据：该文件约 30KB，包含多个 dataclass、`build_render_view_model`、news card、summary、insight、metadata 映射等。
- 影响：render 层变成新的聚合大文件；HTML / notification 改动容易互相影响。
- 推荐方案：拆为 `view_models.py`、`view_model_builder.py`、`summary_mapper.py`、`insight_mapper.py`，保持 `render.__init__` 对外 API 不变。
- 风险或依赖：中等偏高，容易影响 HTML 和 notification 输出。
- 验证：`tests/test_workflow_render_service.py`、`tests/test_workflow_render_insight.py`、workflow end-to-end、HTML smoke。

### 4.12 增加 render 语义快照测试

- 优先级：P1
- 证据：render 已拆成 `html_page` / `html_components` / `html_formatters` / `html_assets`，但业务测试不一定覆盖 HTML 状态呈现和中文文案异常。
- 影响：HTML 结构回归、空内容、状态误呈现可能漏掉。
- 推荐方案：增加语义片段测试，覆盖正常 insight、fallback insight、skipped insight、空 selection、仅 summary cards、content fetch failed。
- 风险或依赖：不要锁死整页 HTML，避免测试脆弱。
- 验证：只断言关键 class、标题、状态文案和必要数据片段。

### 4.13 扩展 `doctor --live` / `smoke`

- 优先级：P1
- 证据：preflight 已检查 Python、配置、prompt、AI runtime、embedding、storage、output，但不做网络连通、provider 类型连通、crawl source 快速探测。
- 影响：`doctor` 通过后，真实运行仍可能在 crawl/provider 阶段失败。
- 推荐方案：新增 `newspulse doctor --live` 或 `newspulse smoke`，短超时探测 provider、crawl source、runtime import，并输出分类：`config_invalid`、`provider_auth_failed`、`provider_unreachable`、`crawl_source_unreachable`、`runtime_import_missing`。
- 风险或依赖：依赖网络和密钥，默认不应在普通 preflight 中开启。
- 验证：mock 网络分类单测；手动 live smoke。

### 4.14 固定主流程验证矩阵

- 优先级：P1
- 证据：已有 focused tests 和 `tests/test_workflow_end_to_end.py`，但缺少固定“每次重构该怎么验”的矩阵。
- 影响：重构时容易只跑局部测试，漏掉配置、render、review artifact 或 live smoke 的组合问题。
- 推荐方案：固定顺序：targeted stage tests -> `python -m ruff check newspulse tests` -> `python -m pytest -q` -> 本地 HTML smoke -> 可选 live smoke。
- 风险或依赖：live smoke 需要环境变量和网络，默认 skip。
- 验证：把该矩阵写入后续任务文档或 README 开发段落。

### 4.15 精简 superseded specs / 规划文档

- 优先级：P2
- 证据：`.kiro/specs/` 中有多个历史方向，如 mobile-reading-app、unified-ai-runtime-access、theme-summary-global-insight、lightweight-native-insight；部分内容仍提旧方向。
- 影响：规划源互相冲突，容易把已废弃方向带回主线。
- 推荐方案：保留当前权威 spec；旧 spec 移到 archive 并标注 superseded，或从工作区清除。
- 风险或依赖：需要确认是否还要保留历史记录。
- 验证：README / spec index 指向唯一当前方向。

### 4.16 降低 legacy cleanup 负向测试维护成本

- 优先级：P2
- 证据：`tests/test_legacy_cleanup.py` 大量断言旧模块不可导入，prompt / insight 测试也有多处旧词条 `assertNotIn`。
- 影响：短期防回归有效，长期会变成历史词条清单，影响测试可读性。
- 推荐方案：保留关键负向测试；把大量残留字符串检查迁到显式 cleanup audit 命令或脚本。
- 风险或依赖：低；删除前用 `rg` 确认旧路径确实不存在。
- 验证：`tests/test_legacy_cleanup.py` 仍覆盖关键旧入口；cleanup audit 可单独运行。

### 4.17 梳理 `crawler.sources.builtin` 兼容出口

- 优先级：P2
- 证据：`newspulse/crawler/sources/builtin.py` 使用 wildcard re-export source handlers；生产代码主要从 registry 解析，测试仍有从 builtin 导入。
- 影响：旧兼容出口扩大 API 面，source handlers 被整体暴露。
- 推荐方案：测试迁移到 `newspulse.crawler.sources.registry`；若无外部脚本依赖，删除或缩小 `builtin.py`。
- 风险或依赖：可能有用户脚本直接 import。
- 验证：`rg "crawler.sources.builtin|SOURCE_REGISTRY"`，迁移后跑 crawler/source tests。

### 4.18 决定 `NewsData` / `NormalizedCrawlBatch` 双模型去留

- 优先级：P2
- 证据：`storage/base.py` 仍有 legacy `NewsData` input 转换；`LocalStorageBackend.save_news_data` 和多个 tests/runtime 仍使用 `NewsData`。
- 影响：数据模型双轨增加 storage / snapshot 复杂度。
- 推荐方案：如果当前主线是 native crawl batch，逐步把测试和 runtime 写入迁到 `NormalizedCrawlBatch`；否则把 `NewsData` 明确标为 storage DTO，而不是 legacy 残留。
- 风险或依赖：较高，触及 storage、snapshot、end-to-end。
- 验证：storage stage tests、snapshot tests、workflow end-to-end、一次本地 HTML smoke。

### 4.19 为 legacy config fallback 增加显式迁移策略

- 优先级：P2
- 证据：旧代码模块已通过 `tests/test_legacy_cleanup.py` 防回归，但 `runtime_config.py` 仍保留 legacy config 读取。
- 影响：模块已经清理，配置层仍处于过渡态；当前权威 schema 不够明确。
- 推荐方案：定义 `config schema version` 或迁移层，只在 loader 中一次性升级旧配置，runtime 只看新 schema。
- 风险或依赖：仍使用旧配置的用户需要 doctor 警告和迁移提示。
- 验证：旧配置迁移测试、新配置直通测试、doctor warning 测试。

## 5. 推荐执行 Tranche

### Tranche 0：工作区和低风险清理

目标：降低噪音，建立后续重构前的干净基线。

- 确认 `.gitignore` 当前改动是否保留。
- 清理 ignored / untracked 生成物和移动端残留，保留 `.env` 与必要备份。
- 处理 `subagent-*.md` 编码和归属。
- 移除未使用依赖 `aiohttp`、`tenacity` 并重锁。
- 标记或归档 superseded specs。
- 固定验证矩阵。

验证：

```powershell
python -m ruff check newspulse tests
python -m pytest -q
python -m newspulse doctor
```

### Tranche 1：诊断和报告可信度

目标：让 selection / insight / render 的质量状态可见。

- selection error taxonomy。
- insight `quality_status` / `generation_status`。
- render 语义快照测试。
- review / audit artifact 显示失败分类和质量状态。

验证：

```powershell
python -m pytest tests/test_workflow_selection.py tests/test_workflow_selection_ai.py tests/test_runtime_insight.py tests/test_workflow_render_insight.py -q
python -m ruff check newspulse tests
python -m pytest -q
```

### Tranche 2：主流程边界收紧

目标：把主流程编排从 `NewsRunner` 中抽出来。

- 添加 characterization tests 固定当前 stage 调用顺序。
- 新增 `ApplicationWorkflow` / `NewsPulseOrchestrator`。
- 引入内部 `StageResult`。
- 合并 review / outbox harness 的公共部分。

验证：

```powershell
python -m pytest tests/test_runner_news_runner.py tests/test_workflow_end_to_end.py tests/test_review_entrypoints.py -q
python -m ruff check newspulse tests
python -m pytest -q
```

### Tranche 3：配置和路径治理

目标：让配置和路径只有一个权威解释入口。

- `load_config()` 变薄。
- typed normalizer 统一 schema / default / legacy migration。
- `RuntimePathSettings` 集中解析 project root、config path、data dir。
- legacy config fallback 改为显式迁移策略。

验证：

```powershell
python -m pytest tests/test_loader.py tests/test_runtime_settings.py tests/test_preflight.py -q
python -m newspulse doctor
python -m ruff check newspulse tests
python -m pytest -q
```

### Tranche 4：结构拆分和兼容出口收口

目标：降低维护成本，但不改变主流程行为。

- 拆分 `workflow/render/models.py`。
- 降低 legacy cleanup 负向测试维护成本。
- 梳理 `crawler.sources.builtin` 兼容出口。

验证：

```powershell
python -m pytest tests/test_workflow_render_service.py tests/test_workflow_render_insight.py tests/test_builtin_sources.py tests/test_legacy_cleanup.py -q
python -m ruff check newspulse tests
python -m pytest -q
```

### Tranche 5：高风险模型和 live smoke

目标：处理较大半径的数据模型和 live 诊断能力。

- 决定 `NewsData` / `NormalizedCrawlBatch` 双模型去留。
- 新增 `newspulse doctor --live` 或 `newspulse smoke`。
- 建立可选真实环境验证脚本。

验证：

```powershell
python -m pytest tests/test_storage_stage2.py tests/test_workflow_snapshot.py tests/test_workflow_end_to_end.py -q
python -m newspulse doctor
# 手动、有网络和密钥时再运行 live smoke
```

## 6. 不做事项

以下内容保持暂停，不进入本轮优化：

- Expo Android App。
- ntfy / Expo Push / 自建移动端推送。
- Windows 移动端计划任务。
- LAN mobile server。
- 从 `backup/mobile-push-wip-20260428` 或 rollback patch 整体恢复移动端实现。

## 7. 下一步建议

建议先执行 Tranche 0 和 Tranche 1。它们能快速降低仓库噪音，并让报告质量和失败诊断更可信。等诊断字段稳定后，再拆 `NewsRunner` 和配置层，否则重构后仍会缺少判断运行质量的统一信号。
