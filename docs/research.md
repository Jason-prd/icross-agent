# iCross Agent — 开源项目研究报告

> **日期**：2026-04-25
> **状态**：核心项目调研完成，vendor 代码已完善
> **位置**：`vendors/` 目录下已克隆所有开源项目源码

---

## 一、已克隆项目清单

```
vendors/
├── langgraph/                      # LangGraph (from langchain-ai/langgraph)
│   └── libs/
│       ├── langgraph/             # 核心框架，含 Pregel 编排引擎
│       ├── checkpoint/            # checkpoint 接口定义
│       ├── checkpoint-postgres/   # Postgres checkpoint 实现
│       ├── checkpoint-sqlite/     # SQLite checkpoint 实现
│       ├── prebuilt/              # 高级 API（create_agent 等）
│       ├── cli/                   # 命令行工具
│       ├── sdk-py/                # Python SDK
│       └── sdk-js/                # JS/TS SDK
│
├── dify/                           # Dify（从社区克隆）
│   ├── api/                       # Python Flask 后端（DDD 架构）
│   │   └── core/                  # 核心域（agent/app/llm/memory/tools 等）
│   └── web/                       # Next.js 前端
│
├── next.js/                        # Next.js 框架（pnpm monorepo）
│   ├── packages/                  # 发布包（next/create-next-app 等）
│   ├── turbopack/                  # Turbopack bundler (Rust)
│   ├── crates/                    # SWC 编译绑定 (Rust)
│   └── test/                      # 测试套件
│
├── ant-design/                     # Ant Design React 组件库
│   ├── components/                # 84+ 组件（TypeScript + CSS-in-JS）
│   └── docs/                      # 站点文档
│
├── OzonAPI-main/                   # Ozon Seller API 客户端（异步 + Pydantic）
│   └── src/ozonapi/               # 核心代码
│
├── celery/                         # Celery 任务队列
│   └── celery/                    # 主包
│
├── fastapi/                        # FastAPI Web 框架
│   └── fastapi/                   # 主包
│
├── rembg/                          # 图片去背景库
│   └── rembg/                     # 主包
│
├── DrissionPage/                   # 爬虫框架（双引擎）
│
└── stable-diffusion-webui/         # Stable Diffusion WebUI
    └── modules/                   # 核心脚本
```

---

## 二、核心研究成果

### 2.1 LangGraph — 有状态 Agent 编排框架

**关键发现**：

| 特性 | 详情 |
|------|------|
| 定位 | 低层编排框架，构建有状态、长时间运行的 Agent |
| 核心类 | `Pregel`（图执行引擎）+ `NodeBuilder`（节点构建器） |
| 状态管理 | `checkpoint` 机制支持持久化、故障恢复、人在环中 |
| Memory | 内置短时/长时 memory，支持跨 session 持久化 |
| Human-in-the-loop | `interrupt` 机制，可在任意节点暂停等待人工确认 |
| 调试 | LangSmith 集成，可视化执行路径和状态转换 |

**架构**：
```
vendors/langgraph/libs/langgraph/langgraph/
├── pregel/         # 核心执行引擎
│   ├── main.py     # Pregel 类（from langgraph.pregel.main import Pregel）
│   ├── _loop.py    # 状态循环
│   ├── _checkpoint.py  # checkpoint 读写
│   ├── _io.py      # 输入输出处理
│   └── protocol.py # 协议定义
├── graph/          # 图结构
│   ├── state.py    # 状态机
│   ├── _node.py    # 节点
│   └── _branch.py  # 分支
├── _internal/     # 内部工具（_runnable.py, _serde.py 等）
└── callbacks.py    # 回调机制
```

