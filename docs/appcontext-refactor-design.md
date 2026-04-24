# AppContext 重构设计方案

## 1. 背景与目标

当前 `newspulse/context.py` 已经从早期的大杂烩里抽出了一部分结构，但它仍然同时承担了四类职责：

1. 配置归一化后的读取入口。
2. 运行时单例（storage / scheduler / service factory）的生命周期管理。
3. 各 Stage 的 options 组装。
4. 对外的“万能门面”，通过 `__getattr__` 向调用方暴露大量隐式能力。

这让 `AppContext` 继续处于“过度中心化”的状态：

- `NewsRunner`、CLI、review entrypoint、preflight 都直接依赖它。
- 测试会直接写 `_storage_manager` / `_scheduler` 等私有字段。
- 配置访问是“属性名约定 + 动态透传”，缺少显式边界。
- 运行时对象创建与配置解释混在一起，不利于后续按模块演进。

本次方案目标不是马上大改，而是给出一个可分阶段落地、风险可控的重构路径，让后续功能开发不再持续堆在 `AppContext` 上。

## 2. 当前问题拆解

### 2.1 配置视图与运行时容器耦合

`AppConfigView` 负责解析“应该怎么跑”，`WorkflowRuntimeFacade` 负责“真的去创建和持有服务”，但两者被 `AppContext` 重新包成一个带动态透传的统一入口，最终调用方仍然看不到真实边界。

后果：

- 无法从接口层明确区分“纯配置读取”与“会触发副作用的资源初始化”。
- 调用方拿到 `ctx.xxx` 时，不容易判断是在读配置，还是在触发 lazy init。

### 2.2 `__getattr__` 带来隐式 API 漂移

`AppContext.__getattr__` 会把 `AppConfigView` 和 `WorkflowRuntimeFacade` 上的属性全部向外暴露。

后果：

- 对外 API 没有清单，新增一个内部属性就可能变成外部依赖点。
- 重构时难以判断哪些字段是真正公共契约。
- IDE 补全、类型检查、接口审查都不准确。

### 2.3 Stage 级 options 组装分散在 Context 内部

`build_selection_options`、`build_insight_options`、`build_render_options`、`build_delivery_options` 都堆在 `AppConfigView` 里。

后果：

- `AppContext` 继续承担业务编排细节。
- 各 Stage 的配置演进必须改 `context.py`，模块边界不清晰。

### 2.4 测试依赖私有字段注入

当前多个测试通过直接写 `ctx._storage_manager` 的方式注入假依赖。

后果：

- 测试与内部实现强耦合。
- 一旦更换内部缓存字段名，就要大面积改测试。

### 2.5 运行时资源生命周期粒度过粗

目前 storage、scheduler、service factory 都由 `WorkflowRuntimeFacade` 统一持有。

后果：

- 生命周期策略难以精细化控制。
- 后续若引入更多 provider/runtime（如移动端推送、更多检索后端），`AppContext` 容易再次膨胀。

## 3. 目标状态

目标不是保留一个更大的 `AppContext`，而是把它收缩成“过渡层”，最终让调用关系变成：

- `RuntimeSettings`：只负责强类型配置。
- `RuntimeContainer`：只负责资源实例化与生命周期。
- `StageContext` / `StageOptionsBuilder`：只负责某个 Stage 的输入构造。
- `NewsRunner` / CLI / review：直接依赖显式对象，而不是依赖万能门面。

理想的目标结构：

```text
load_config()
  -> RuntimeSettings
  -> RuntimeContainer
       -> storage
       -> scheduler
       -> selection services
       -> insight services
       -> render services
       -> delivery services

runner / cli / reviews
  -> consume RuntimeSettings + RuntimeContainer + stage builders
```

## 4. 推荐架构

### 4.1 配置层：拆成强类型 Settings 对象

建议新增模块：`newspulse/runtime/settings.py`

核心数据结构：

