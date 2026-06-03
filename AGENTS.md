# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Project Overview

iCross Agent is an AI-powered e-commerce operations system for managing Ozon (Russian marketplace) shops. The system uses a conversational AI Agent interface to automate product sourcing, listing generation, pricing, and advertising operations.

**Current Status**: Phase 1-8 ✅ + Phase A-D ✅ + AI 跨模块应用 ✅ (34 features, 11 个 AI 路由模块). **Next**: Agent 跨能力编排 (复合任务链路)

## Architecture

```
[Web前端 / Telegram / 企业微信 / 钉钉]
           ↓
     [LangGraph Agent]              # create_react_agent + InMemorySaver
           ↓
  ┌─────────────────────────────────────┐
  │  MiniMaxChat (主)                    │
  │  ChatAnthropic (备)                  │
  │  ChatDeepSeek (备)                   │
  └─────────────────────────────────────┘
           ↓
  ┌── 工具层 ──────────────────────────┐
  │ 基础工具:  read/write/cli/文件解析   │  ← Phase 5 新增
  │ 业务工具:  选品 | Listing | 图片    │
  │ Ozon工具:  商品 | 订单 | 仓库 | 财务 │
  │ 渠道工具:  Telegram/企微/钉钉       │
  └────────────────────────────────────┘
           ↓
  [Ozon API | 1688/拼多多爬虫 | AI模型(DeepSeek/Codex/MiniMax)]
```

> **架构说明**: 使用 LangGraph `create_react_agent` 作为 Agent 执行框架，核心特点：
>
> - LangGraph Pregel 图执行引擎 + 条件边
> - 内置 checkpointer (InMemorySaver) 实现 Session 持久化
> - `bind_tools()` 绑定工具，支持 OpenAI-style function calling
> - 工具执行通过 `ToolNode` 自动处理

### Technology Stack

| Layer                        | Technology                                  | Vendor Path                                                                      |
| ---------------------------- | ------------------------------------------- | -------------------------------------------------------------------------------- |
| **Agent Framework**          | **LangGraph** (`create_react_agent`)         | `vendors/langgraph/`                                                             |
| **LLM**                      | **MiniMaxChat** (langchain-community)        | `vendors/langchain-community/`                                                   |
| **LLM Factory**              | **Multi-model** (MiniMax/Codex/DeepSeek)    | `src/icross/agents/master/llm.py`                                                |
| **Tools**                    | **LangChain `@tool`** decorator              | `src/icross/agents/master/tools.py`                                              |
| **Ozon API Client**          | **ozonapi-async**                           | `vendors/OzonAPI-main/src/ozonapi/`                                              |
| **Web Framework**            | FastAPI                                     | `vendors/fastapi/`                                                               |
| **Task Queue**               | Celery + Redis (optional)                   | `vendors/celery/`                                                                |
| **Web Scraping**             | DrissionPage                                | `vendors/DrissionPage/`                                                          |
| **Image Background Removal** | rembg                                       | `vendors/rembg/`                                                                 |
| **Image Generation**         | Stable Diffusion WebUI                       | `vendors/stable-diffusion-webui/`                                                |
| **Document Parsing**         | **Docling** (PDF/Excel/Word/PPT)            | `pip install docling`                                                            |
| **Frontend (current)**       | Vanilla HTML + Ant Design CDN                 | `frontend/`                                                                       |
| **Frontend (migrating)**     | **React 18 + TypeScript + Vite + Ant Design 5.x** | `frontend/` (重构中)                                                     |
| **Reference Architecture**   | Dify                                        | `vendors/dify/` (backend: `api/core/`, frontend: `web/`)                          |

## Current Directory Structure