**在 iCross 系统中的应用**：
```python
from langgraph.pregel import Pregel
from langgraph.graph import StateGraph

# 定义状态
class AgentState(TypedDict):
    messages: list
    shop_id: str | None
    current_task: str | None

# 构建图
builder = StateGraph(AgentState)
builder.add_node("agent", agent_node)
builder.add_node("tool_executor", tool_executor_node)
builder.add_edge("__start__", "agent")
builder.add_conditional_edges("agent", should_continue, {
    "continue": "tool_executor",
    "end": "__end__"
})

# 运行（支持 checkpoint 恢复）
graph = builder.compile()
result = graph.invoke({"messages": [HumanMessage(content)], "shop_id": None})
```

**与 LangChain 的关系**：
- LangGraph 是 LangChain 的底层引擎
- LangChain 的 `create_agent` 封装在 `prebuilt/` 中
- 推荐：在 iCross 中直接使用 LangGraph 的 `Pregel` 原生 API，而非通过 LangChain 封装

---

### 2.2 Dify — LLM 应用平台（参考架构）

**关键发现**：

| 特性 | 详情 |
|------|------|
| 架构 | Backend API（Flask）+ Frontend（Next.js），DDD 设计 |
| Agent 能力 | Agentic AI Workflows，RAG pipelines，模型管理 |
| 多渠道 | 内置 Agent 能力，可作为 iCross 渠道接入的参考 |
| 任务队列 | Celery + Redis（与 Dify 一致） |
| 前端国际化 | `web/i18n/en-US/` 目录，所有用户可见字符串需走 i18n |

**后端核心模块**（`api/core/`）：
```
core/
├── agent/          # Agent 核心逻辑
├── app/            # 应用配置和执行
├── llm_generator/  # LLM 调用生成
├── memory/         # 对话记忆
├── model_manager.py  # 模型管理
├── prompt/         # Prompt 模板
├── tools/          # 工具集
└── Rag/            # RAG 能力
```

**Dify 给 iCross 的启示**：
1. **多渠道接入**：Dify 的渠道设计可参考，但 Agent 能力直接用 LangGraph
2. **工作流编排**：iCross 的 Master Agent 可参考 Dify 的 workflow 设计
3. **国际化**：前端字符串必须走 i18n，避免硬编码

---

### 2.3 Next.js + Ant Design — 前端技术栈

**关键发现**：

| 组件 | 详情 |
|------|------|
| Next.js | pnpm monorepo，Turbopack 默认 bundler，App Router |
| Ant Design | 84+ React 组件，TypeScript，CSS-in-JS（`@ant-design/cssinjs`），Design Token 主题系统 |
| 国际化 | Ant Design 内置 150+ 语言支持 |
| 暗黑模式 | 内置支持，Design Token 系统 |

**关键文件**：
- `next.js/packages/next/src/` — Next.js 框架核心源码
- `next.js/packages/next/src/server/` — 服务端运行时
- `ant-design/components/` — 组件源码（每个组件 `index.tsx` + `style/`）

**iCross 前端结构**（参考三栏布局设计）：
```typescript
// 前端技术栈
const frontendStack = {
  framework: 'next.js (App Router)',
  ui: 'ant-design (CSS-in-JS + Design Token)',
  state: 'zustand / @tanstack/react-query',
  api: 'axios / SWR',
  i18n: 'next-i18next'
}
```

---

### 2.4 OzonAPI — Ozon Seller API 客户端

**关键发现**：

| 特性 | 详情 |
|------|------|
| 架构 | Mixin 模式（Pydantic 请求/响应 + 异步 HTTP） |
| 核心类 | `SellerAPI` — 组合所有 API 方法的单一入口 |
| 认证 | API Key (`client_id` + `api_key`) 或 OAuth Token |
| 限流 | 内置 `RateLimiterManager`，默认 27 QPS（可配置到 50），自动重试 |
| 重试 | `tenacity` 指数退避（`APIServerError`、`TooManyRequestsError` 自动重试） |
| 依赖 | `aiohttp`（异步 HTTP）、`pydantic`（数据验证）、`tenacity`（重试） |

