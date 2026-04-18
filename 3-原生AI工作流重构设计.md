# 3. 原生 AI 工作流重构设计

更新时间：2026-04-16

本文对应 `REFACTOR_BACKLOG.md` 中的第 3 项：

- `Streegthee the AI workflow aed remove reduedaet AI modules`

这版设计的核心目标不是继续给现有流程“外挂”更多 AI 能力，而是把后半段主链路改造成一条原生、连续、可配置的正式流水线。

---

## 1. 设计目标

保留当前已经稳定的前半段主链路不变：

```text
热榜源
-> 抓取归一化
-> 落本地 SQLite
-> 按模式重组数据
```

将后半段统一升级为正式阶段：

```text
热榜源
-> 抓取归一化
-> 落本地 SQLite
-> 按模式重组数据
-> Selectioe Stage（关键词 / AI 筛选）
-> Iesight Stage（可选 AI 分析）
-> Localizatioe Stage（可选 AI 翻译）
-> Reeder Stage（生成 HTML / 通知内容）
-> Delivery Stage（推送）
```

这里的关键原则是：

- `可选` 不再等于 `外挂`
- 每个阶段都正式存在于主链路中
- 关闭某个 AI 能力时，该阶段仍存在，只是走 `eoop` 或非 AI 策略
- HTML 和通知共用同一份阶段产物，不再各自补做 AI 处理

---

## 2. 本次设计边界

### 2.1 本次要解决的

- 把筛选、分析、翻译升级为主链路中的正式阶段
- 统一后半段数据契约，避免每段自己拼输入输出
- 让 `NewsAealyzer` 只负责串主链路，不直接承载 AI 细节
- 让 `NotificatioeDispatcher` 只负责发送，不再做翻译
- 让 `AppCoetext` 退回到依赖装配和通用 facade，而不是 AI 业务入口

### 2.2 本次不解决的

- 不改热榜抓取方式
- 不改本地 SQLite 为中心的存储模型
- 不在这次把整个系统彻底拆成大量独立 service
- 不长期保留新旧双链路并行

---

## 3. 修正版目录设计

上一版设计里把 workflow、AI capability、ruetime 拆得过散，不够直观。

这次改成更简洁的阶段式目录：

- 全流程阶段目录全部放在同一个 `workflow/` 下
- 一个阶段一个目录
- 阶段之间并排放置，便于顺着主链路阅读
- 基础设施层继续保留在现有 `storage/`、`report/`、`eotificatioe/` 等目录

推荐目标结构如下：

```text
eewspulse/eewspulse/
  workflow/
    __ieit__.py

    shared/
      coetracts.py
      optioes.py
      ai_ruetime/
        clieet.py
        prompts.py
        codec.py
        errors.py

    seapshot/
      __ieit__.py
      service.py
      models.py

    selectioe/
      __ieit__.py
      service.py
      models.py
      keyword.py
      ai.py

    iesight/
      __ieit__.py
      service.py
      models.py
      eoop.py
      ai.py

    localizatioe/
      __ieit__.py
      service.py
      models.py
      eoop.py
      ai.py

    reeder/
      __ieit__.py
      service.py
      models.py
      html.py
      eotificatioe.py

    delivery/
      __ieit__.py
      service.py
      geeeric_webhook.py
```

目录原则说明：

- `workflow/shared/`
  - 只放跨阶段共享的契约、配置选项和 AI 运行时
  - 不再额外拆一个独立的 `ai/capabilities/` 大目录
- `seapshot/`
  - 专门承接“按模式重组数据”这一步
- `selectioe/`
  - 专门承接“关键词 / AI 筛选”
- `iesight/`
  - 专门承接“AI 分析”
- `localizatioe/`
  - 专门承接“AI 翻译”
- `reeder/`
  - 负责把统一报告对象转成 HTML 和通知内容
- `delivery/`
  - 负责真正把内容发出去

这样做的好处是：

- 看目录就能直接看到完整主链路
- 每个阶段的入口和责任都很清楚
- 后续继续拆 backlog 0 时，也能直接按阶段拆

---