```
src/icross/                      # Main package
├── __init__.py
├── api/                          # FastAPI application
│   ├── __init__.py
│   ├── main.py                  # App entry, /health
│   └── routers/
│       ├── __init__.py
│       ├── chat.py              # WebSocket /chat endpoint
│       ├── sessions.py          # Session CRUD API
│       ├── shops.py            # Shop management API
│       └── products.py # Product management API
├── agents/                       # Agent implementations
│   └── master/
│       ├── __init__.py
│       ├── agent.py             # create_react_agent wrapper
│       ├── llm.py               # Multi-LLM factory
│       ├── tools.py             # @tool decorated tools (业务工具)
│       ├── tools_product.py     # 选品/Listing/图片工具
│       └── tools_system.py      # 基础工具: read/write/cli/文档解析 ← NEW
├── core/                         # Infrastructure
│   ├── memory/
│   │   ├── __init__.py
│   │   └── manager.py           # SessionMemoryManager (JSON file)
│   └── storage/
│       ├── __init__.py
│       ├── ozon_data.py         # JSON file storage
│       ├── session_postgres.py  # Session storage
│       ├── shop_postgres.py     # Shop storage
│       └── product_postgres.py  # Product storage
├── services/
│   ├── task_queue.py            # Lightweight task queue (Phase 4)
│   ├── workflow.py              # Automation workflow engine (Phase 4)
│   ├── document_reader.py       # 文档解析服务 (PDF/Excel/Word)   ← NEW
│   └── ozon/
│       ├── __init__.py          # OzonClient wrapper
│       └── client.py            # Ozon API 客户端
tests/
workspace/                        # Agent 工作区沙箱              ← NEW
uploads/                          # 文件上传临时目录              ← NEW
frontend/                         # 前端静态页面 (legacy)
├── index.html                   # Three-column agent frontend
├── operations.html              # Unified operations center
├── products.html                # Product management (redirect)
├── drafts.html                  # Draft review (redirect)
├── hub.html                     # Hub/product selection (redirect)
└── static/                      # Static assets

frontend-react/                  # 前端 React (重构中)
├── src/
│   ├── main.tsx                 # App entry
│   ├── App.tsx                  # Router + layout
│   ├── index.css                # Global styles
│   ├── components/
│   │   └── AppLayout.tsx        # Top nav + layout shell
│   ├── pages/
│   │   ├── AgentPage.tsx        # 3-column agent chat
│   │   ├── OperationsPage.tsx   # Operations with sidebar
│   │   └── SettingsPage.tsx     # Config management
│   ├── api/                     # API client modules
│   ├── stores/                  # Zustand stores
│   ├── hooks/                   # Custom hooks
│   └── types/                   # TypeScript types
├── package.json
├── vite.config.ts
└── tsconfig.json

data/                             # JSON 数据文件
```

## Data Storage

All data is stored in **JSON files** under `data/` directory (no database required). Each storage class manages its own JSON file:

| File | Storage Class | Content |
|------|--------------|---------|
| `data/shops.json` | ShopStorage | Ozon 店铺配置 |
| `data/products.json` | ProductStorage | 商品数据 |
| `data/sessions.json` | SessionStorage | 会话历史 |
| `data/session_messages.json` | SessionStorage (messages) | 会话消息 |
| `data/drafts.json` | DraftStorage | 产品草稿 |
| `data/orders.json` | OrderStorage | 订单数据 |
| `data/analytics.json` | AnalyticsStorage | 库存分析 |
| `data/warehouses.json` | WarehouseStorage | 仓库列表 |
| `data/seller_info.json` | SellerInfoStorage | 卖家信息 |
| `data/sync_logs.json` | SyncLogStorage | 同步日志 |
| `data/templates.json` | ListingTemplateStorage | Listing 模板 |
| `data/categories.json` | CategoryStorage | Ozon 类目缓存 |
| `data/tasks.json` | TaskStorage | 异步任务队列 |
| `data/workflows.json` | WorkflowStorage | 自动化工作流 |

## Vendor Codebase Usage

Vendors are **git clones** of open-source projects, not installed packages. They are referenced via `tool.uv.sources` in `pyproject.toml`:

- **LangChain**: `vendors/langchain/` (core, community)
- **LangGraph**: `vendors/langgraph/` (pregel, prebuilt)
- **OzonAPI**: `vendors/OzonAPI-main/src/ozonapi/`
- **Dify** (reference): `vendors/dify/api/core/` for backend patterns
- **Next.js**: `vendors/next.js/packages/next/src/` for framework internals
- **Ant Design**: `vendors/ant-design/components/` for component patterns
- **DrissionPage**: Use `vendors/DrissionPage/` directly
- **rembg**: Use `vendors/rembg/` directly
- **FastAPI**: Use `vendors/fastapi/` directly
- **Celery**: Use `vendors/celery/` directly