**包结构**：
```
ozonapi/
├── seller/
│   ├── core/
│   │   ├── core.py          # APIManager（基类，含 _request 方法）
│   │   ├── config.py        # SellerAPIConfig
│   │   ├── rate_limiter.py  # 全局限流
│   │   ├── method_rate_limiter.py  # 按方法限流
│   │   ├── sessions.py      # aiohttp Session 管理
│   │   └── exceptions.py    # 异常类
│   └── methods/
│       ├── products/         # 商品 CRUD
│       ├── prices_and_stocks/  # 价格和库存
│       ├── fbs/             # FBS 订单
│       ├── fbo/             # FBO 订单
│       └── attributes_and_characteristics/  # 类目属性
```

**在 iCross 系统中的应用**：
```python
from ozonapi import SellerAPI, SellerAPIConfig
from contextlib import asynccontextmanager

class OzonClient:
    """iCross 专属的 Ozon 客户端封装"""

    def __init__(self, client_id: str, api_key: str):
        self.config = SellerAPIConfig(
            client_id=client_id,
            api_key=api_key,
            max_requests_per_second=27,
            max_retries=5,
            retry_min_wait=2,
            retry_max_wait=10,
        )
        self._api: SellerAPI | None = None

    @asynccontextmanager
    async def session(self):
        async with SellerAPI(config=self.config) as api:
            self._api = api
            yield api

    async def create_product(self, listing: dict) -> dict:
        """封装 product_import"""
        async with self.session() as api:
            item = self._build_import_item(listing)
            result = await api.product_import(ProductImportRequest(items=[item]))
            return {"task_id": result.task_id}
```

**关键注意事项**：
| 注意点 | 说明 |
|--------|------|
| 商品导入 | 每次最多 100 品，返回 task_id，需调用 `product_import_info` 查询结果 |
| 价格更新 | 每品每小时最多 10 次更新，注意限流 |
| 商品图片 | 必须公网可访问的 URL（JPG/PNG），最多 30 张 |

---

### 2.5 Celery — 异步任务队列

**关键发现**：

| 特性 | 详情 |
|------|------|
| 架构 | Producer → Broker(Redis) → Worker → Result Backend |
| 任务定义 | `@app.task` 装饰器，支持 `bind=True` 获取 `self` |
| 重试 | `autoretry_for` 自动重试 + `retry_backoff` 指数退避 |
| 周期任务 | `beat_schedule` 配置 + crontab 表达式 |
| 编排 | `chain`（顺序）、`group`（并行）、`chord`（并行+回调） |
| 进度 | `self.update_state(state='PROGRESS', meta={...})` |

**在 iCross 系统中的应用**：
```python
from celery import Celery, chain, group
from celery.schedules import crontab

app = Celery('icross')

@app.task(bind=True)
def batch_import(self, product_ids):
    for i, pid in enumerate(product_ids):
        import_product(pid)
        if i % 50 == 0:
            self.update_state(state='PROGRESS', meta={'current': i+1, 'total': len(product_ids)})
    return {'imported': len(product_ids)}

@app.task
def daily_price_adjust():
    products = get_products_for_adjust()
    for p in products:
        update_price(p, calculate_new_price(p))

# 定时调价（每日凌晨2点）
app.conf.beat_schedule = {
    'daily-price-adjust': {
        'task': 'daily_price_adjust',
        'schedule': crontab(hour=2, minute=0),
    },
}
```

---

### 2.6 FastAPI — Web 微服务框架

**关键发现**：

| 特性 | 详情 |
|------|------|
| 架构 | 基于 Starlette，依赖注入和自动 OpenAPI |
| 生命周期 | `lifespan` 上下文管理器（startup/shutdown） |
| WebSocket | 内置 `@app.websocket("/ws")` |
| 流式响应 | `StreamingResponse` / `EventSourceResponse`（SSE） |
| 后台任务 | `BackgroundTasks`（轻量）或 Celery（重量） |