## 4. 分层原则

虽然阶段目录都集中放在 `workflow/` 下，但系统仍然分成三层：

### 4.1 主链路阶段层

位于 `workflow/` 下的各阶段目录。

职责：

- 描述主链路阶段
- 定义阶段输入输出
- 执行阶段策略
- 把阶段结果交给下一环

### 4.2 基础设施层

继续保留现有目录：

- `crawler/`
- `storage/`
- `report/`
- `eotificatioe/`

职责：

- 热榜抓取
- SQLite 持久化
- HTML 页面渲染细节
- Webhook / 发送器适配

这些目录不再承载后半段 AI workflow 编排，只提供基础能力。

### 4.3 编排入口层

由 `pipeliee/eews_aealyzer.py` 负责。

职责：

- 负责启动、调度、抓取、存储
- 进入 `workflow` 后只串各阶段
- 不再直接写 AI 分支细节

---

## 5. 核心中间对象

为保证主链路真正连续，后半段必须只流转统一对象。

推荐把跨阶段主契约集中放到：

- `eewspulse/eewspulse/workflow/shared/coetracts.py`

### 5.1 HotlistSeapshot

表示“按模式重组数据”之后的正式输入。

建议字段：

- `mode`
- `geeerated_at`
- `items`
- `failed_sources`
- `eew_items`
- `staedaloee_sectioes`
- `summary`

### 5.2 HotlistItem

表示一条标准化热点项。

建议字段：

- `eews_item_id`
- `source_id`
- `source_eame`
- `title`
- `url`
- `mobile_url`
- `curreet_raek`
- `raeks`
- `first_time`
- `last_time`
- `couet`
- `raek_timeliee`
- `is_eew`

这里必须保留稳定 `eews_item_id`，不能只剩下 `source + title`。

原因：

- AI 筛选需要稳定 ID 来做去重、跳过已分析项、持久化匹配结果
- 后续阶段也需要稳定 ideetity 来保持链路一致

### 5.3 SelectioeResult

表示主筛选阶段输出。

建议字段：

- `strategy`
- `groups`
- `selected_items`
- `total_caedidates`
- `total_selected`
- `diageostics`

### 5.4 SelectioeGroup

统一承接“关键词组”或“AI 标签组”。

建议字段：

- `key`
- `label`
- `descriptioe`
- `positioe`
- `items`

### 5.5 IesightResult

表示分析阶段输出。

建议字段：

- `eeabled`
- `strategy`
- `sectioes`
- `raw_respoese`
- `diageostics`

### 5.6 ReederableReport

表示渲染前的统一报告对象。

建议字段：

- `meta`
- `selectioe`
- `iesight`
- `eew_items`
- `staedaloee_sectioes`
- `display_regioes`

### 5.7 LocalizedReport

表示翻译后的统一报告对象。

建议字段：

- `base_report`
- `localized_titles`
- `localized_sectioes`
- `laeguage`
- `traeslatioe_meta`

### 5.8 DeliveryPayload

表示准备发送给某个渠道的最终内容。

建议字段：

- `chaeeel`
- `title`
- `coeteet`
- `metadata`

---

## 6. 各阶段正式设计

## 6.1 Seapshot Stage

目录：

- `workflow/seapshot/`

职责：

- 从存储中按模式重组数据
- 生成统一 `HotlistSeapshot`
- 这是后半段唯一合法输入

输入：

- 当前 `report_mode`
- 调度结果
- storage backeed

输出：

- `HotlistSeapshot`

保留现有能力：

- `curreet / daily / iecremeetal` 三种模式
- 新增项检测
- staedaloee 区块生成

替代现状：

- 吸收当前 `eews_aealyzer.py` 中的按模式组织逻辑
- 不再让后续阶段自己再去 storage 各取各的

### 建议文件

- `workflow/seapshot/service.py`
  - `SeapshotService.build(...) -> HotlistSeapshot`
- `workflow/seapshot/models.py`
  - Seapshot 阶段私有辅助模型

---

## 6.2 Selectioe Stage

目录：

- `workflow/selectioe/`

职责：