- `AppSettings`
- `CrawlerSettings`
- `StorageSettings`
- `SelectionSettings`
- `InsightSettings`
- `RenderSettings`
- `DeliverySettings`
- `ScheduleSettings`

要求：

- 只保留业务真正需要的字段。
- 从 `load_config()` 的最终结果映射而来，不再在运行期到处 `dict.get()`。
- 支持 `from_mapping()`，但转换完成后内部不再依赖原始 dict。

收益：

- 配置契约显式。
- 便于按模块做变更审查。
- `AppContext` 不再需要维护几十个 property。

### 4.2 运行时层：独立 RuntimeContainer

建议新增模块：`newspulse/runtime/container.py`

职责：

- 懒加载创建 `StorageManager`。
- 创建 `Scheduler`。
- 创建 `SelectionService` / `InsightService` / `RenderService` / `DeliveryService`。
- 统一 cleanup。

建议接口：

```python
class RuntimeContainer:
    def __init__(self, settings: RuntimeSettings): ...
    def storage(self) -> StorageManager: ...
    def scheduler(self) -> Scheduler: ...
    def selection_service(self) -> SelectionService: ...
    def insight_service(self) -> InsightService: ...
    def render_service(self) -> RenderService: ...
    def delivery_service(self) -> DeliveryService: ...
    def cleanup(self) -> None: ...
```

要求：

- 容器不做业务判断，只做实例装配。
- 所有缓存字段保持私有，但通过显式方法暴露。
- 测试注入通过构造参数或 provider override 完成，不再改私有属性。

### 4.3 Stage 层：每个 Stage 独立 builder

建议新增模块：

- `newspulse/runtime/selection_context.py`
- `newspulse/runtime/insight_context.py`
- `newspulse/runtime/render_context.py`
- `newspulse/runtime/delivery_context.py`

职责：

- 根据 `RuntimeSettings` 生成 `SelectionOptions` / `InsightOptions` / `RenderOptions` / `DeliveryOptions`。
- 只处理本 Stage 的规则，不混入其它 Stage 的运行时对象。

这样 `SelectionOptions` 的变化只影响 selection builder，不需要再改总 Context。

### 4.4 AppContext 变成兼容过渡层

短期保留 `AppContext`，但只允许承担两件事：

1. 持有 `RuntimeSettings`。
2. 持有 `RuntimeContainer`。

同时逐步删掉：

- `__getattr__`
- 大量配置 property
- 私有缓存字段透传 property
- Stage options 的直接构造逻辑

过渡期的 `AppContext` 应该像这样：

```python
class AppContext:
    def __init__(self, config: dict[str, Any]):
        self.settings = RuntimeSettings.from_mapping(config)
        self.runtime = RuntimeContainer(self.settings)

    def cleanup(self) -> None:
        self.runtime.cleanup()
```

之后调用方逐步从：

```python
ctx.create_selection_service()
ctx.build_selection_options()
```

迁移到：

```python
runtime.selection_service()
selection_builder.build(...)
```

## 5. 分阶段执行方案

### Phase 1：收紧契约，不改主流程

目标：不改变外部行为，先把边界收清楚。

任务：

1. 新增 `RuntimeSettings`，把 `AppConfigView` 的纯配置 property 迁过去。
2. 新增 `RuntimeContainer`，把 `WorkflowRuntimeFacade` 的资源创建逻辑迁过去。
3. `AppContext` 内部改为组合 `settings + runtime`，但暂时保留现有调用方式。
4. 去掉 `__getattr__`，改成显式 property / method 转发。

完成标准：

- `AppContext` 对外公开 API 可枚举、可搜索、可审查。
- 测试仍然全部通过。

### Phase 2：拆 Stage builder

目标：把 options 组装逻辑从总 Context 中剥离。

任务：

1. 拆出 `SelectionOptionsBuilder`。
2. 拆出 `InsightOptionsBuilder`。
3. 拆出 `RenderOptionsBuilder`。
4. 拆出 `DeliveryOptionsBuilder`。
5. `NewsRunner` 改为直接依赖这些 builder。