**在 iCross 系统中的应用**：
```python
from contextlib import asynccontextmanager
from fastapi import FastAPI

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.ozon_client = OzonClient()
    yield
    await app.state.ozon_client.close()

app = FastAPI(title="iCross Agent API", lifespan=lifespan)

@app.post("/chat")
async def chat(message: str, session_id: str | None = None):
    ...
```

---

### 2.7 DrissionPage — 爬虫框架

**关键发现**：

| 特性 | 详情 |
|------|------|
| 双引擎 | `d` 模式（CDP/浏览器自动化）+ `s` 模式（requests/HTTP） |
| 核心类 | `ChromiumPage`（浏览器）、`WebPage`（双模式）、`SessionPage`（纯 HTTP） |
| 浏览器管理 | 基于 CDP 协议，WebSocket 连接，不依赖 Selenium |
| 元素定位 | 简洁语法：`page.ele('@name=xxx')`、`page.ele('text=关键词')` |

**在 iCross 系统中的应用**：
```python
from DrissionPage import ChromiumPage, ChromiumOptions

options = ChromiumOptions()
options.set_user_data_path('./chrome_data')
page = ChromiumPage(options)

page.get('https://1688.com')
page.ele('@name=keyword').input('瑜伽裤')
page.ele('text=搜索').click()

items = page.eles('.offer-list-item')
for item in items:
    print(item.ele('@class=title').text)
```

---

### 2.8 rembg — 图片去背景

**关键发现**：

| 特性 | 详情 |
|------|------|
| 架构 | Session 工厂 + ONNX Runtime 推理 |
| 核心函数 | `remove(data, session, alpha_matting, bgcolor)` |
| 推荐模型 | `birefnet-general` — 1024x1024 输入，精度最高，电商首选 |
| Alpha Matting | 开启后边缘更精细，适合商品图 |
| HTTP API | `rembg s --port 7000` 启动 REST API 服务 |

**在 iCross 系统中的应用**：
```python
from rembg import remove, new_session

session = new_session("birefnet-general")

def make_white_background(image_bytes):
    return remove(
        image_bytes,
        session=session,
        alpha_matting=True,
        alpha_matting_foreground_threshold=240,
        alpha_matting_background_threshold=10,
        bgcolor=(255, 255, 255, 255),
    )
```

---

### 2.9 Stable Diffusion WebUI — 图像生成

**关键发现**：

| 特性 | 详情 |
|------|------|
| API 启动 | `python webui.py --api --nowebui`（仅 API 模式） |
| 核心端点 | `/sdapi/v1/txt2img`（文生图）、`/sdapi/v1/img2img`（图生图） |
| 采样器 | 支持 Euler、DPM++ 2M 等多种采样器 |
| ControlNet | 通过 `--alwayson_scripts` 机制集成 |
| LoRA | 提示词语法 `</lora:name:weight>` |
| 认证 | `--api-auth username:password` 开启 API 认证 |

**在 iCross 系统中的应用**：
```python
import httpx
import base64

def txt2img(prompt, negative_prompt="", steps=30):
    resp = httpx.post("http://localhost:7860/sdapi/v1/txt2img", json={
        "prompt": prompt,
        "negative_prompt": negative_prompt,
        "steps": steps,
        "width": 512,
        "height": 768,
        "cfg_scale": 7.0,
        "sampler_name": "Euler",
    })
    data = resp.json()
    images = [base64.b64decode(img) for img in data['images']]
    return images[0]
```

---

## 三、vendor 代码与设计文档的对应关系

| 设计文档章节 | 对应 vendor | 关键实现点 |
|-------------|------------|-----------|
| Agent 对话层 | langgraph + dify | Pregel 图执行、DDD 架构 |
| 工具集 | DrissionPage + OzonAPI + rembg + SD WebUI | @tool 装饰器、异步调用 |
| Web 框架 | FastAPI | lifespan、WebSocket、SSE |
| 任务队列 | Celery | @app.task、beat_schedule |
| 前端 | Next.js + Ant Design | App Router、Design Token |