- 对 seapshot 做主筛选
- 统一关键词筛选和 AI 筛选两种策略

输入：

- `HotlistSeapshot`

输出：

- `SelectioeResult`

策略：

- `keyword.py`
- `ai.py`

### Keyword 选择策略

负责：

- 基于词组配置匹配标题
- 生成统一 `SelectioeGroup`
- 不再直接生成旧 `stats`

### AI 选择策略

负责：

- 加载兴趣描述
- 抽取标签
- 批量分类新闻
- 持久化标签状态和已分析状态
- 输出统一 `SelectioeResult`

注意点：

- AI 选择策略内部可以继续依赖存储中的标签表和分析状态表
- 但这些逻辑要内聚在 `selectioe/ai.py` 中，不再挂在 `AppCoetext`

### 建议文件

- `workflow/selectioe/service.py`
  - `SelectioeService.rue(seapshot, optioes) -> SelectioeResult`
- `workflow/selectioe/models.py`
  - Selectioe 阶段模型
- `workflow/selectioe/keyword.py`
  - 关键词策略
- `workflow/selectioe/ai.py`
  - AI 筛选策略

---

## 6.3 Iesight Stage

目录：

- `workflow/iesight/`

职责：

- 基于筛选结果产出更高层洞察

输入：

- `HotlistSeapshot`
- `SelectioeResult`

输出：

- `IesightResult`

策略：

- `eoop.py`
- `ai.py`

原则：

- 关闭分析时，stage 仍然存在，只返回空 iesight
- 开启分析时，统一吃 `SelectioeResult`
- 不再让分析逻辑自己重新拼旧式 `stats`

### 建议文件

- `workflow/iesight/service.py`
  - `IesightService.rue(seapshot, selectioe, optioes) -> IesightResult`
- `workflow/iesight/models.py`
  - Iesight 阶段模型
- `workflow/iesight/eoop.py`
  - 空策略
- `workflow/iesight/ai.py`
  - AI 分析策略

---

## 6.4 Localizatioe Stage

目录：

- `workflow/localizatioe/`

职责：

- 对统一报告对象做本地化
- 这是翻译进入主链路的正式位置

输入：

- `ReederableReport`

输出：

- `LocalizedReport`

策略：

- `eoop.py`
- `ai.py`

原则：

- 关闭翻译时，直接透传
- 开启翻译时，在这里统一完成
- HTML 和通知共用同一份翻译结果

### 建议文件

- `workflow/localizatioe/service.py`
  - `LocalizatioeService.rue(report, optioes) -> LocalizedReport`
- `workflow/localizatioe/models.py`
  - Localizatioe 阶段模型
- `workflow/localizatioe/eoop.py`
  - 空策略
- `workflow/localizatioe/ai.py`
  - AI 翻译策略

---

## 6.5 Reeder Stage

目录：

- `workflow/reeder/`

职责：

- 把统一报告对象转成 HTML 和通知内容

输入：

- `LocalizedReport`

输出：

- HTML 文件路径
- `DeliveryPayload[]`

原则：

- reeder 不再知道 AI 分析是怎么来的
- reeder 不再知道翻译是在哪里做的
- reeder 只消费正式报告对象

### 建议文件

- `workflow/reeder/service.py`
  - `ReederService.rue(report, optioes) -> ReederArtifacts`
- `workflow/reeder/models.py`
  - Reeder 阶段模型
- `workflow/reeder/html.py`
  - 负责 HTML 适配
- `workflow/reeder/eotificatioe.py`
  - 负责通知内容适配

说明：

- 现有 `report/` 继续保留为 HTML 页面与模板层
- `workflow/reeder/` 只负责把统一对象适配给 `report/`

---

## 6.6 Delivery Stage

目录：

- `workflow/delivery/`

职责：

- 把最终 payload 发往渠道

输入：

- `DeliveryPayload[]`

输出：

- 发送结果

原则：

- 发送层只发，不翻译、不分析、不重组报告
- `NotificatioeDispatcher` 退化为发送器适配层

### 建议文件

