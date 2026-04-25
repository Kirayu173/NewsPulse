# NewsPulse

NewsPulse 是一个本地优先的热点抓取与分析工具。它会抓取已配置的数据源，执行 Selection / Insight 主链路，并生成 HTML 报告与可选通知 payload。

## 快速开始

推荐运行环境：

- Python `3.12`
- 使用 `uv` 管理依赖
- 项目配置位于 `config/`
- 环境变量文件使用仓库根目录的 `.env`

### 1. 安装依赖

推荐方式：

```bash
uv sync --frozen --no-dev
```

备选方式：

```bash
pip install -r requirements.txt
```

### 2. 创建 `.env`

模板已放在仓库根目录：

```powershell
Copy-Item .env.example .env
```

至少补齐以下变量：

- `API_KEY`：LLM 服务 API Key
- `BASE_URL`：OpenAI 兼容接口地址
- `MODEL`：主模型
- `EMB_MODEL`：语义召回使用的 embedding 模型

### 3. 检查配置文件

启动前建议先确认这些文件存在并可用：

- `config/config.yaml`
- `config/timeline.yaml`（可选，缺失时会退回默认调度模板）
- `config/frequency_words.txt`
- `config/ai_interests.txt`
- `config/ai_filter/prompt.txt`
- `config/ai_filter/extract_prompt.txt`
- `config/ai_filter/update_tags_prompt.txt`
- `config/ai_analysis_prompt.txt`

### 4. 先跑环境检查

推荐先运行预检：

```bash
newspulse doctor
```

或：

```bash
python -m newspulse doctor
```

`doctor` 会检查 Python 版本、配置文件、调度解析、AI runtime、prompt 文件、通知配置、存储与输出目录，并在 `output/meta/doctor_report.json` 保存结果。

### 5. 正常启动

```bash
newspulse run
```

或：

```bash
python -m newspulse run
```

不传子命令时默认也会执行 `run`：

```bash
python -m newspulse
```

## 常用命令

```bash
newspulse run
newspulse doctor
newspulse status
newspulse test-notification
```

兼容旧入口：

```bash
python -m newspulse --doctor
python -m newspulse --show-schedule
python -m newspulse --test-notification
```

### 命令说明

- `run`：执行完整抓取、筛选、洞察、渲染与通知链路
- `doctor`：独立运行环境与配置检查
- `status`：显示当前调度解析结果
- `test-notification`：发送通知链路 smoke test

## HTML 报告

当前 HTML 报告支持以下交互：

- 标题 / 摘要 / 来源实时搜索
- 来源标签点击过滤
- Insight 区域展开 / 折叠
- 跟随系统偏好的暗色模式

即使浏览器禁用 JavaScript，页面依然可以直接阅读完整内容。

## 常见问题排查

### 1. `Config file` 检查失败

- 确认 `config/config.yaml` 存在
- 如果配置文件不在默认位置，设置 `CONFIG_PATH`

### 2. `AI selection runtime` / `AI insight runtime` 失败

- 检查 `.env` 中的 `API_KEY`、`BASE_URL`、`MODEL`
- 如果 selection / insight 使用独立模型，也检查对应 operation 配置

### 3. `Semantic embedding` 失败

- 检查 `.env` 中是否已配置 `EMB_MODEL`
- 确认当前 provider 的 embedding 能力和 API Key 可用

### 4. `AI selection prompts` / `AI insight prompts` 失败

- 检查 `config/ai_filter/*.txt`
- 检查 `config/ai_analysis_prompt.txt`

### 5. 调度解析失败

- 检查 `config/timeline.yaml`
- 重点确认 `preset`、`week_map`、`day_plans`、`periods` 与时间格式 `HH:MM`

### 6. 输出目录不可写

- 检查 `storage.local.data_dir`
- 确认当前用户对目标目录有写权限

## 输出位置

- HTML 报告：`output/html/`
- 最新 HTML 快捷路径：`output/html/latest/`
- 体检结果：`output/meta/doctor_report.json`
- SQLite 数据：`output/news/`
- 审阅 / 验证产物：`outbox/`

## 目录说明

- `newspulse/`：主程序代码
- `config/`：项目配置与 prompt
- `tests/`：自动化测试
- `docs/`：整改与重构文档

## 说明

- 当前项目重点是热点榜单类数据源，而不是旧版以 RSS 为主的流程
- 语义召回依赖 `EMB_MODEL`；未配置时，启用 semantic selection 会被预检阻止
- 通知发送是可选能力，是否生效取决于 `config/config.yaml` 与环境变量配置

## 许可证

见 `LICENSE`