## Development Phases

### Phase 1: Core Skeleton (2-3 weeks) — ✅ DONE

- [x] Initialize Python project with `uv` and `pyproject.toml`
- [x] Set up directory structure under `src/icross/`
- [x] Implement **LangGraph Agent** with `create_react_agent`
- [x] Build FastAPI gateway with `/chat` endpoint and WebSocket streaming
- [x] Create three-column frontend layout
- [x] Implement Session + Memory management via JSON file storage
- [x] Add simple example tools (calculator, datetime) for MVP demo
- [x] Session save/load/search with JSON file persistence
- [x] Session naming (auto-summary from first message)
- **Deliverable**: MVP with simple Agent echo conversation

### Phase 2: Ozon Basic Operations (4 weeks) — ✅ DONE

- [x] Ozon API client wrapper (`src/icross/services/ozon/client.py`)
- [x] Tools: `ozon_product_list`, `ozon_product_info`, `ozon_update_price`, `ozon_update_stock`
- [x] Tools: `ozon_analytics_stocks`, `ozon_order_list`, `ozon_seller_info`, `ozon_get_warehouses`
- [x] Hub product management center (`frontend/products.html`)
- [x] JSON file storage for flexible product attributes
- [x] Product sync from Ozon with detailed info (batch fetching)
- [x] Agent draft review workflow (create_product_draft, list_pending_drafts, /api/drafts endpoints)
- **Deliverable**: Ozon product management with human-in-the-loop draft approval

### Phase 3: Smart Product Selection & Listing (3 weeks) — ✅ DONE

- [x] DrissionPage crawler integration for 1688/Pinduoduo
- [x] Tool: `search_1688_products`, `search_pinduoduo_products`
- [x] Tool: `search_hot_product` (多平台聚合选品)
- [x] Tool: `generate_listing` (Russian language)
- [x] Tool: `translate_text`
- [x] Tool: `generate_product_image`, `remove_background`
- [x] Hub product selection center (operations.html 选品 tab)
- [x] Product detail crawler by URL

### Phase 4: Visual Automation & Smart Pricing (3 weeks) — ✅ DONE

- [x] Seedream AI image generation (代替 SD WebUI)
- [x] Rembg background removal
- [x] Cost/profit calculator (基于 Ozon 平台规则)
- [x] Auto-pricing rules engine + scheduler
- [x] Ozon 平台规则知识库
- [x] Task Queue (异步任务队列)
- [x] Automation Workflow (选品→图片→Listing→定价→上架)
- [x] ~~SD WebUI~~ (已取消，改用 Seedream API)

### Phase 5: Agent 基础能力增强 & Full托管/订单管理 (4-5 weeks) — ✅ DONE

**目标：增强 Agent 核心能力（文件读写/命令执行/文档解析），同时完成 FBS 订单全流程 + 广告管理**

- [x] **Agent 基础工具**
  - `read_file(path)` — 读取工作区文件（带沙箱隔离，限制访问路径）
  - `write_file(path, content)` — 写入/创建文件
  - `edit_file(path, old_string, new_string)` — 精确编辑文件内容
  - `delete_file(path)` — 删除文件
  - `run_command(command)` — 执行 CLI 命令（命令白名单 + 超时控制 + 沙箱）
  - `glob_files(pattern)` / `grep_files(pattern)` — 文件搜索和内容搜索
  - **安全机制**：工作区沙箱（`./workspace` 目录）、路径穿越防护、命令白名单