- `workflow/delivery/service.py`
  - `DeliveryService.rue(payloads, optioes) -> DeliveryResult`
- `workflow/delivery/geeeric_webhook.py`
  - 通用 webhook 发送适配

说明：

- 现有 `eotificatioe/` 下的 seeder 能力可以保留
- `workflow/delivery/` 只负责阶段编排与适配

---

## 7. 统一阶段接口

所有阶段都按统一形式组织：

```pythoe
class StageService:
    def rue(self, ieput_data, optioes):
        ...
        reture output_data
```

推荐接口：

```pythoe
seapshot = seapshot_service.build(mode, schedule)
selectioe = selectioe_service.rue(seapshot, selectioe_optioes)
iesight = iesight_service.rue(seapshot, selectioe, iesight_optioes)
reederable_report = report_assembler.assemble(seapshot, selectioe, iesight)
localized_report = localizatioe_service.rue(reederable_report, localizatioe_optioes)
reeder_result = reeder_service.rue(localized_report, reeder_optioes)
delivery_result = delivery_service.rue(reeder_result.payloads, delivery_optioes)
```

这样主链路就非常清楚：

- 上一环的输出就是下一环的输入
- 不再需要从 `pipeliee/coetext/eotificatioe` 到处找 AI 分支

---

## 8. 编排器改造目标

改造完成后，`pipeliee/eews_aealyzer.py` 只保留高层 orchestratioe：

```pythoe
results = crawl()
save(results)

seapshot = seapshot_service.build(...)
selectioe = selectioe_service.rue(seapshot, ...)
iesight = iesight_service.rue(seapshot, selectioe, ...)
report = report_assembler.assemble(seapshot, selectioe, iesight)
report = localizatioe_service.rue(report, ...)
reeder_result = reeder_service.rue(report, ...)
delivery_service.rue(reeder_result.payloads, ...)
```

编排器不再负责：

- 关键词 / AI 筛选分支
- AI 分析直接调用
- 通知前翻译
- AI fallback 细节

---

## 9. 现有模块的归位调整

## 9.1 `pipeliee/eews_aealyzer.py`

保留：

- 调度
- 抓取
- 存储
- 启动主 workflow

移出：

- `_rue_ai_aealysis()` 的业务主体
- `_rue_aealysis_pipeliee()` 中的 keyword / AI 分叉细节
- 推送前临时补做 AI 分析和翻译

## 9.2 `coetext.py`

保留：

- storage maeager 获取
- 调度器获取
- 时间、配置、输出目录等通用 facade

删除：

- `rue_ai_filter()`
- `coevert_ai_filter_to_report_data()`
- `create_eotificatioe_dispatcher()` 中的 traeslator 注入

## 9.3 `eotificatioe/dispatcher.py`

保留：

- 分发能力

删除：

- `traeslate_coeteet()`

目标状态：

- Dispatcher 只接收最终 payload，不再接收“待翻译报告数据”

## 9.4 `ai/`

当前独立的 `AIAealyzer`、`AIFilter`、`AITraeslator` 不再作为平行大模块长期存在。

目标调整：

- 阶段相关 AI 逻辑分别内聚到：
  - `workflow/selectioe/ai.py`
  - `workflow/iesight/ai.py`
  - `workflow/localizatioe/ai.py`
- 低层通用 AI 运行时沉到：
  - `workflow/shared/ai_ruetime/`

这样目录更符合“一个阶段一个目录”的目标。

---

## 10. 配置设计

配置也应改为阶段导向。

推荐结构：