---

## 四、技术选型确认

| 模块 | 最终选型 | 理由 |
|------|----------|------|
| Agent 框架 | **LangGraph (原生 API)** | 低层编排 + 内置 checkpoint + human-in-loop，优于 LangChain 封装 |
| 多渠道接入 | Dify（参考架构） | 自研成本高，参考 Dify workflow 设计 |
| 爬虫 | DrissionPage | 双引擎（浏览器自动化 + HTTP），无需 Selenium |
| 图片去背景 | rembg | Python 原生，`birefnet-general` 精度高，HTTP API 支持 |
| 图片生成 | SD WebUI (AUTOMATIC1111) | API 成熟，ControlNet/LoRA 生态完整 |
| Ozon API 客户端 | **OzonAPI (ozonapi-async)** | 异步 + Pydantic + 内置限流重试，开源活跃 |
| 任务队列 | Celery + Redis | 分布式任务的事实标准 |
| Web 框架 | FastAPI | 轻量、异步、依赖注入、自动 OpenAPI |
| 前端 | Next.js (App Router) + Ant Design | 成熟生态，Design Token 主题系统 |
| 数据库 | PostgreSQL | 结构化数据，向量检索可加 Qdrant |

---

## 五、项目包结构设计（已更新）

基于开源项目分析，确认 iCross Agent 项目结构如下：

```
src/icross/
├── __init__.py
│
├── api/                          # FastAPI 应用
│   ├── __init__.py
│   ├── main.py                   # 应用入口，lifespan 管理
│   ├── config.py                 # 配置（Pydantic Settings）
│   ├── deps.py                   # 依赖注入
│   ├── routers/
│   │   ├── chat.py              # Agent 对话接口（/chat, WebSocket）
│   │   ├── ozon.py              # Ozon 适配器接口
│   │   ├── hub.py               # Hub 管理接口
│   │   └── tasks.py             # 任务状态接口
│   └── schemas/                 # Pydantic 模型
│       ├── chat.py
│       ├── ozon.py
│       └── hub.py
│
├── agents/                       # Agent 层
│   ├── __init__.py
│   ├── master/                  # Master Agent（LangGraph Pregel）
│   │   ├── __init__.py
│   │   ├── graph.py            # 状态图定义
│   │   └── nodes.py            # 节点实现
│   ├── product_selection/       # 选品子 Agent
│   ├── copywriting/             # 文案子 Agent
│   └── ad_management/           # 广告子 Agent
│
├── tools/                        # LangChain Tools（@tool 装饰器）
│   ├── __init__.py
│   ├── base.py                 # 工具基类和公共逻辑
│   ├── crawler/
│   │   └── hot_product.py      # DrissionPage 爬虫工具
│   ├── ozon/
│   │   ├── product.py          # ozon_product_create/list
│   │   ├── price.py            # ozon_update_price
│   │   └── ad.py               # ozon_ad_create/manage
│   ├── image/
│   │   ├── remove_bg.py        # rembg 去背景
│   │   └── generate.py          # SD WebUI 生成
│   └── pricing/
│       └── auto_pricing.py     # 自动定价
│
├── services/                     # 外部服务封装
│   ├── __init__.py
│   ├── ozon_client.py          # OzonAPI 封装（异步上下文管理器）
│   ├── crawler_service.py      # DrissionPage 爬虫服务
│   ├── sd_service.py           # Stable Diffusion HTTP API
│   └── rembg_service.py        # rembg HTTP API 或直接调用
│
├── core/                         # 核心基础设施
│   ├── __init__.py
│   ├── llm/
│   │   ├── __init__.py
│   │   ├── factory.py          # LLM 工厂（模型路由）
│   │   ├── gpt4.py
│   │   ├── claude.py
│   │   └── deepseek.py
│   ├── memory/
│   │   ├── __init__.py
│   │   ├── manager.py          # Session-Memory 绑定
│   │   └── chat_history.py     # 对话历史管理
│   └── callbacks/
│       ├── __init__.py
│       ├── logging.py          # 数据库日志回调
│       └── streaming.py        # WebSocket 流式回调
│
├── db/                           # 数据库层
│   ├── __init__.py
│   ├── base.py                 # SQLAlchemy base
│   ├── session.py              # async session
│   └── models/                 # ORM 模型
│
├── tasks/                        # Celery 任务
│   ├── __init__.py
│   ├── celery_app.py           # Celery 配置
│   ├── batch_import.py         # 批量上架
│   ├── price_adjust.py         # 定时调价
│   └── image_gen.py            # 图片生成队列
│
└── utils/                        # 工具函数
    ├── __init__.py
    └── price_calculator.py     # 定价公式

vendors/                          # 开源项目源码（已克隆）
├── langgraph/                   # LangGraph
├── dify/                        # Dify（参考）
├── next.js/                     # Next.js
├── ant-design/                  # Ant Design
├── OzonAPI-main/                # OzonAPI
├── celery/                      # Celery
├── fastapi/                     # FastAPI
├── rembg/                       # rembg
├── DrissionPage/                # DrissionPage
└── stable-diffusion-webui/     # SD WebUI

frontend/                        # Next.js 前端（待实现）
├── src/
│   ├── app/                    # App Router
│   ├── components/             # 组件（三栏布局等）
│   └── i18n/                   # 国际化
├── package.json
└── next.config.js

tests/
├── unit/
├── integration/
└── e2e/

docs/                            # 文档
├── Requirements.md
├── Design.md
└── research.md
```