完成标准：

- `context.py` 不再包含 Stage-specific 的 options 细节。
- 某一 Stage 的配置变更不需要修改总 Context。

### Phase 3：替换测试注入方式

目标：去掉对 `_storage_manager` / `_scheduler` 的私有注入依赖。

任务：

1. `RuntimeContainer` 支持 provider override / fake factory。
2. 测试通过构造 fake container 或 fake providers 注入依赖。
3. 删除 `AppContext` 上的私有透传 setter。

完成标准：

- 测试不再写 `ctx._storage_manager = ...`。
- 内部缓存字段完全私有。

### Phase 4：Runner / CLI 直接吃新接口

目标：让 `AppContext` 从主链路中退出核心位置。

任务：

1. `NewsRunner` 直接依赖 `RuntimeSettings` + `RuntimeContainer`。
2. CLI status / doctor / review 入口逐步直接使用新接口。
3. 仅保留一个很薄的 `AppContext` 兼容层，或者彻底删除。

完成标准：

- 新功能开发默认不再触碰 `context.py`。
- `AppContext` 不再是架构核心。

## 6. 关键接口建议

### 6.1 `RuntimeSettings`

```python
@dataclass(frozen=True)
class RuntimeSettings:
    app: AppSettings
    crawler: CrawlerSettings
    storage: StorageSettings
    schedule: ScheduleSettings
    selection: SelectionSettings
    insight: InsightSettings
    render: RenderSettings
    delivery: DeliverySettings
    paths: RuntimePathSettings
```

### 6.2 `RuntimeContainer`

```python
class RuntimeContainer:
    def __init__(self, settings: RuntimeSettings, providers: RuntimeProviders | None = None):
        ...
```

其中 `providers` 允许测试覆盖：

- `storage_factory`
- `scheduler_factory`
- `selection_service_factory`
- `insight_service_factory`
- `render_service_factory`
- `delivery_service_factory`

### 6.3 Builder 层

```python
class SelectionOptionsBuilder:
    def build(self, settings: SelectionSettings, *, strategy: str | None = None, ...):
        ...
```

## 7. 风险与控制

### 风险 1：Runner 改动面大

`NewsRunner` 目前大量依赖 `ctx.xxx` 属性。

控制方式：

- 先做 Phase 1 的显式转发，不直接大改 runner。
- 用 characterization tests 锁住 daily/current/incremental 三条主路径。

### 风险 2：测试大量依赖内部实现

当前测试会直接写 context 私有字段。

控制方式：

- 先引入 `providers` 注入机制，再逐步切换测试。
- 在同一批改造里不要同时改业务逻辑和测试注入模型。

### 风险 3：配置对象拆分后字段映射出错

控制方式：

- 保留 `RuntimeSettings.from_mapping()` 的单点映射。
- 对 selection / insight / render / storage 四个关键 settings 分别补单测。

## 8. 推荐落地顺序

建议按下面顺序推进：

1. `RuntimeSettings` 落地。
2. `RuntimeContainer` 落地。
3. `AppContext` 去掉 `__getattr__`，改显式 API。
4. 拆 `SelectionOptionsBuilder` 与 `InsightOptionsBuilder`。
5. 改测试注入。
6. 最后再让 `NewsRunner`、CLI、review 入口直接吃新接口。

原因：这条路径能先把“结构债”拆开，再处理入口改造，回归风险最低。

## 9. 本轮整改后的建议结论

结合当前代码状态，结论如下：

- 现在已经可以继续做功能开发，不是“必须先全仓重构”才可继续。
- 但 `AppContext` 仍然是中期最值得优先治理的结构点。
- 推荐把 AppContext 重构作为下一阶段的 P1 架构任务，而不是继续往 `context.py` 里加能力。

优先级建议：

- P0：不再往 `AppContext` 新增隐式透传属性。
- P1：完成 Phase 1 + Phase 2。
- P2：完成 Phase 3 + Phase 4，并让 `AppContext` 退出核心主链路。