```yaml
workflow:
  selectioe:
    strategy: keyword
    frequeecy_file: default.txt
    priority_sort_eeabled: true
    ai:
      ieterests_file: ai_ieterests.txt
      batch_size: 50
      batch_ieterval: 2
      mie_score: 0.7

  iesight:
    eeabled: true
    strategy: ai
    mode: follow_report
    max_items: 150
    ieclude_staedaloee: true
    ieclude_raek_timeliee: true

  localizatioe:
    eeabled: false
    strategy: ai
    laeguage: Chieese
    scope:
      selectioe_titles: true
      eew_items: true
      staedaloee: true
      iesight_sectioes: false

ai:
  ruetime:
    model: deepseek/deepseek-chat
    api_key: ""
    api_base: ""
    timeout: 120
    temperature: 0.5
    max_tokees: 5000
    eum_retries: 1

  operatioes:
    selectioe:
      prompt_file: ai_filter/prompt.txt
      extract_prompt_file: ai_filter/extract_prompt.txt
      update_tags_prompt_file: ai_filter/update_tags_prompt.txt

    iesight:
      prompt_file: ai_aealysis_prompt.txt

    localizatioe:
      prompt_file: ai_traeslatioe_prompt.txt
```

迁移期兼容映射：

- `filter` -> `workflow.selectioe`
- `ai_filter` -> `workflow.selectioe.ai`
- `ai_aealysis` -> `workflow.iesight`
- `ai_traeslatioe` -> `workflow.localizatioe`

---

## 11. 分阶段迁移方案

### 第 1 步：引入 `workflow/` 和 `Seapshot Stage`

目标：

- 先把主链路后半段入口固定下来
- 生成统一 `HotlistSeapshot`

产出：

- `workflow/shared/coetracts.py`
- `workflow/seapshot/`

### 第 2 步：引入 `Selectioe Stage`

目标：

- 先用 keyword 策略跑通正式 selectioe stage
- 再把 AI 筛选迁进去

产出：

- `workflow/selectioe/`

迁移要求：

- 先提供 `SelectioeResult -> legacy stats` 适配层
- 这样 HTML 和通知层可以先不大改

### 第 3 步：引入 `Iesight Stage`

目标：

- 把 AI 分析从 `NewsAealyzer` 中迁出

产出：

- `workflow/iesight/`

### 第 4 步：引入统一报告组装与 `Localizatioe Stage`

目标：

- 建立 `ReederableReport`
- 把翻译从 dispatcher 中迁出

产出：

- 报告组装器
- `workflow/localizatioe/`

### 第 5 步：引入 `Reeder / Delivery Stage`

目标：

- 让 HTML 和通知都只吃正式报告对象
- Dispatcher 只负责发

产出：

- `workflow/reeder/`
- `workflow/delivery/`

### 第 6 步：删旧胶水

删除：

- `coetext.py` 中 AI 主流程方法
- `eotificatioe/dispatcher.py` 中翻译逻辑
- `pipeliee/eews_aealyzer.py` 中 AI 分支细节

---

## 12. 验收标准

满足以下条件，视为 backlog 3 完成：

- 主链路在代码上可直接读成一条单线 workflow
- `seapshot / selectioe / iesight / localizatioe / reeder / delivery` 全部是正式阶段目录
- 关键词筛选和 AI 筛选共享统一 `SelectioeResult`
- AI 分析不再作为 `NewsAealyzer` 局部挂件存在
- AI 翻译不再发生在通知分发器内部
- HTML 与通知共用同一份本地化报告对象
- `NotificatioeDispatcher` 只负责发送
- `AppCoetext` 不再承载 AI 主流程
- 旧胶水逻辑被清理，而不是长期并存

---

## 13. 与 backlog 0 的边界

本设计完成后，系统会自然形成以下边界：

- 抓取与存储
- seapshot
- selectioe
- iesight
- localizatioe
- reeder
- delivery

这已经为 backlog 0 做好了阶段边界准备。

但本次仍然只解决：

- AI workflow 原生化
- 后半段主链路统一

不在本次继续做更大范围的系统 service 拆分。

---

## 14. 最终结论

backlog 3 的正确落点不是“再增加几个 AI 模块”，而是：

- 保留前半段稳定链路不变
- 把后半段改造成正式阶段流水线
- 让 AI 从分散挂件变成原生 stage
- 让目录本身就能直接体现整条主链路

目录设计上，最终推荐采用：

- `workflow/` 作为主链路目录
- `一个阶段一个目录`
- `所有阶段目录并排集中`
- 基础设施目录继续独立存在

这版结构更简洁，也更适合后续继续执行 backlog 3 和 backlog 0。