---

## 六、关键实现模式

### 6.1 LangGraph Pregel Agent 实现

```python
from langgraph.pregel import Pregel
from langgraph.graph import StateGraph, START, END
from typing import TypedDict

class AgentState(TypedDict):
    messages: list[BaseMessage]
    shop_id: str | None
    task_result: dict | None

def agent_node(state: AgentState) -> AgentState:
    """主 Agent 节点"""
    response = llm.invoke(state["messages"])
    return {"messages": [response]}

def tool_node(state: AgentState) -> AgentState:
    """工具执行节点"""
    last_msg = state["messages"][-1]
    if last_msg.tool_calls:
        for tool_call in last_msg.tool_calls:
            result = tool_executor.invoke(tool_call)
            state["messages"].append(ToolMessage(content=str(result), tool_call_id=tool_call.id))
    return state

builder = StateGraph(AgentState)
builder.add_node("agent", agent_node)
builder.add_node("tools", tool_node)
builder.add_edge(START, "agent")
builder.add_conditional_edges("agent", should_continue, {
    "continue": "tools",
    "end": END
})
builder.add_edge("tools", "agent")

graph = builder.compile()

# 支持 checkpoint 恢复
from langgraph.checkpoint.memory import MemorySaver
checkpointer = MemorySaver()
graph = builder.compile(checkpointer=checkpointer)
```

### 6.2 Ozon Client 封装

```python
from ozonapi import SellerAPI, SellerAPIConfig
from contextlib import asynccontextmanager

class OzonClient:
    def __init__(self, client_id: str, api_key: str):
        self.config = SellerAPIConfig(
            client_id=client_id,
            api_key=api_key,
            max_requests_per_second=27,
        )

    @asynccontextmanager
    async def session(self):
        async with SellerAPI(config=self.config) as api:
            yield api

    async def create_product(self, listing: dict) -> str:
        async with self.session() as api:
            item = self._build_import_item(listing)
            result = await api.product_import(ProductImportRequest(items=[item]))
            return result.task_id
```

### 6.3 工具定义（@tool 装饰器）

