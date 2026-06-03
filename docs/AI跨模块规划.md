# AI 应用跨模块规划（含多模型路由系统）

> 计划时间: 2026-05-14
> 状态: 📋 已规划，待开发
> 下一阶段: Phase 1 (订单+退货) + 模型路由基建

## 背景

当前 AI 能力集中在**商品模块**（标题优化、描述生成、质量检查、属性补全、定价建议、图片生成），其他 10 个运营模块几乎无 AI 覆盖。目标是系统性地将 AI 应用到各个业务模块，减少人工操作，提升运营效率。

同时，代码库已具备多模型基础设施（`get_llm()`, `ProviderDef`, transport 注册表, `providers.json`, Settings 页面提供方 CRUD），但**所有端点硬编码单一模型**（`get_llm("minimax", ...)`），无法按业务场景灵活选择模型或热切换。本规划在扩展 AI 功能的同时，增加**模型路由层**统一管理。

---

## 一、架构设计总览

### 层叠关系

```
┌─────────────────────────────────────────┐
│           22 个 AI 功能端点               │  ← 新增（Phase 1-5）
│  (订单/退货/财务/报表/营销/客服/运营等)    │
├─────────────────────────────────────────┤
│       get_ai_llm(feature_key, **kw)      │  ← 新增：统一入口
│  特征 → 层级 → provider → model → param  │
├─────────────────────────────────────────┤
│  get_llm(provider, model, temp, ...)     │  ← 已有：多模型工厂
│     + ProviderDef + transport 注册表      │
├─────────────────────────────────────────┤
│    MiniMax   Claude   DeepSeek   GPT-4o  │  ← models
│  (anthropic) (anthropic) (openai) (openai)│  ← transports
└─────────────────────────────────────────┘
```

### 模型层级定义

| Tier | 用途 | 推荐 provider | 说明 |
|------|------|---------------|------|
| `fast` | 简单分类、关键词提取、简短生成 | deepseek | 低成本、高速度 |
| `default` | 标题优化、描述生成、属性补全 | minimax | 日常运营主力 |
| `quality` | 复杂分析、质量检查、广告分析 | anthropic | 需要深度推理的场景 |
| `embedding` | 向量嵌入（类别匹配等） | minimax (embo-01) | 固定使用 MiniMax 嵌入模型 |

### 配置文件 `data/ai_model_config.json`

```json
{
  "tiers": {
    "fast": { "provider": "deepseek", "model": "deepseek-chat", "temperature": 0.3, "max_tokens": 1024 },
    "default": { "provider": "minimax", "model": "MiniMax-M2.7", "temperature": 0.3, "max_tokens": 2048 },
    "quality": { "provider": "anthropic", "model": "claude-sonnet-4-20250514", "temperature": 0.3, "max_tokens": 4096 },
    "embedding": { "provider": "minimax", "model": "embo-01", "temperature": 0, "max_tokens": 0 }
  },
  "features": {
    "product.title.optimize": { "tier": "default", "temperature": 0.3 },
    "product.description.generate": { "tier": "default", "temperature": 0.4 },
    "product.attributes.complete": { "tier": "default", "temperature": 0.2 },
    "product.quality.check": { "tier": "default", "temperature": 0.2 },
    "product.price.suggest": { "tier": "default", "temperature": 0.4 },
    "product.image.generate": { "tier": null },
    "category.match": { "tier": "fast", "temperature": 0.1 },
    "category.list": { "tier": "fast", "temperature": 0.1 },
    "listing.generate": { "tier": "default", "temperature": 0.7, "max_tokens": 4096 },
    "session.title.summarize": { "tier": "fast", "max_tokens": 50 },
    "agent.main": { "tier": "default" },
    "product.parse": { "tier": "default" },
    "order.anomaly.detect": { "tier": "default" },
    "order.issue.classify": { "tier": "fast" },
    "return.decision.suggest": { "tier": "default" },
    "return.pattern.analyze": { "tier": "quality" },
    "finance.daily.commentary": { "tier": "default" },
    "finance.profit.anomaly": { "tier": "quality" },
    "finance.transaction.tag": { "tier": "fast" },
    "report.summary.generate": { "tier": "quality" },
    "marketing.campaign.analyze": { "tier": "quality" },
    "service.reply.suggest": { "tier": "default" },
    "service.question.answer": { "tier": "fast" },
    "service.review.analyze": { "tier": "default" },
    "operations.replenish.suggest": { "tier": "default" },
    "operations.trend.commentary": { "tier": "default" },
    "autopilot.config.suggest": { "tier": "default" },
    "pricing.competitive.analyze": { "tier": "default" },
    "draft.quality.check": { "tier": "default" },
    "draft.auto.correct": { "tier": "quality" }
  }
}
```

