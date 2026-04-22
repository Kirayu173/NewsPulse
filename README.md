# NewsPulse

NewsPulse 是一个本地优先的热榜抓取与分析工具。它会抓取已配置的数据源，执行 Selection / Insight 主链路，并生成 HTML 报告与可选通知 payload。

## 快速开始

推荐运行环境：

- Python `3.12`
- 使用 `uv` 管理依赖
- 项目配置位于 `config/`
- 环境变量文件使用仓库根目录的 `.env`
- `.env` 请直接从仓库根目录的 `.env.example` 复制生成

### 1. 安装依赖

推荐方式：

```bash
uv sync --frozen --no-dev
```

备选方式：

```bash
pip install -r requirements.txt
```

### 2. 在标准位置创建 `.env`

推荐模板文件已经放在仓库根目录：

```powershell
Copy-Item .env.example .env
```

然后在 `.env` 中填写：

- `API_KEY`：LLM 服务的 API Key
- `BASE_URL`：OpenAI 兼容接口的 base URL
- `MODEL`：主聊天模型
- `EMB_MODEL`：语义召回使用的 embedding 模型

标准启动方式默认读取仓库根目录的 `.env`，不建议再自行放到别的位置。

### 3. 检查默认配置

启动前建议至少看一眼这些文件：

- `config/config.yaml`
- `config/timeline.yaml`
- `config/frequency_words.txt`
- `config/ai_interests.txt`
- `config/ai_filter/prompt.txt`
- `config/ai_analysis_prompt.txt`
- `config/ai_insight_item_prompt.txt`

配置解析规则：

- 默认配置根目录是 `config/`
- 相对路径的 prompt / keyword / interests 文件都从当前 config root 解析
- 运行时环境变量文件推荐固定放在仓库根目录 `.env`

### 4. 先跑一次环境检查

```bash
python -m newspulse --doctor
```

### 5. 按标准方式启动

```bash
python -m newspulse
```

这就是标准入口。

如果只是想先看调度结果，可以执行：

```bash
python -m newspulse --show-schedule
```

## 常用命令

```bash
python -m newspulse
python -m newspulse --show-schedule
python -m newspulse --doctor
python -m newspulse --test-notification
```

## 输出位置

- HTML 报告：`output/html/`
- 最新 HTML 快捷路径：`output/html/latest/`
- SQLite 数据：`output/news/`
- 审阅 / 验证产物：`outbox/`

## 目录说明

- `newspulse/`：主程序代码
- `config/`：项目配置与 prompt
- `tests/`：自动化测试
- `sources/`：源侧辅助文件

## 说明

- 当前项目重点是 hotlist 类数据源，不再是旧版以 RSS 为主的流程
- 语义召回依赖 `EMB_MODEL`，如果没配，semantic selection 无法工作
- 通知发送是可选能力，是否生效取决于 `config/config.yaml` 和对应环境变量配置

## 许可证

见 `LICENSE`