```python
from langchain_core.tools import tool

@tool
def ozon_product_create(listing: dict, shop_id: str) -> str:
    """在 Ozon 店铺创建商品

    Args:
        listing: 商品信息（标题、描述、价格等）
        shop_id: 店铺 ID

    Returns:
        商品 ID 或错误信息
    """
    shop = get_shop(shop_id)
    client = OzonClient(shop.client_id, shop.api_key)
    return await client.create_product(listing)

@tool
def generate_product_image(product_desc: str, style: str = "professional") -> list[str]:
    """生成商品场景图

    Args:
        product_desc: 商品描述
        style: 场景风格（professional/casual/luxury）

    Returns:
        图片 URL 列表
    """
    # rembg 去背景 -> SD WebUI 生成 -> 返回 URL
    ...
```

---

## 七、待补充项目

以下项目已克隆完成，无需补充：
- ✅ LangGraph — `vendors/langgraph/`
- ✅ Dify — `vendors/dify/`
- ✅ Next.js — `vendors/next.js/`
- ✅ Ant Design — `vendors/ant-design/`
- ✅ OzonAPI — `vendors/OzonAPI-main/`
- ✅ Celery — `vendors/celery/`
- ✅ FastAPI — `vendors/fastapi/`
- ✅ rembg — `vendors/rembg/`
- ✅ DrissionPage — `vendors/DrissionPage/`
- ✅ Stable Diffusion WebUI — `vendors/stable-diffusion-webui/`

---

## 八、开发行动计划（更新版）

### Phase 1：核心骨架（2-3周）

1. **初始化项目**
   ```bash
   mkdir -p src/icross
   uv init --name icross-agent
   ```

2. **LangGraph Agent 集成**
   - 引入 `vendors/langgraph/libs/langgraph`
   - 实现第一个 Tool（echo/calculator）
   - 跑通 `Pregel` + `StateGraph`
   - 支持 checkpoint（MemorySaver）

3. **FastAPI 网关**
   - `/chat` 接口
   - WebSocket 流式输出
   - Session 管理

4. **前端三栏布局**
   - 克隆 `next.js` + `ant-design`
   - 基础页面结构

5. **验证**：Agent 能调用计算器工具并返回结果

### Phase 2：Ozon 基础运营（4周）

1. **OzonAPI 封装**
   - `OzonClient` 实现
   - `product_import`、`product_list`、`product_import_prices`

2. **Agent Tools**
   - `ozon_product_create`
   - `ozon_product_list`
   - `ozon_update_price`

3. **Hub 极简版**
   - 草稿审核页面

### Phase 3：智能选品与 Listing（3周）

1. **DrissionPage 爬虫**
   - 1688/拼多多热销抓取
   - 登录态、反爬处理

2. **Tools**
   - `search_hot_product`
   - `generate_listing`（Claude 俄语）

3. **Hub 选品中心**

### Phase 4：视觉自动化与智能调价（3周）

1. **rembg 集成**
   - `remove_background` Tool

2. **SD WebUI 集成**
   - `generate_product_image` Tool

3. **Celery 任务队列**
   - 批量上架
   - 定时调价

### Phase 5：全托管与广告（2周）

1. **广告 Tools**
   - `ozon_ad_create`
   - `ozon_ad_manage`

2. **Master Agent 编排**

3. **多渠道接入**
   - Telegram Bot

---

## 九、附录：vendor CLAUDE.md 摘要

| vendor | 关键指导 |
|--------|---------|
| **langgraph** | monorepo 结构；`libs/langgraph/langgraph/` 是核心；运行 `make format/lint/test` |
| **dify** | DDD + Clean Architecture；后端 `api/core/`；异步通过 Celery；前端字符串走 i18n |
| **next.js** | pnpm monorepo；Turbopack 默认；`packages/next/src/` 是源码；`pnpm build-all` 全量构建 |
| **ant-design** | TypeScript + CSS-in-JS；组件在 `components/component-name/`；绝对路径导入 `antd/es/*` |