### 共享函数 `get_ai_llm()`

**文件**: `src/icross/api/ai_utils.py`（新建）

```python
def get_ai_llm(feature_key: str, **overrides) -> BaseChatModel:
    """Create LLM by feature key with model routing.

    Resolves: feature_key → config (tier) → tier config → get_llm()
    Allows per-call overrides: temperature, max_tokens, provider, model.
    Falls back to tier "default" if feature not found.
    """
    config = _load_ai_model_config()
    feature_cfg = config.get("features", {}).get(feature_key, {})
    tier_id = feature_cfg.get("tier") or "default"
    tier_cfg = config.get("tiers", {}).get(tier_id, config["tiers"]["default"])

    provider = overrides.pop("provider", None) or tier_cfg["provider"]
    model = overrides.pop("model", None) or tier_cfg.get("model")
    temperature = overrides.pop("temperature", None) or feature_cfg.get("temperature") or tier_cfg.get("temperature", 0.3)
    max_tokens = overrides.pop("max_tokens", None) or feature_cfg.get("max_tokens") or tier_cfg.get("max_tokens", 2048)

    return get_llm(provider, model=model, temperature=temperature, max_tokens=max_tokens, **overrides)
```

### API 端点

| 方法 | 路径 | 用途 |
|------|------|------|
| `GET` | `/api/ai-model-config` | 获取当前配置（含所有 feature 和 tier） |
| `PUT` | `/api/ai-model-config` | 更新配置（允许修改单个 feature 或 tier） |

### Settings 页面新增

在 `SettingsPage.tsx` 的 Collapse 中新增 **"AI 模型配置"** Section：
- 按模块分组的 feature 列表
- Feature 行：名称 → 当前 tier → provider → model → temperature
- 点击行直接编辑 tier 或覆盖 provider/model
- 保存后实时生效（下次 API 调用）

---

## 二、架构模式（复用现有）

**后端**（参考 `ai_product.py`）:
- 端点: `POST /api/{module}/{id}/ai/{action}`
- 从 `OzonRuleKB` 查规则作为 RAG 上下文
- 调用 `get_ai_llm("module.action", temperature=...)` 生成（代替硬编码 `get_llm("minimax", ...)`）
- 用 `_extract_json()` 解析 LLM 响应
- 注册到 `main.py`

**前端**（参考 `Products.tsx`）:
- 每个 AI 操作 = 一个 `useMutation`
- 触发: `RobotOutlined` 图标按钮 + `Tooltip`
- 结果: 填充表单字段或打开结果弹窗
- 加载态: button `loading` 属性
- 反馈: `message.success` 带 before/after 对比

---

## 三、现有 AI 调用迁移

将 13 处现有硬编码调用全部替换为 `get_ai_llm()`：

| 文件 | 行 | 现有代码 | 替换为 |
|------|-----|----------|--------|
| `ai_product.py:119` | `create_llm(LLMType.MINIMAX, ...)` | `get_ai_llm("product.quality.check", ...)` |
| `ai_product.py:539` | `get_llm("minimax", ...)` | `get_ai_llm("product.description.generate", ...)` |
| `ai_product.py:661` | `get_llm("minimax", ...)` | `get_ai_llm("product.price.suggest", ...)` |
| `categories.py:181` | `create_llm(LLMType.MINIMAX, ...)` | `get_ai_llm("category.list", ...)` |
| `chat.py:179` | `create_llm(LLMType.MINIMAX, ...)` | `get_ai_llm("session.title.summarize", ...)` |
| `category_matcher.py:275` | `get_llm("minimax", ...)` | `get_ai_llm("category.match", ...)` |
| `product_parser.py:303` | `create_llm(LLMType.MINIMAX)` | `get_ai_llm("product.parse", ...)` |
| `agent.py:81` | `create_llm(llm_type, ...)` | `get_ai_llm("agent.main", ...)` |
| `agent.py:149-150` | `create_llm(LLMType.MINIMAX, ...)` | `get_ai_llm("session.title.summarize", ...)` |
| `tools_product.py:276` | `create_llm(LLMType.MINIMAX, ...)` | `get_ai_llm("listing.generate", ...)` |
| `tools_product.py:337` | `create_llm(LLMType.MINIMAX, ...)` | `get_ai_llm("product.image.generate", ...)` |

---

## 四、功能模块

### Phase 1: 订单 & 退货 (P0)

