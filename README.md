# NewsPulse

面向本地运行场景的热点聚合与分析工具。

## 当前定位

NewsPulse 当前保留的核心能力：

- 热榜与 RSS 数据采集
- 关键词规则、调度与统计分析
- 本地 SQLite 存储
- HTML 报告生成
- 通用 Webhook 通知
- AI 筛选、AI 分析、AI 翻译

当前默认不包含的能力：

- Docker 部署资源
- 远程存储
- 专用通知渠道
- 外部 MCP 服务层
- 历史 `docs/` 文档目录

## 快速开始

建议使用 Python 3.12 及以上版本。

### 1. 安装依赖

使用 `uv`：

```bash
uv sync --frozen --no-dev
```

或使用 `pip`：

```bash
pip install -r requirements.txt
```

### 2. 修改配置

主要配置文件：

- `config/config.yaml`
- `config/frequency_words.txt`
- `config/timeline.yaml`

如启用 AI 能力，还需要关注：

- `config/ai_analysis_prompt.txt`
- `config/ai_translation_prompt.txt`
- `config/ai_interests.txt`
- `config/ai_filter/`

Config lookup rules:

- Default config root is the project-local `config/` directory.
- Relative `CONFIG_PATH` values are resolved from the project root.
- Relative prompt / keyword / interests files are resolved from the active config root.
- Parent directories are no longer searched for `.env`; export environment variables explicitly when needed.

### 3. 运行

```bash
python -m newspulse
```

## 常用命令

```bash
python -m newspulse
python -m newspulse --show-schedule
python -m newspulse --doctor
python -m newspulse --test-notification
```

说明：

- `--show-schedule`：查看当前调度解析结果
- `--doctor`：检查配置、AI、存储、通知和输出目录状态
- `--test-notification`：向当前配置的通用 Webhook 发送测试消息

## 目录概览

- `newspulse/`：主程序、采集、存储、报告、通知、AI 模块
- `config/`：运行配置、调度规则、AI prompt 与兴趣文件
- `tests/`：基础测试
- `PROJECT_MODULE_MAP.md`：模块拆分总览
- `module-*.md`：逐模块精简与改造决策记录

## 当前实现说明

### 采集

- 热榜抓取使用内建 Python source registry
- RSS 作为独立体系保留
- 主抓取流程不再依赖外部热榜 API

### 存储

- 当前仅保留本地存储
- 数据与报告默认输出到 `output/`

### 通知

- 当前仅保留通用 Webhook
- 适合对接 Discord、Matrix、IFTTT 或自建中转层

### AI

- 保留 AI 筛选
- 保留 AI 分析
- 保留 AI 翻译

## 模块决策记录

- `PROJECT_MODULE_MAP.md`
- `module-01-entry-orchestration.md`
- `module-02-config-rules-schedule.md`
- `module-03-crawler.md`
- `module-04-storage.md`
- `module-05-report-and-ui.md`
- `module-06-notification.md`
- `module-07-ai.md`
- `module-09-project-assets.md`

## 版本与更新

- 当前独立版本：`1.0.0`
- 默认不启用远程版本检查

## 许可证

项目保留根目录 `LICENSE` 文件，许可证文本以该文件为准。