- [x] **文件解析能力（Docling）**
  - 后端：上传端点 `/api/upload` → `workspace/` 存储 → Docling 解析
  - 技术方案：[**Docling**](https://github.com/unify-apps/docling)（IBM 开源，支持 PDF/DOCX/XLSX/PPTX/HTML/图片）
    - 统一文档模型，导出 Markdown
    - 内置 OCR（扫描件），表格结构识别，版面分析
    - 回退方案：python-docx / openpyxl / pypdf
  - Agent 工具：`read_document(file_path)` — 自动识别类型并解析为文本
- [x] **FBS 订单管理**
  - `ozon_fbs_order_list` — FBS 订单列表（多店铺支持）
  - `ozon_fbs_order_info` — 订单详情（商品/物流/费用）
  - `ozon_fbs_ship_orders` — 确认打包发货 (`/v4/posting/fbs/ship`)
  - `ozon_fbs_awaiting_delivery` — 标记等待配送
  - `ozon_fbs_create_act` — 创建验收报告
  - `ozon_fbs_get_act_status` — 查询验收报告状态
- [x] **广告管理**
  - `ozon_ad_campaigns_list` / `ozon_ad_campaign_info` — 广告活动查询
  - `ozon_ad_campaign_create` / `ozon_ad_campaign_update` — 广告创建/更新
  - `ozon_ad_campaign_stats` — 广告数据统计（展示/点击/花费/ROI）
  - `ozon_ad_campaign_products` — 广告商品列表
- [x] **多店铺支持**（所有工具支持 `shop_id` + `shop_ids` 参数）
- **Source files**:
  - `src/icross/agents/master/tools_system.py` — 系统工具（8个）
  - `src/icross/services/document_reader.py` — Docling 文档解析服务
  - `src/icross/api/routers/uploads.py` — 文件上传端点
  - `src/icross/services/ozon/client.py` — 新增 FBS + 广告 API 方法
  - `src/icross/agents/master/tools.py` — FBS 订单 + 广告管理工具

### Phase 6: 售后 & 财务 (2-3 weeks) — ✅ DONE

**目标：售后处理链路 + 财务数据可视化**

- [x] **售后中心**
  - 退货列表（FBO + FBS + rFBS）
  - 退货详情（商品、原因、状态）
  - rFBS 退货处理：验收 / 拒绝（含备注）/ 退款 / 索赔
  - 退货看板：待处理 / 已验收 / 已退款
- [x] **财务中心**
  - 交易流水明细（`/v3/finance/transaction/list`）
  - 每日销售报表（`/v1/finance/realization/by-day`）
  - 订单入账明细（`/v2/finance/realization`）
  - 按订单查看利润（结合现有成本计算）
- [x] Agent 工具：`ozon_returns_list`, `ozon_finance_transactions`
- **Deliverable**: 运营中心新增退货和财务 tab，售后流程可操作

### Phase 7: 客服 & 营销 (2-3 weeks) — ✅ DONE

**目标：打通买家沟通渠道 + 营销活动管理**

- [x] **客服中心**
  - 买家聊天历史（`/v3/chat/history`）
  - 发送消息/文件（`/v1/chat/send/message` + `/v1/chat/send/file`）
  - 买家问答管理：待回答问题列表 → 回答 → 删除
  - 商品评价管理：评价列表 → 回复
  - 未读会话提醒
- [x] **营销中心**
  - 可用活动列表（`/v1/actions`）
  - 活动中商品管理：加入/移出
  - 折扣申请审批流程
  - 自建活动：折扣/分期/满减/优惠券
- [x] Agent 工具：`ozon_chat_send`, `ozon_chat_history`, `ozon_actions_list`
- **Deliverable**: 运营中心新增客服和营销 tab，支持买家沟通和活动参与

### Phase 8: 数据报表 & 智能化 (2-3 weeks) — ✅ DONE

**目标：异步报表 + 看板图表 + 多通道通知**

- [x] **报表中心**
  - 商品/订单/财务/库存/分析 5 种异步报表生成 & 下载
  - 报表状态追踪、历史报表列表
  - 报表 API（`/api/reports/*`）
- [x] **Agent 工具字段说明**
  - 14 个核心工具增加 `_fields` 描述，LLM 可读字段含义和计算关系
  - 覆盖财务、订单、退货、商品等高频工具
- [x] **看板图表可视化**
  - ECharts 集成，趋势图/柱状图展示销售数据
  - 后端 `/api/dashboard/metrics` 时间序列 API
- [x] **飞书机器人通知**
  - 基于 `lark-oapi` SDK（参照 Hermes Agent FeishuAdapter 实现）
  - Agent 可主动发通知到飞书群（`send_notification` 工具）
  - 通知 REST API（`/api/notifications/send` + `/api/notifications/channels`）
  - 通知调度服务（`NotificationService` + `FeishuNotifier`）
- [ ] **多通道接入**
  - 飞书通知打通
  - Telegram/企业微信/钉钉（后续扩展）
- **Deliverable**: 看板图表展示 + 飞书通知 + Agent 字段感知

### Phase 9: 架构升级 & 智能化深化 (3-4 weeks) — ✅ 核心已完成

**目标：借鉴 Hermes Agent 架构模式，重构工具/模型/上下文系统，增强 Agent 编排能力**

参考架构来源：`vendors/hermes-agent-main/`

| 优先级 | 领域 | 任务 | 说明 | 参考文件 |
|--------|------|------|------|----------|
| P0 | **多模型适配** | ProviderTransport ABC + 注册表模式 | 替换 `llm.py` 的硬编码 `LLMType`，改 Hermes transport 模式 | `agent/transports/base.py`, `__init__.py` |
| P0 | **多模型适配** | Provider 数据模型 + 配置文件 | `data/providers.json` 驱动，支持运行时加 provider | `hermes_cli/providers.py` (`ProviderDef`) |
| P0 | **多模型适配** | 凭据池 (Credential Pool) | 统一管理多来源 API key（环境变量 / .env / JSON） | `agent/credential_pool.py` |
| P0 | **工具注册表** | 替换手动 `TOOLS` 列表 | 每个 tool 文件自注册，AST 自动发现 | `tools/registry.py` |
| P1 | **工具集组合** | 按角色分组工具 | 运营/财务/客服工具集，`resolve_toolset()` 递归展开 | `tools/registry.py` |
| P1 | **平台适配器工厂** | `Platform` 枚举 + 工厂 + `BasePlatformAdapter` ABC | 统一飞书/Telegram/钉钉接口，飞书双向通信 | `gateway/platforms/base.py`, `feishu.py` |
| P1 | **传递路由** | `"platform:chat_id"` 寻址 | Agent 发通知时指定目标平台和频道 | `gateway/config.py` (`PlatformConfig`) |
| P2 | **可插拔上下文引擎** | `ContextEngine` ABC | 长会话自动总结，保护首尾消息 | `agent/context_engine/` |
| P2 | **Cron 调度增强** | 定时任务支持 | 每日销售报告推送飞书，文件锁防重叠 | `gateway/platforms/base.py` |
| P2 | **Agent 跨能力编排** | 复合任务链路 | "处理退货并补货通知运营"等多步骤任务 | 工作流引擎扩展 |
- **Deliverable**: 多模型 ProviderTransport + 工具自动注册 + 多通道架构 + 定时任务 + Agent 编排

---

### 能力全景图

```
┌──────────────────────────────────────────────────────────────────────────────────┐
│                          iCross Agent 能力全景                                   │
├──────────────────────────────────────────────────────────────────────────────────┤
│  Phase 1-2     │  Phase 3-4       │  Phase 5         │  Phase 6-7     │ Phase 8 │
│  基础架构       │  智能选品上架     │  Agent增强+订单   │  售后财务客服营销 │ 报表    │
├────────────────┼──────────────────┼──────────────────┼─────────────────┼────────┤
│ Agent 框架      │ 1688/拼多多爬虫  │ 文件读写(read/    │ FBS/rFBS退货    │ 报表    │
│ WebSocket 通信  │ AI Listing 生成  │   write/edit)    │ 交易流水/销售    │ Agent  │
│ 会话记忆/持久化  │ 图片生成/去背景  │ CLI命令执行       │ 买家聊天/问答    │ 异常    │
│ 商品管理 CRUD   │ 定价规则引擎     │ 文档解析(PDF/    │ 评价管理        │ 多通道  │
│ 草稿审批流程    │ 自动化工作流     │   Excel/Word)    │ 营销活动/折扣   │         │
│ 多店铺支持      │ Ozon 规则知识库  │ FBS订单/发货/运单│ 利润分析        │         │
│                │                  │ 广告管理         │ 成本核算        │         │
└────────────────┴──────────────────┴─────────────────┴────────────────┴─────────┘
```

## Key Patterns

### LangGraph Agent Creation

```python
from langgraph.prebuilt import create_react_agent
from icross.agents.master.agent import create_agent
from icross.agents.master.llm import LLMType

# Create agent (uses InMemorySaver checkpointer)
agent = create_agent(llm_type=LLMType.MINIMAX)
```

### Agent Invocation

```python
from langchain_core.messages import HumanMessage

config = {"configurable": {"thread_id": "session-123"}}
result = agent.invoke(
    {"messages": [HumanMessage(content="查看店铺数据")]},
    config
)
```

### Tool Definition

```python
from langchain_core.tools import tool

@tool
def calculator(expression: str) -> str:
    """执行数学计算。

    Args:
        expression: 数学表达式，如 "100 * 23"
    """
    result = eval(expression)  # simplified
    return str(result)
```

### Session Memory (checkpointer)

```python
from icross.agents.master.agent import default_agent

config = {"configurable": {"thread_id": "session-123"}}

# 首次对话
agent.invoke({"messages": [HumanMessage(content="hi")]}, config)

# 同一 session_id 再次对话，自动携带历史 (InMemorySaver)
agent.invoke({"messages": [HumanMessage(content="记得我吗？")]}, config)
```

### WebSocket Streaming

```python
from icross.agents.master.agent import default_agent

async for event in default_agent.astream({"messages": messages}, config):
    if "messages" in event:
        for msg in event["messages"]:
            await ws.send_json({"type": "message", "content": msg.content})
```

## Data Models

Core entities defined in `docs/Design.md`:

- **Shop**: ozonClientId, ozonApiKey, status
- **Session**: chat history per shop (via LangGraph checkpointer)
- **Product**: title, sku, price, stock, status, sourceUrl
- **ProductDraft**: Agent-generated content pending review
- **Task**: async task tracking with logs
- **PriceRule**: auto-pricing configuration
- **AdCampaign**: advertising campaign management

## Environment Variables

```
MINIMAX_API_KEY=sk-...
MINIMAX_GROUP_ID=...
ANTHROPIC_API_KEY=sk-ant-...
DEEPSEEK_API_KEY=sk-...
OPENAI_API_KEY=sk-...
OZON_CLIENT_ID=...
OZON_API_KEY=...
```

## Important Notes

- **Human-in-the-Loop**: Product publishing and ad creation require mandatory human confirmation
- **Safety Rules**: Agent refuses batch operations (>50 items), negative prices, shop deletion
- **Session-Shop Binding**: Each Session is bound to one shop; switching shops filters Session list
- **Rate Limiting**: Ozon API limited to ~27 QPS; implement exponential backoff for retries
- **Multilingual**: Primary content is Russian (for Ozon SEO) and Chinese (for internal ops)
- **Data Storage**: JSON files under `data/` directory — no database required
- **LangGraph checkpointer**: Uses InMemorySaver for session persistence within conversation

## Reference Documentation

| Doc                | Location                                                                              |
| ------------------ | ------------------------------------------------------------------------------------- |
| **AI 跨模块规划**  | `docs/AI跨模块规划.md` (AI 跨模块 + 多模型路由系统方案 — 待开发)                     |
| **Design Spec**    | `docs/Design.md` (comprehensive system design — **authoritative**)                    |
| **Product Design** | `PRODUCT.md` (brand personality, design principles, anti-references — **impeccable**) |
| ~~Requirements~~   | `docs/Requirements.md` (**obsolete** — content merged into Design.md)                 |
| Vendor Research    | `docs/research.md` (updated with vendor analysis)                                     |
| LangChain Core     | `vendors/langchain/libs/core/src/langchain_core/`                                      |
| LangGraph          | `vendors/langgraph/libs/pregel/` + `vendors/langgraph/libs/prebuilt/`                 |
| MiniMaxChat        | `vendors/langchain-community/libs/community/langchain_community/chat_models/minimax.py`|
| OzonAPI            | `vendors/OzonAPI-main/readme.md`                                                      |
| Dify (reference)   | `vendors/dify/AGENTS.md`                                                              |
| Next.js (frontend) | `vendors/next.js/AGENTS.md` (symlink to AGENTS.md)                                    |
| Ant Design         | `vendors/ant-design/AGENTS.md`                                                        |

## Design Context

See `PRODUCT.md` for full product design context. Key principles:

- **AI-native, not AI-wrapped**: Agent is the core interaction paradigm, UI is the confirmation and transparency layer
- **Progressive disclosure**: Simple path first, complexity on demand. Sellers shouldn't see task queues and sync logs by default
- **Trust through transparency**: Show Agent's thinking and tool calls for every step
- **Human in control**: Every irreversible action requires confirmation; UI clearly marks who decides (Agent vs human)
- **Warm professionalism**: Between cold enterprise and casual consumer — think Linear's restraint, Notion's approachability
- **Anti-references**: Not traditional ERP (table-heavy, deep menus), not AI wrapper template (generic chat + black/white theme)

## Current Execution Plan

Immediate parallel tracks after Phase 8 completion:

### Phase A: 选品闭环 & 基建修复 — ✅ DONE

| # | Task | Est. | Description |
|---|------|------|-------------|
| A1 | Product Parser 结构化 | 1d | Pydantic output model for SPU/SKU, JSON Schema validation |
| A2 | 类目向量匹配引擎 | 2d | Embedding precompute → cosine similarity top-5 → LLM re-rank |
| A3 | 工作流引擎修复 | 2d | TypeError fix + image handler + auto step advance + persistence |
| A4 | 定价推送 Ozon | 1d | Push price to Ozon API after rule apply, log results |
| A5 | 路由补全 | 0.5d | Create products.html / drafts.html / hub.html frame pages |

### Phase B: 前端重构 & 设计系统 — ✅ DONE

> 额外完成: Images, Pricing, Returns, Marketing, AutoPilot, Service, OperationsData, Reports, System 共 9 个运营子页面；SettingsPage (LLM providers/shops/notifications) 配置管理页面。

| # | Task | Est. | Description |
|---|------|------|-------------|
| B0 | 项目初始化 | 1d | Vite + React 18 + TypeScript + Ant Design 5 + React Router + Zustand |
| B1 | 信息架构 + 导航框架 | 1.5d | Three-level nav: /agent / /operations / /settings; sidebar + breadcrumbs |
| B2 | Agent 对话页迁移 | 1.5d | Migrate index.html 3-column layout to React components |
| B3 | 运营工作台迁移 | 2.5d | Dashboard / Hub / Products / Drafts / Orders / Finance pages |
| B4 | 统一组件系统 | 1d | DataTable, PageHeader, StatusTag, ConfirmModal, empty/error states |
| B5 | 设计系统微调 | 0.5d | Ant Design token customization, skeleton loading, global error handling |

### Phase C: 自动运营落地 — ✅ DONE

| # | Task | Est. | Description |
|---|------|------|-------------|
| C1 | 调度器统一 | 1.5d | Migrate pricing scheduler to scheduler.py, JSON persistence |
| C2 | 自动运营配置项 | 2d | Config UI + Agent tools (auto_pilot_config.json) |
| C3 | 类目 ID 贯通 | 1.5d | Wire category_id through listing/price/creation pipeline |
| C4 | Listing→Draft 桥接 | 1d | Combined tool + auto image upload to Ozon CDN |

### Phase D: 收尾打磨 — ✅ DONE

| # | Task | Est. | Description |
|---|------|------|-------------|
| D1 | Ozon 规则知识库 | 1d | Build index + Agent search_ozon_rules tool | ✅ |
| D2 | Dashboard 监控看板 | 0.5d | Auto-pilot status cards on dashboard; 集成 ECharts 销售趋势图表 | ✅ |
| D3 | Design polish | 0.5d | `/impeccable polish` final pass | ✅ |

### AI 跨模块应用 + 多模型路由系统 — 📋 PLANNED

见 `docs/AI跨模块规划.md` 完整方案。核心思路：
- **22 个 AI 功能**覆盖 10 个运营模块（订单/退货/财务/报表/营销/客服/运营数据/自动运营/定价/草稿）
- **模型路由层** `get_ai_llm(feature_key)` 统一管理所有 AI 调用的模型选择
- **4 个模型层级** (fast/default/quality/embedding)，通过 `data/ai_model_config.json` 可配置
- **Settings 页面**新增 AI 模型配置 UI
- 建议从 Phase 1 (订单+退货) + 模型路由基建开始

### Architecture Vision (Phase 9 — separate track)

Phase 9 核心目标已达成: ProviderTransport + 凭证池 (agents/llm/), 工具注册表 (agents/tools/registry.py) + 自动发现, 爬虫已移除, 上下文引擎已实现, Cron 调度增强已有文件锁+重叠预防. 剩余: Agent 跨能力编排, 平台双向通信 (按需).