| # | 模块 | 功能 | 端点 | 模型层级 | 工作量 |
|---|------|------|------|----------|--------|
| 1.1 | 订单 | **AI 订单异常检测** — 分析大单/高退货率商品/异常地址，标记风险 | `POST /api/orders/{id}/ai/analyze` | default | Medium |
| 1.2 | 订单 | **AI 取消原因分类** — 将取消/退货描述归类为结构化原因 | `POST /api/orders/{id}/ai/classify-issue` | fast | Small |
| 1.3 | 退货 | **AI 退货决策建议** — 根据原因/类目/金额推荐 接受/拒绝/部分退款 | `POST /api/returns/{id}/ai/decision` | default | Medium |
| 1.4 | 退货 | **AI 退货模式分析** — 分析历史退货率、常见原因、季节性趋势 | `POST /api/returns/ai/pattern-analysis` | quality | Medium |

**新建文件**: `ai_orders.py`, `ai_returns.py`
**修改文件**: `Orders.tsx`, `Returns.tsx`

### Phase 2: 财务 & 报表 (P0)

| # | 模块 | 功能 | 端点 | 模型层级 | 工作量 |
|---|------|------|------|----------|--------|
| 2.1 | 财务 | **AI 每日销售评述** — 自然语言总结销售额/利润变化、亮点商品 | `POST /api/finance/ai/daily-commentary` | default | Small |
| 2.2 | 财务 | **AI 利润异常检测** — 标记实际利润偏离预期的订单，分析原因 | `POST /api/finance/ai/profit-anomalies` | quality | Medium |
| 2.3 | 财务 | **AI 费用自动分类** — 将交易流水操作分类为佣金/物流/广告/罚款等 | `POST /api/finance/ai/tag-transactions` | fast | Small |
| 2.4 | 报表 | **AI 报表摘要** — 为 CSV 报表生成中文执行摘要 | `POST /api/reports/ai/generate-summary` | quality | Medium |

**新建文件**: `ai_finance.py`, `ai_reports.py`
**修改文件**: `Finance.tsx`, `Reports.tsx`

### Phase 3: 营销 & 客服 (P0)

| # | 模块 | 功能 | 端点 | 模型层级 | 工作量 |
|---|------|------|------|----------|--------|
| 3.1 | 营销 | **AI 广告效果分析** — 分析 ROAS/点击/转化，给出优化建议 | `POST /api/marketing/ai/analyze-campaign/{id}` | quality | Medium |
| 3.2 | 客服 | **AI 回复建议** — 根据聊天历史生成俄语回复 | `POST /api/service/ai/suggest-reply/{chat_id}` | default | Medium |
| 3.3 | 客服 | **AI 买家问答自动回答** — 根据商品信息生成俄语答案 | `POST /api/service/ai/suggest-answer/{q_id}` | fast | Small |
| 3.4 | 客服 | **AI 评价分析** — 情感分类 + 提取关键问题 + 建议回复 | `POST /api/service/ai/analyze-review/{id}` | default | Medium |

**新建文件**: `ai_marketing.py`, `ai_service.py`
**修改文件**: `Marketing.tsx`, `Service.tsx`

### Phase 4: 运营数据 & 自动运营 (P0/P1)

| # | 模块 | 功能 | 端点 | 模型层级 | 工作量 |
|---|------|------|------|----------|--------|
| 4.1 | 运营数据 | **AI 补货建议** — 基于销量/库存/交期推荐补货数量和时机 | `POST /api/operations-data/ai/replenish` | default | Medium |
| 4.2 | 运营数据 | **AI 趋势评述** — 图表旁 1-2 句中文趋势说明 | `POST /api/operations-data/ai/trend-commentary` | default | Small |
| 4.3 | 自动运营 | **AI 配置建议** — 推荐最佳 AutoPilot 参数 | `POST /api/auto-pilot/ai/suggest-config` | default | Small |

**新建文件**: `ai_operations.py`, `ai_autopilot.py`
**修改文件**: `OperationsData.tsx`, `AutoPilot.tsx`

### Phase 5: 定价 & 草稿 (P1)

| # | 模块 | 功能 | 端点 | 模型层级 | 工作量 |
|---|------|------|------|----------|--------|
| 5.1 | 定价 | **AI 竞争定价分析** — 考虑佣金阶梯/市场价给出优化定价 | `POST /api/pricing/ai/competitive-analysis/{id}` | default | Medium |
| 5.2 | 草稿 | **AI 草稿质量检查** — 发布前检查标题/描述/图片/定价 | `POST /api/drafts/{id}/ai/quality-check` | default | Small |
| 5.3 | 草稿 | **AI 自动修正** — 质量检查不合格项一键修正 | `POST /api/drafts/{id}/ai/correct` | quality | Medium |

**新建文件**: `ai_pricing.py`, `ai_drafts.py`
**修改文件**: `Pricing.tsx`, `Drafts.tsx`

---

## 五、架构改进

1. **新建 `src/icross/api/ai_utils.py`**:
   - `get_ai_llm(feature_key, **overrides)` — 特征→层级→provider 路由
   - `_extract_json()` — 从 `ai_product.py` 提取为共享工具
   - `_search_rules()` — 从 `ai_product.py` 提取 OzonRuleKB 查询
   - `_load_ai_model_config()` — 配置加载器
   - `save_ai_model_config()` — 配置持久化

2. **新建 `data/ai_model_config.json`**: 模型层级 + 特征配置初始化

3. **新建 `src/icross/api/routers/ai_model_config.py`**: `GET/PUT /api/ai-model-config` 端点

4. **修改 `frontend-react/src/pages/SettingsPage.tsx`**: 新增 "AI 模型配置" Collapse Section

5. **所有新建 router 注册到 `main.py`**

6. **迁移 13 处现有硬编码调用** → `get_ai_llm()`

7. **前端可选提炼**: `AiActionButton` 组件、`AiResultModal` 组件（非必须，可逐个实现）

---

## 六、关键文件清单

### 新建文件

| 文件 | 用途 |
|------|------|
| `src/icross/api/ai_utils.py` | `get_ai_llm()`, `_extract_json()`, `_search_rules()`, 配置加载 |
| `src/icross/api/routers/ai_model_config.py` | `GET/PUT /api/ai-model-config` |
| `data/ai_model_config.json` | 模型层级 + 特征配置 |
| `src/icross/api/routers/ai_orders.py` | Phase 1 订单 AI 端点 |
| `src/icross/api/routers/ai_returns.py` | Phase 1 退货 AI 端点 |
| `src/icross/api/routers/ai_finance.py` | Phase 2 财务 AI 端点 |
| `src/icross/api/routers/ai_reports.py` | Phase 2 报表 AI 端点 |
| `src/icross/api/routers/ai_marketing.py` | Phase 3 营销 AI 端点 |
| `src/icross/api/routers/ai_service.py` | Phase 3 客服 AI 端点 |
| `src/icross/api/routers/ai_operations.py` | Phase 4 运营数据 AI 端点 |
| `src/icross/api/routers/ai_autopilot.py` | Phase 4 自动运营 AI 端点 |
| `src/icross/api/routers/ai_pricing.py` | Phase 5 定价 AI 端点 |
| `src/icross/api/routers/ai_drafts.py` | Phase 5 草稿 AI 端点 |

### 修改文件

| 文件 | 改动 |
|------|------|
| `src/icross/api/routers/ai_product.py` | 提取共享工具，替换硬编码调用为 `get_ai_llm()` |
| `src/icross/api/routers/categories.py` | 替换 `create_llm(LLMType.MINIMAX)` → `get_ai_llm("category.list")` |
| `src/icross/api/routers/chat.py` | 替换 → `get_ai_llm("session.title.summarize")` |
| `src/icross/api/routers/main.py` | 注册 11 个新 router |
| `src/icross/services/category_matcher.py` | 替换 → `get_ai_llm("category.match")` |
| `src/icross/services/product_parser.py` | 替换 → `get_ai_llm("product.parse")` |
| `src/icross/agents/master/agent.py` | 替换 → `get_ai_llm("agent.main")`, `get_ai_llm("session.title.summarize")` |
| `src/icross/agents/master/tools_product.py` | 替换 → `get_ai_llm("listing.generate")` |
| `frontend-react/src/pages/SettingsPage.tsx` | 新增 "AI 模型配置" Section |
| `frontend-react/src/pages/operations/Orders.tsx` | Phase 1 AI 按钮 |
| `frontend-react/src/pages/operations/Returns.tsx` | Phase 1 AI 按钮 |
| `frontend-react/src/pages/operations/Finance.tsx` | Phase 2 AI 按钮 |
| `frontend-react/src/pages/operations/Reports.tsx` | Phase 2 AI 按钮 |
| `frontend-react/src/pages/operations/Marketing.tsx` | Phase 3 AI 按钮 |
| `frontend-react/src/pages/operations/Service.tsx` | Phase 3 AI 按钮 |
| `frontend-react/src/pages/operations/OperationsData.tsx` | Phase 4 AI 按钮 |
| `frontend-react/src/pages/operations/AutoPilot.tsx` | Phase 4 AI 按钮 |
| `frontend-react/src/pages/operations/Pricing.tsx` | Phase 5 AI 按钮 |
| `frontend-react/src/pages/operations/Drafts.tsx` | Phase 5 AI 按钮 |

---

## 七、总计

- **22 个 AI 功能**，覆盖 **10 个模块**
- **1 个跨层模型路由系统**（`get_ai_llm()` + 配置 + UI）
- **13 处现有迁移**，**11 个新后端文件**，**10+ 前端文件修改**
- 预估工作量: **25-35 人日**
- 建议从 Phase 1 (订单+退货) + 模型路由基建 开始
