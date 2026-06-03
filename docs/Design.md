# iCross Agent 智能电商运营系统 — 产品设计文档

> **版本**：v1.1
> **日期**：2026-05-04
> **状态**：Phase 1-2 开发完成，Phase 3 开发中
> **作者**：iCross Agent 团队

---

## 目录

1. [产品概述与愿景](#1-产品概述与愿景)
2. [用户研究与用户故事](#2-用户研究与用户故事)
3. [MVP 定义](#3-mvp-定义)
4. [产品功能规格](#4-产品功能规格)
5. [系统架构设计](#5-系统架构设计)
6. [详细技术设计](#6-详细技术设计)
7. [数据模型设计](#7-数据模型设计)
8. [API 契约设计](#8-api-契约设计)
9. [前端界面设计](#9-前端界面设计)
10. [错误处理与容错策略](#10-错误处理与容错策略)
11. [安全模型](#11-安全模型)
12. [项目工程结构](#12-项目工程结构)
13. [分阶段开发计划](#13-分阶段开发计划)
14. [技术依赖清单](#14-技术依赖清单)
15. [部署与运维](#15-部署与运维)
16. [前端可配置化设计](#16-前端可配置化设计)
17. [附录](#附录)

---

## 1. 产品概述与愿景

### 1.1 产品定位

**iCross Agent** 是一个面向中小型跨境电商卖家的 AI 运营智能体，通过自然语言对话方式，实现 Ozon 店铺的半自动/全自动托管运营。

核心理念：**"下达经营目标，Agent 自主执行"**。运营人员只需描述目标（如"本月利润目标 10 万，主推瑜伽裤"），Agent 自动完成选品、生成 Listing、生成商品图、自动上架、智能定价、广告投放全流程。

### 1.2 目标用户画像

| 属性 | 描述 |
|------|------|
| **用户类型** | 中小型跨境电商卖家 |
| **运营规模** | 1~5 个 Ozon 店铺 |
| **团队构成** | 夫妻店/2~3 人小团队，无专职技术人员 |
| **核心痛点** | 人工上架耗时长、文案质量差、定价凭经验、广告不会投 |
| **技术能力** | 缺乏 AI 和编程能力，但会用电脑和手机 |
| **付费意愿** | 愿意为显著提效的工具付费 |
| **使用场景** | 日常运营、选品开发、新品上架、促销调价 |

### 1.3 产品价值主张

| 维度 | 现状（人工） | 使用 iCross Agent |
|------|------------|-------------------|
| **选品** | 手动搜索 + 经验判断，耗时 2~4h/天 | Agent 自动抓取 + 分析，5 分钟 |
| **Listing 生成** | 人工翻译 + 编写，30~60min/品 | Agent 生成俄语文案，2 分钟 |
| **商品图** | 找工厂图或付费拍摄，3~7 天 | AI 生成场景图，5 分钟 |
| **上架** | 后台手动填写，20~30min/品 | Agent 一键上架，实时完成 |
| **定价** | 参考竞品手动调价 | Agent 规则引擎自动定价 + 每日调价 |
| **广告** | 凭经验投放，效果不稳定 | Agent 智能投放 + ACOS 优化 |

### 1.4 产品原则

- **按阶段闭环**：每个阶段交付可独立验证价值的产品，不追求一步到位
- **开源主导**：核心能力基于成熟开源项目二次开发，不重复造轮子
- **效果优先**：AI 模型预算无上限，优先使用最强模型
- **人工可控**：关键操作节点必须人工确认，Agent 不做不可逆决策
- **渐进自动化**：从人工主导 → 人工复核 → 半自动 → 全自动，层层递进

---

## 2. 用户研究与用户故事

### 2.1 用户典型一天

```
早上 9:00  打开 iCross Agent，查看仪表盘 KPI
           → 发现昨天 GMV 1.2 万卢布，广告 ACOS 18%

9:05       对 Agent 说："帮我找最近 1688 上卖得好的瑜伽裤"
           → Agent 返回 Top 20 热销品列表

9:10       选中一款瑜伽裤，说："帮我生成 Listing 并上架到店铺 A"
           → Agent 生成俄语文案 + 场景图 + 草稿上架
           → 草稿进入 Hub 待审核，运营点击确认发布

10:30      查看 Hub 选品中心，发现 Agent 推荐的候选品
           → 采纳 3 个商品，推送给 Agent 生成 Listing

下午 14:00  查看 Hub 广告看板，发现一款商品 ACOS 高达 35%
           → 对 Agent 说："帮我把这个商品的广告 ACOS 降到 20%"
           → Agent 自动调高出价或暂停低效关键词

17:00      收到 Telegram 周报："本周自动上架新品 8 个，
           调整价格 23 次，广告 ACOS 平均下降 5%"
```

### 2.2 用户故事（User Stories）

| # | 角色 | 用户故事 | 验收标准 |
|---|------|----------|----------|
| US-01 | 运营人员 | 作为运营人员，我希望通过自然语言让 Agent 完成商品上架，这样我不用学习 Ozon 后台复杂操作 | Agent 听懂"上架瑜伽裤到店铺A"，并成功在 Ozon 创建商品 |
| US-02 | 运营人员 | 作为运营人员，我希望 Agent 能自动从 1688 找到热销品，这样我不用手动搜索 | Agent 返回 1688 热销商品列表，包含价格/销量/店铺信息 |
| US-03 | 运营人员 | 作为运营人员，我希望 Agent 生成符合 Ozon SEO 的俄语文案，这样我不用自己翻译 | 生成的 Listing 包含俄语标题（SEO 友好）、描述、关键词 |
| US-04 | 运营人员 | 作为运营人员，我希望 Agent 生成商品场景图，这样我不用花钱请人拍摄 | Agent 生成模特/场景图，可选去除背景 |
| US-05 | 运营人员 | 作为运营人员，我希望 Agent 自动帮我设定商品价格，这样我不用手动计算 | Agent 基于成本+毛利率自动定价，并支持竞品跟踪 |
| US-06 | 运营人员 | 作为运营人员，我希望 Agent 每天自动调整价格，这样我不用每天盯盘 | Celery 定时任务每日检查竞品价格，按规则调价 |
| US-07 | 运营人员 | 作为运营人员，我希望 Agent 自动创建和管理广告，这样我不用手动投放 | Agent 创建 Ozon 搜索广告，支持出价调整 |
| US-08 | 运营人员 | 作为运营人员，我希望在 Hub 后台审核 Agent 生成的草稿，这样最终决定权在我手里 | Hub 显示草稿列表，支持"发布"/"修改"/"驳回"操作 |
| US-09 | 运营人员 | 作为运营人员，我希望通过 Telegram 与 Agent 交互，这样我在外出时也能管理店铺 | Telegram 消息与 Web 端 Session 互通 |
| US-10 | 运营人员 | 作为运营人员，我希望看到 Agent 执行任务的思考过程，这样我知道它在做什么 | Hub 日志中心展示 Agent 思考链和工具调用详情 |
| US-11 | 店铺所有者 | 作为店铺所有者，我希望能收到每周自动报告，这样我不用每天盯着 | 每周一 9:00 Telegram 推送周报 |
| US-12 | 运营人员 | 作为运营人员，我希望切换店铺后对话历史跟着切换，这样不同店铺的操作互不干扰 | 切换店铺后，Session 列表按该店铺过滤 |
| US-13 | 运营人员 | 作为运营人员，我希望在后台配置全局运营策略（品牌定位、毛利率、定价规则），这样系统能按我的思路自动决策 | 修改策略后 Agent 下次执行自动生效 |
| US-14 | 运营人员 | 作为运营人员，我希望在后台新增/删除公司（租户），这样我无需手动创建目录和配置文件 | 前端创建公司后自动生成目录和默认配置 |
| US-15 | 运营人员 | 作为运营人员，我希望在后台新增/编辑店铺配置（API Key、品牌定位、库存策略），这样不再需要手动编辑 JSON 文件 | 前端保存后即时写入配置文件 |
| US-16 | 运营人员 | 作为运营人员，我希望在前端用 Markdown 编辑器修改运营策略文档，并支持实时预览，这样我的策略调整能立即生效 | 保存后策略文件直接覆盖，Agent 下次读取即更新 |

### 2.3 竞品分析

| 竞品 | 优点 | 缺点 | iCross Agent 的差异化 |
|------|------|------|----------------------|
| **店小秘** | ERP 功能全，用户多 | 无 AI 能力，操作繁琐 | AI 原生，Agent 对话驱动 |
| **芒果店长** | 简单易用 | 无选品/文案生成能力 | Agent 自动化选品和文案 |
| **ChatGPT** | AI 能力强大 | 无电商工具集成，无法直接操作 Ozon | 深度集成 Ozon API，Agent 直接执行 |
| **Jungle Scout** | 选品数据专业 | 贵，按月订阅 | 开源+AI，选品不收费 |

---

## 3. MVP 定义

### 3.1 MVP 范围

**MVP 定位**：验证 Agent 对话 + 单一工具调用的核心闭环。

MVP 不包含：Hub 后台、选品爬虫、图片生成、Celery 定时任务。

### 3.2 MVP 功能清单

| 功能 | 描述 | 验证指标 |
|------|------|----------|
| **M1** 三栏布局 Web 前端 | 纯静态 HTML，无后端连接 | 前端正常渲染 |
| **M2** Agent Echo 对话 | 接入 Hermes-style Agent，Agent 返回固定/简单回答 | 对话正常响应 |
| **M3** 简单工具调用 | Agent 调用一个示例工具（如计算器/时间查询） | 工具调用链路打通 |
| **M4** Session 管理 | 多轮对话保存，切换 Session | Session 切换正常 |
| **M5** 店铺选择器 | 右侧下拉选择店铺（静态数据） | 切换后界面更新 |

### 3.3 MVP 验收条件

- [ ] 用户可在 Web 界面与 Agent 对话
- [ ] Agent 能调用一个简单工具（如"算 100*23"返回 2300）
- [ ] 支持多轮对话，Agent 记住上下文
- [ ] 前端三栏布局正常展示
- [ ] 切换店铺后 Session 列表跟着变化

### 3.4 Out of Scope（第一版不做）

以下功能明确不在 MVP 和第一阶段范围内：

- Hub 中控后台（商品管理、选品中心、利润看板等）
- 选品爬虫（1688/拼多多）
- 图片生成（SD WebUI）
- 图片去背景（rembg）
- Celery 定时任务
- Telegram/企业微信/钉钉渠道接入
- 广告管理
- 多 Agent 编排
- 多模型路由

---

## 4. 产品功能规格

### 4.1 Agent 对话层功能规格

#### 4.1.1 核心工具集

| Tool 名称 | 类型 | 输入参数 | 输出 | 人工确认点 |
|-----------|------|----------|------|-----------|
| `search_hot_product` | 爬虫 | `keyword: str, platform: str["1688"/"pinduoduo"], limit: int` | 热销商品 JSON 列表 | 无 |
| `generate_listing` | LLM | `product_info: JSON, language: str, template: str` | 俄语 Listing JSON | 上架前 |
| `generate_product_image` | SD+rembg | `product_desc: str, style: str, count: int` | 图片 URL 列表 | 选择图片后 |
| `ozon_product_create` | API | `listing: JSON, images: list[str], price: float` | Ozon 商品 ID | **上架前强制确认** |
| `ozon_product_list` | API | `shop_id: str, limit: int, offset: int` | 商品列表 JSON | 无 |
| `ozon_update_price` | API | `product_id: str, new_price: float` | 更新结果 | 价格变动 >10% 时确认 |
| `ozon_ad_create` | API | `product_id: str, budget: float, acos_target: float` | 广告活动 ID | **创建前强制确认** |
| `ozon_ad_manage` | API | `campaign_id: str, action: str, bid: float` | 操作结果 | 出价调整 >20% 时确认 |
| `auto_pricing` | 规则 | `cost: float, margin: float, competitor_price: float` | 建议售价 | 无（可配置） |
| `scheduled_price_adjustment` | Celery | `rule_id: str, schedule: str` | 定时任务 ID | 无 |
| `master_agent` | 聚合 | `user_goal: str, shop_id: str` | 执行报告 JSON | **每个关键节点确认** |

#### 4.1.2 多模型路由策略

| 任务类型 | 模型 | 场景 |
|----------|------|------|
| 文案生成 | Claude Sonnet 4 | 高质量俄语文案、俄语 SEO 优化 |
| 策略决策 | DeepSeek Chat / GPT-4 | 选品分析、定价策略、竞品分析 |
| 简单执行 | GPT-3.5 Turbo | 工具调用、状态查询、价格更新 |
| 特殊场景 | GPT-4o | 图片描述生成（给 SD 的 prompt） |

#### 4.1.3 人工确认点（Human-in-the-Loop）

以下操作必须经人工确认才能执行：

1. **商品上架** — Agent 生成草稿 → Hub 待审核 → 人工确认 → 实际发布
2. **广告创建** — Agent 生成方案 → 用户确认预算/ACOS 目标 → 创建
3. **价格大幅调整** — 价格变动超过 ±10% → 用户确认
4. **商品删除/下架** — 所有下架操作 → 用户确认

#### 4.1.4 禁止执行的操作（安全边界）

Agent 不得执行以下操作：

- 单次操作超过 50 个商品
- 价格调整为负数或零
- 删除店铺
- 修改店铺 API Key
- 跨店铺操作（未明确指定店铺时拒绝）

### 4.2 Hub 中控后台功能规格

#### 4.2.1 仪表盘

**KPI 卡片区**：

| 指标 | 数据来源 | 刷新频率 |
|------|----------|----------|
| 今日/本周/本月 GMV | Ozon API 订单数据 | 实时 |
| 订单数 | Ozon API 订单数据 | 实时 |
| 毛利润 | 订单数据 - 成本 - 佣金 - 物流 | 每日 |
| 广告花费 | Ozon 广告 API | 实时 |
| ACOS | 广告花费 / GMV | 实时 |

**店铺状态卡片**：

- 店铺名称 + Logo
- API 连接状态（正常/异常/授权过期）
- 上架商品数量
- 店铺评分

**Agent 执行摘要**：

- 今日自动任务数（自动上架/自动调价/自动广告）
- 待处理草稿数（需人工确认）

**告警流**：

- 高优先级：API 连接异常、商品审核被拒、ACOS 飙高 >40%
- 中优先级：库存预警、定时任务失败
- 低优先级：Listing 模板变更、新功能上线

#### 4.2.2 商品管理中心

**线上商品列表**：

| 列 | 说明 |
|-----|------|
| 商品图片 | 缩略图 |
| 标题 | 俄语标题 |
| SKU | Ozon SKU |
| 当前价格 | 卢布 |
| 库存 | 数量 |
| 状态 | 上架/下架/草稿 |
| 近 7 天销量 | 自动汇总 |
| 转化率 | 浏览→下单 |
| 操作 | 改价/下架/编辑 |

**草稿箱**（Agent 产出）：

- 卡片展示：商品图 + 标题 + 价格建议 + 来源链接
- 操作：一键发布 / 编辑后发布 / 驳回（附原因）

**图片素材库**：

- 按商品/风格/用途分类
- 支持搜索和预览
- 状态：已使用 / 待使用

#### 4.2.3 选品中心

**热销榜单**：

- 来源标签（1688 / 拼多多）
- 商品卡片（图 + 标题 + 价格 + 销量 + 店铺）
- 数据更新时间

**候选品详情**：

- 价格走势折线图
- 1688 同款比价
- Ozon 竞争分析（搜索结果数 + 头部均价 + 头部销量）

**操作按钮**：

- **采纳** → 推送 Agent 生成 Listing
- **忽略** → 不再推荐同类
- **关注** → 持续监控价格

#### 4.2.4 任务与日志中心

**任务历史**：

| 列 | 说明 |
|-----|------|
| 任务 ID | 唯一标识 |
| 任务类型 | 选品/上架/调价/广告 |
| 发起方式 | 用户指令 / 定时自动 |
| 店铺 | 所属店铺 |
| 目标商品 | 商品 ID 或关键词 |
| 开始时间 | - |
| 耗时 | 秒数 |
| 状态 | 执行中/成功/失败/待确认 |
| 操作 | 查看详情/重试/停止 |

**任务详情**（点击展开）：

- Agent 思考链（每一步的 Thought）
- 调用的工具及参数
- 工具返回结果
- 耗时分布

**错误日志**：

- 高��错误码和错误信息
- 重试次数
- 一键重试按钮

#### 4.2.5 系统配置中心

**设计原则**：所有配置通过 Web UI 管理，后端自动读写本地 JSON/MD 文件，无需手动编辑文件系统。

**公司（租户）管理**：

- 列表展示所有电商公司（租户）
- 新增公司：弹窗填写公司名、Ozon API Key、通知邮箱等
- 每个公司包含独立配置目录 `tenants/{company_id}/`
- 删除公司时同时清理对应目录

**店铺管理**（公司级）：

- 在选定公司下查看所有店铺
- 新增店铺：弹窗输入店铺 ID、品牌定位等（可继承公司默认值）
- 每个店铺包含独立配置子目录 `tenants/{company_id}/stores/{store_id}/`

**店铺授权**（原店铺级）：

- 添加/编辑/删除店铺
- 输入 Client ID + API Key
- 测试连接按钮
- 授权范围展示

**公司级策略配置**（`config.json`）：

| 字段 | 类型 | 说明 |
|------|------|------|
| brand_positioning | enum | 品牌定位：高端/性价比/niche |
| target_margin | float | 目标毛利率（0~1） |
| auto_pricing_enabled | bool | 自动定价开关 |
| min_price_coefficient | float | 最低价格系数 |
| max_price_coefficient | float | 最高价格系数 |
| competitor_strategy | enum | 竞品跟随策略：领先/滞后/忽略 |
| listing_tone | enum | Listing语气：专业/友好/数据驱动 |
| stock_buffer_days | int | 库存缓冲天数 |

**公司级策略文档**（`strategy.md`）：

- Markdown 格式自由编写
- 前端提供富文本/Markdown 编辑器 + 实时预览
- 内容直接写入 `strategy.md`，Agent 调用时读取

**自动化策略**（原店铺级）：

- 定价规则：默认成本毛利率（默认 30%）、最低限价、最高限价
- 调价触发：频率（每日/每小时）、是否跟踪竞品底价、价格变动上限（±%）
- 广告规则：ACOS 目标值、出价上限、异常关停阈值（ACOS>40% 自动暂停）

**模型配置**：

- 各任务类型的模型选择
- API Key 管理

### 4.3 典型业务场景

#### 全托管流程（端到端）

```
用户指令 → Agent解析 → 选品(1688/拼多多)
         → 生成Listing(LLM俄语文案)
         → 生成商品图(SD场景图+去背景)
         → 用户确认/自动上架(Ozon)
         → 自动定价(成本+30%)
         → 开启广告
         → 定时调价监控
```

#### 场景 1：半自动上架

> 用户："在 Ozon 店铺 A 上架一个新品，标题是瑜伽裤，价格 999 卢布"
> → Agent 调用接口完成上架

#### 场景 2：AI 驱动选品上架

> 用户："找 1688 上最近卖得好的瑜伽裤，帮我生成 Ozon Listing 并上架"
> → 展示选品列表 → 生成文案预览 → 一键发布

#### 场景 3：全托管经营

> 用户："本月利润目标 10 万卢布，主推瑜伽裤"
> → Agent 自主执行选品、上架、调价、广告投放，定期输出报告

---

## 5. 系统架构设计

### 5.1 整体架构图

```
┌──────────────────────────────────────────────────────────────────────────────┐
│                              客户端层                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐                      │
│  │ Web 前端  │  │ Telegram │  │ 企业微信  │  │  钉钉    │                      │
│  │ (HTML)   │  │   Bot    │  │   Bot    │  │   Bot    │                      │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘                      │
└───────┼─────────────┼─────────────┼─────────────┼──────────────────────────────┘
        │ WebSocket   │           │           │
        └─────────────┴───────────┴───────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                            网关层                                             │
│  ┌─────────────────────────────────────────────────────────────────────────┐  │
│  │                      FastAPI Gateway                                   │  │
│  │  • WebSocket /chat (Agent 流式输出)                                    │  │
│  │  • REST API (Session / Shop / Product / Draft CRUD)                   │  │
│  │  • 配置管理 API (Tenant / Store 配置读写)                               │  │
│  │  • 文件服务 (前端静态文件)                                              │  │
│  └─────────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
                         │
           ┌─────────────┼─────────────┐
           ▼             ▼             ▼
┌──────────────────┐ ┌───────────┐ ┌──────────────┐
│  LangGraph       │ │ REST API │ │ OzonAdapter  │
│  Agent            │ │ (CRUD)   │ │  客户端      │
│                  │ │          │ │              │
│  • create_react_agent│ │  商品    │ │  • product   │
│  • AsyncPostgresSaver│ │  订单    │ │  • price     │
│  • Human-in-loop  │ │  选品    │ │  • ad        │
│  • ToolNode 调用   │ │  配置    │ │  • analytics │
│  • 流式输出       │ │  仪表盘  │ │              │
└────────┬─────────┘ └─────┬─────┘ └──────┬───────┘
         │                  │             │
         ▼                  ▼             ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                            服务层                                             │
│  ┌───────────────┐  ┌─────────────┐  ┌──────────────┐  ┌─────────────────┐   │
│  │ 外部 LLM 服务  │  │ 任务队列    │  │ 爬虫服务     │  │ 图片服务        │   │
│  │               │  │             │  │              │  │                 │   │
│  │ • MiniMax     │  │ Celery +    │  │ DrissionPage │  │ • rembg         │   │
│  │ • Claude      │  │   Redis     │  │              │  │ • SD WebUI API  │   │
│  │ • DeepSeek    │  │             │  │ 1688/拼多多  │  │                 │   │
│  └───────────────┘  └─────────────┘  └──────────────┘  └─────────────────┘   │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐  │
│  │                         数据与存储层                                   │  │
│  │  PostgreSQL (产品/会话/店铺) │ Redis (Session/Cache) │ 本地文件系统    │  │
│  │                                                     │ tenants/{id}/   │  │
│  │                                                     │   config.json   │  │
│  │                                                     │   strategy.md   │  │
│  │                                                     │   stores/{}/    │  │
│  └──────────────────────────────────────────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────────────────────────┐
│                           外部服务                                           │
│   Ozon API        1688/拼多多       DeepSeek API     Claude API   MiniMax API │
└──────────────────────────────────────────────────────────────────────────────┘
```

### 5.2 数据流设计

#### 5.2.1 Agent 对话数据流

```
用户输入 → Gateway → Agent 服务
                    │
                    ├── LLM (意图理解)
                    │       ↓
                    ├── 选择 Tool
                    │       ↓
                    ├── 执行 Tool（爬虫/Ozon API/图片生成）
                    │       ↓
                    ├── Callback 写入任务日志
                    │       ↓
                    └── LLM (生成回复 + 流式输出)
                            │
                    WebSocket ← Gateway
                            │
                         前端展示
```

#### 5.2.2 图片生成数据流

```
用户请求
    ↓
Tool: generate_product_image
    ↓
Step 1: rembg 去背景
    → 输入：源商品图
    → 输出：透明背景 PNG (birefnet-general 模型)
    ↓
Step 2: Stable Diffusion 生成场景图
    → 输入：商品描述 prompt + 透明底图（ControlNet Canny）
    → 输出：带场景的商品图（base64）
    ↓
Step 3: 可选再次 rembg 精修
    ↓
Step 4: 上传至文件存储（MinIO/本地）
    ↓
Step 5: 返回图片 URL
    ↓
Ozon 上架时使用图片 URL
```

#### 5.2.3 定时调价数据流

```
Celery Beat（每日凌晨 2:00）
    ↓
定时任务：scheduled_price_adjustment
    ↓
查询所有启用了自动调价的商品
    ↓
对于每个商品：
    ├─ 获取当前价格
    ├─ 获取竞品均价（Ozon market-analysis API）
    ├─ 计算新价格（规则：竞品均价 × 0.98，限价保护）
    ├─ 价格变动 >±5%？
    │   ├─ 是 → 写入价格调整草稿（需人工确认）
    │   └─ 否 → 直接执行 ozon_update_price
    └─ 记录调价日志
    ↓
发送调价报告（Slack/邮件）
```

### 5.3 服务间依赖关系

```
前端 (Next.js)
  └── Gateway (FastAPI)
        ├── Agent 服务
        │     ├── LLM (外部)
        │     ├── OzonAdapter
        │     ├── 爬虫服务
        │     └── 图片服务
        │           ├── rembg (本地)
        │           └── SD WebUI (本地/远程)
        ├── Hub API
        │     └── PostgreSQL
        └── OzonAdapter
              ├── Celery Worker
              │     └── Redis
              └── PostgreSQL

所有服务通过 Redis 共享 Session 状态
```

---

## 6. 详细技术设计

### 6.1 Agent 技术设计

#### 6.1.1 Agent 框架选型

**核心结论**：使用 **LangGraph `create_react_agent`** 作为 Agent 执行框架。

| 方案 | 推荐度 | 理由 |
|------|--------|------|
| **LangGraph Pregel** | ✅ 已采用 | LangGraph Pregel 图执行引擎 + 条件边，内置 checkpointer 实现 Session 持久化，ToolNode 自动处理工具调用 |
| Hermes-style While-Loop | 次选 | 轻量简单，但缺少原生流式输出、checkpoint、并发控制等 |
| LangChain create_agent | 不推荐 | 封装过度，灵活性降低 |

LangGraph Agent 的核心特点：
- **Pregel 图执行引擎**：有向图执行，支持条件边和并行节点
- **`create_react_agent`**：预置 ReAct 模式 Agent，支持 `bind_tools()` + ToolNode
- **checkpointer**：通过 `AsyncPostgresSaver` 实现 PostgreSQL 持久化
- **`astream`**：原生流式输出支持，适合 WebSocket 实时展示
- **Human-in-the-loop**：通过 tool call 拦截实现人工确认

#### 6.1.2 Master Agent 执行流程

```python
from langgraph.prebuilt import create_react_agent
from icross.agents.master.agent import create_agent, init_checkpointer
from icross.agents.master.llm import LLMType, create_llm

# 初始化 checkpointer（启动时调用一次）
await init_checkpointer()

# 创建 Agent
agent = create_agent(llm_type=LLMType.MINIMAX)

# 调用 Agent
config = {"configurable": {"thread_id": "session-123"}}
result = agent.invoke(
    {"messages": [HumanMessage(content="查看店铺数据")]},
    config
)
```

**内部执行流程**（LangGraph Pregel）：

```
用户输入 → create_react_agent 执行图
    │
    ├── [LLM 节点] 调用 bind_tools() 的 LLM
    │       ↓
    ├── 判断 Tool Calls
    │   ├── 无 → 返回 AI 消息，结束
    │   └── 有 → 进入 ToolNode
    │           ↓
    │   ├── [ToolNode] 并行执行所有工具
    │   │       ↓
    │   ├── 工具结果返回 LLM 节点
    │   │       ↓
    │   └── 重复直至无工具调用或达到最大迭代次数
    │
    └── checkpointer 自动保存状态
```

**多模型工厂**（`icross/agents/master/llm.py`）：

支持 MiniMax（主）、Anthropic Claude（备）、DeepSeek（备）三种模型：

```python
class LLMType(Enum):
    MINIMAX = "minimax"       # 主模型（MiniMaxChat）
    CLAUDE = "claude"         # 备用（ChatAnthropic）
    DEEPSEEK = "deepseek"     # 备用（ChatDeepSeek）

def create_llm(llm_type: LLMType, temperature=0.7, max_tokens=2048):
    # 根据类型返回对应的 LangChain ChatModel
    ...
```

#### 6.1.3 工具集（Phase 3 已实现）

使用 LangChain `@tool` 装饰器定义所有 Agent 工具，通过 `bind_tools()` 绑定到 LLM：

```python
from langchain_core.tools import tool

# ── Ozon 工具 (Phase 2) ──────────────────────────────────
@tool
def ozon_product_list(shop_id: str, limit: int = 20) -> str: ...

@tool
def ozon_product_info(product_id: str) -> str: ...

@tool
def ozon_update_price(product_id: str, new_price: float) -> str: ...

@tool
def ozon_update_stock(product_id: str, stock: int) -> str: ...

@tool
def ozon_analytics_stocks(shop_id: str) -> str: ...

@tool
def ozon_order_list(shop_id: str, days: int = 7) -> str: ...

@tool
def ozon_seller_info(shop_id: str) -> str: ...

@tool
def ozon_get_warehouses(shop_id: str) -> str: ...

# ── 选品工具 (Phase 3) ──────────────────────────────────
@tool
def search_1688_products(keyword: str, page: int = 1, page_size: int = 20) -> str:
    """搜索1688热卖商品（用于选品参考）。"""
    ...

@tool
def search_pinduoduo_products(keyword: str, page: int = 1, page_size: int = 20) -> str:
    """搜索拼多多热卖商品（用于选品参考）。"""
    ...

@tool
def get_product_detail_from_url(source_url: str) -> str:
    """根据商品链接获取详细信息（1688或拼多多）。"""
    ...

@tool
def generate_listing(product_name_cn: str, product_description_cn: str = "",
                     category: str = "", keywords: list[str] = None) -> str:
    """生成俄语产品Listing（标题+描述），用于Ozon上架。"""
    ...

@tool
def translate_text(text: str, target_lang: str = "俄语") -> str:
    """翻译文本到指定语言。"""
    ...
```

#### 6.1.4 Memory 设计

**LangGraph Checkpointer 机制**：

使用 LangGraph 内置的 `AsyncPostgresSaver` 实现 Session 持久化：

```python
from langgraph.checkpoint.postgres import AsyncPostgresSaver

# 初始化 PostgreSQL checkpointer
checkpointer = AsyncPostgresSaver.from_conn_string(DATABASE_URL)
```

**关键特性**：
- 自动序列化/反序列化消息历史
- 支持 `thread_id` 隔离不同 Session 的对话
- 通过 `configurable` 参数传递店铺上下文
- 每次 `invoke()` 自动保存状态，无需手动管理

**Session 管理**（`SessionMemoryManager` + PostgreSQL）：

```python
# Session 元数据存储在 PostgreSQL session 表中
class SessionMemoryManager:
    """管理 Session 元数据和消息历史"""

    async def ensure_session(session_id): ...
    async def save_message(session_id, type, content): ...
    async def get_messages(session_id): ...
    async def update_session_title(session_id, title): ...
    async def list_sessions(shop_id): ...
```

**数据流**：

```
用户消息 → LangGraph Agent invoke()
          → LLM 节点生成回复
          → ToolNode 执行工具
          → AsyncPostgresSaver 自动保存消息
          → WebSocket 流式输出到前端
```

#### 6.1.5 Agent System Prompt

```
System Prompt (Master Agent):
---
你是 iCross Agent，专业的 Ozon 电商运营智能助手。

你的核心能力：
1. 理解用户的经营目标（选品、上架、定价、广告等）
2. 调用工具完成操作（search_hot_product / generate_listing / ozon_product_create 等）
3. 在关键节点主动要求用户确认（上架、广告创建）
4. 每步操作后简明汇报结果

安全规则（不可绕过）：
- 单次操作 >50 个商品 → 拒绝
- 价格 ≤0 → 拒绝
- 删除店铺或修改 API Key → 拒绝
- 上架前必须确认
- 广告创建前必须确认
- 价格调整 >±10% 必须确认

执行流程：
1. 确认目标（店铺、商品范围、预期结果）
2. 调用工具逐步执行
3. 关键节点强制等待确认
4. 执行完成生成简明报告

工具集：
- search_hot_product: 从 1688/拼多多搜索热销商品
- generate_listing: 生成俄语 Ozon Listing（Claude）
- generate_product_image: 生成商品场景图（SD WebUI）
- ozon_product_create: 在 Ozon 上架商品
- ozon_product_list: 查询店铺商品列表
- ozon_update_price: 更新商品价格
- ozon_ad_create / ozon_ad_manage: 广告管理
---
```

### 6.2 爬虫技术设计

#### 6.2.1 爬虫架构

```
DrissionPage 爬虫服务
    │
    ├── 1688 爬虫模块
    │     ├── 热销榜单抓取（HTTP 请求回退 → ChromiumPage 浏览器自动化）
    │     ├── 商品详情抓取（标题/价格/销量/图片/链接）
    │     └── 反爬检测（登录重定向时返回明确错误信息）
    │
    ├── 拼多多爬虫模块
    │     └── 同上
    │
    └── 降级方案
          ├── HTTP 请求模式（通过 requests 尝试直接解析页面 JSON 数据）
          ├── 第三方数据 API（慢慢买等）
          └── 手动导入 CSV
```

#### 6.2.2 反爬策略

| 策略 | 实现方式 |
|------|----------|
| 请求间隔 | 每次请求间隔 2~5s（随机） |
| UA 轮换 | 设置反检测 User-Agent |
| 浏览器特征 | `--disable-blink-features=AutomationControlled` 隐藏自动化标记 |
| 登录检测 | 检测 `login`/`captcha` 重定向，返回明确中文错误提示 |
| HTTP 回退 | 浏览器被拦截时自动尝试 HTTP 请求解析页面 JSON 数据 |
| 数据缓存 | 热销数据缓存 1 小时，避免重复爬取 |

### 6.3 图片生成技术设计

#### 6.3.1 图片生成管线

```python
# 商品图生成完整管线

def generate_product_scene(product_desc: str, source_image: bytes) -> list[bytes]:
    """生成商品场景图"""

    # Step 1: 去背景
    transparent_img = rembg.remove(
        source_image,
        session=rembg_session,
        alpha_matting=True,
    )

    # Step 2: 生成场景图 (ControlNet Canny 保持商品形状)
    scene_prompt = f"professional e-commerce photo, {product_desc}, "
                   f"natural lighting, clean background, high quality"

    scene_images = sd_webui.img2img(
        image=transparent_img,  # 图生图
        prompt=scene_prompt,
        strength=0.7,  # 保持商品形状
        controlnet_units=[{
            "module": "canny",
            "model": "control_v11p_sd15_canny",
            "image": transparent_img,
        }]
    )

    return scene_images
```

#### 6.3.2 性能优化

| 策略 | 说明 |
|------|------|
| 队列缓冲 | 图片生成任务进入 Celery 队列，前端返回 task_id |
| GPU 加速 | SD WebUI 必须有 GPU（建议 12GB+ VRAM） |
| 模型缓存 | rembg session 预加载，常驻内存 |
| 并行生成 | 同时生成 3~5 张候选图供选择 |

### 6.4 任务队列技术设计

#### 6.4.1 队列设计

| 队列名 | 用途 | 优先级 |
|--------|------|--------|
| `default` | 通用任务 | 5 |
| `batch_import` | 批量上架 | 3 |
| `image_generation` | 图片生成 | 7 |
| `scheduled` | 定时任务 | 1 |
| `ad_management` | 广告管理 | 6 |

#### 6.4.2 重试策略

| 场景 | 重试次数 | 退避策略 |
|------|----------|----------|
| Ozon API 调用失败 | 3 | 指数退避（10s → 60s → 300s） |
| 图片生成失败 | 5 | 固定 30s |
| 爬虫被反爬 | 3 | 指数退避 + 切换 UA |
| 外部 LLM 超时 | 2 | 指数退避 |

---

## 7. 数据模型设计

### 7.1 核心实体关系图

```
Shop (1) ──< Session (N)
  │           │
  │           └── messages[] (消息历史)
  │
  ├─< Product (N)
  │      │
  │      └── ProductDraft (1:1, 草稿态)
  │
  ├─< PriceRule (N)
  │
  └─< AdCampaign (N)

Task (N) ──< TaskLog (N)
  │           │
  └─ 关联 shop_id, 关联商品

ListingTemplate (N) ──< ProductDraft (N)
```

### 7.2 详细数据模型

#### 7.2.1 Shop（店铺）

```python
class Shop(BaseModel):
    id: UUID                      # 主键
    name: str                     # 店铺名称，如"店铺A"
    ozon_client_id: str           # Ozon Client ID
    ozon_api_key: str             # 加密存储的 API Key
    category: str                 # 主营类目
    status: ShopStatus            # active / suspended / expired
    created_at: datetime
    updated_at: datetime

class ShopStatus(str, Enum):
    active = "active"
    suspended = "suspended"
    expired = "expired"
```

#### 7.2.2 Session（会话）

```python
class Session(BaseModel):
    id: UUID                      # Session ID
    shop_id: UUID                 # 关联店铺
    user_id: UUID                 # 关联用户
    title: str                    # Session 标题（如"选品-瑜伽裤"）
    created_at: datetime
    updated_at: datetime
    is_active: bool               # 当前是否活跃

class Message(BaseModel):
    id: UUID
    session_id: UUID
    role: MessageRole            # human / ai / system / tool
    content: str                 # 消息内容
    tool_name: str | None        # 如果是 tool 类型，记录工具名
    tool_output: str | None      # 工具输出
    tokens: int | None           # token 消耗
    created_at: datetime
```

#### 7.2.3 Product（商品）

```python
class Product(BaseModel):
    id: UUID
    ozon_product_id: str          # Ozon 平台商品 ID
    shop_id: UUID
    sku: str                      # SKU
    title: str                    # 俄语标题
    description: str              # 俄语描述
    keywords: list[str]           # 关键词列表
    price: float                  # 当前价格（卢布）
    cost: float                   # 成本（人民币）
    stock: int                    # 库存
    status: ProductStatus         # draft / published / archived
    source_url: str | None       # 选品来源 URL
    source_product_id: str | None # 源平台商品 ID
    images: list[str]             # 图片 URL 列表
    created_at: datetime
    updated_at: datetime

class ProductStatus(str, Enum):
    draft = "draft"
    published = "published"
    archived = "archived"
```

#### 7.2.4 ProductDraft（商品草稿）

```python
class ProductDraft(BaseModel):
    id: UUID
    shop_id: UUID
    product_id: UUID | None       # 发布后关联的 Product
    source_product_info: dict    # 选品来源信息（JSON）
    listing_content: dict         # 生成的 Listing 内容
    generated_images: list[str]  # AI 生成的图片 URL
    suggested_price: float       # 建议售价
    final_price: float | None    # 人工调整后的售价
    status: DraftStatus          # pending_review / approved / rejected
    reviewer_note: str | None    # 审核备注（驳回原因）
    created_at: datetime
    reviewed_at: datetime | None
```

#### 7.2.5 Task（任务）

```python
class Task(BaseModel):
    id: UUID
    type: TaskType                # product_selection / listing / image / publish / price / ad
    shop_id: UUID
    user_id: UUID | None         # 发起用户（None=自动任务）
    status: TaskStatus
    input_params: dict           # 输入参数 JSON
    output_result: dict | None   # 输出结果 JSON
    error_message: str | None    # 错误信息
    started_at: datetime
    completed_at: datetime | None
    total_duration: float | None # 秒

class TaskType(str, Enum):
    product_selection = "product_selection"
    listing_generation = "listing_generation"
    image_generation = "image_generation"
    product_publish = "product_publish"
    price_adjust = "price_adjust"
    ad_create = "ad_create"
    scheduled_price = "scheduled_price"

class TaskStatus(str, Enum):
    pending = "pending"
    running = "running"
    success = "success"
    failed = "failed"
    waiting_confirmation = "waiting_confirmation"  # 等待人工确认
    confirmed = "confirmed"
    rejected = "rejected"
```

#### 7.2.6 其他实体

```python
# Listing 模板
class ListingTemplate(BaseModel):
    id: UUID
    shop_id: UUID | None         # None=全局模板
    name: str                    # 如"专业严谨型"、"活泼促销型"
    prompt_template: str         # Prompt 模板文本
    is_default: bool
    created_at: datetime

# 定价规则
class PriceRule(BaseModel):
    id: UUID
    shop_id: UUID
    name: str                    # 规则名称
    min_margin: float           # 最低毛利率（如 0.15 = 15%）
    max_margin: float           # 最高毛利率
    follow_competitor: bool     # 是否跟踪竞品
    competitor_adjust_factor: float  # 竞品价格系数（如 0.98）
    change_threshold: float      # 变动阈值（如 0.05 = 5%）
    is_active: bool
    created_at: datetime

# 广告活动
class AdCampaign(BaseModel):
    id: UUID
    shop_id: UUID
    ozon_campaign_id: str
    product_id: UUID
    campaign_type: str          # search / product_page
    budget_daily: float          # 日预算
    acos_target: float           # 目标 ACOS
    status: str                  # active / paused / completed
    created_at: datetime
```

#### 7.2.7 租户与配置模型

```python
# 公司（租户）
class Tenant(BaseModel):
    id: UUID
    name: str                     # 公司名称
    created_at: datetime
    updated_at: datetime
    # 目录结构：tenants/{id}/

# 公司配置
class TenantConfig(BaseModel):
    brand_positioning: str        # 品牌定位：高端/性价比/niche
    target_margin: float          # 目标毛利率 (0~1)
    auto_pricing_enabled: bool    # 自动定价开关
    min_price_coefficient: float  # 最低价格系数
    max_price_coefficient: float  # 最高价格系数
    competitor_strategy: str      # 竞品跟随策略：领先/滞后/忽略
    listing_tone: str             # Listing语气：专业/友好/数据驱动
    stock_buffer_days: int        # 库存缓冲天数
    notification_email: str       # 通知邮箱

# 店铺配置（继承公司默认值）
class StoreConfig(BaseModel):
    store_id: str                 # 店铺标识
    ozon_client_id: str           # Ozon API 客户端 ID
    ozon_api_key: str             # Ozon API Key（加密存储）
    brand_positioning: str | None  # 可覆盖公司配置
    target_margin: float | None
    auto_pricing_enabled: bool | None
    min_price_coefficient: float | None
    max_price_coefficient: float | None
    competitor_strategy: str | None
    listing_tone: str | None
    stock_buffer_days: int | None
    is_active: bool               # 店铺状态
```

**文件存储结构**：

```
tenants/{company_id}/
├── config.json            # 公司级配置
├── strategy.md            # 公司级运营策略（Markdown）
└── stores/
    └── {store_id}/
        ├── config.json    # 店铺配置（继承公司默认值）
        ├── strategy.md    # 店铺级运营策略
        └── state.json     # 运行时动态状态（自动生成）
```

---

## 8. API 契约设计

### 8.1 Agent 对话 API

#### POST /api/v1/chat

发起 Agent 对话（支持流式输出）。

**请求**：
```json
{
  "message": "帮我找 1688 上卖得好的瑜伽裤",
  "session_id": "uuid",
  "shop_id": "uuid",
  "stream": true
}
```

**响应（流式）**：
```
event: thought
data: {"tool": "search_hot_product", "input": {"keyword": "瑜伽裤", "platform": "1688"}}

event: tool_start
data: {"tool": "search_hot_product"}

event: tool_end
data: {"tool": "search_hot_product", "output": {"count": 20, "products": [...]}}

event: token
data: "已找到 20 款热销瑜伽裤，以下是 Top 5："

event: done
data: {"session_id": "uuid", "tokens_used": 1234}
```

#### GET /api/v1/sessions?shop_id={shop_id}

获取 Session 列表。

**响应**：
```json
{
  "sessions": [
    {"id": "uuid", "title": "选品-瑜伽裤", "created_at": "2026-04-25T09:00:00Z", "updated_at": "2026-04-25T09:30:00Z"}
  ]
}
```

#### GET /api/v1/sessions/{session_id}/messages

获取历史消息。

### 8.2 Ozon Adapter API

#### POST /api/v1/ozon/publish

发布商品到 Ozon。

```json
{
  "shop_id": "uuid",
  "title": "瑜伽裤女款运动健身",
  "description": "高质量弹性面料...",
  "keywords": ["瑜伽裤", "运动裤", "健身服"],
  "price": 999.0,
  "stock": 100,
  "images": ["url1", "url2", "url3"]
}
```

**响应**：
```json
{
  "ozon_product_id": "123456789",
  "status": "pending_review",
  "created_at": "2026-04-25T10:00:00Z"
}
```

#### GET /api/v1/ozon/products?shop_id={shop_id}&limit={limit}&offset={offset}

获取店铺商品列表。

#### PUT /api/v1/ozon/price

更新商品价格。

```json
{
  "shop_id": "uuid",
  "ozon_product_id": "123456789",
  "new_price": 899.0
}
```

### 8.3 Hub API

#### GET /api/v1/hub/dashboard?shop_id={shop_id}

获取仪表盘数据（KPI 卡片）。

#### GET /api/v1/hub/drafts?shop_id={shop_id}

获取草稿箱列表。

#### POST /api/v1/hub/drafts/{draft_id}/approve

审核通过草稿并发布。

#### POST /api/v1/hub/drafts/{draft_id}/reject

驳回草稿。

### 8.4 任务 API

#### POST /api/v1/tasks

创建异步任务（内部使用，Celery 触发）。

#### GET /api/v1/tasks/{task_id}

获取任务状态和结果。

#### GET /api/v1/hub/tasks?shop_id={shop_id}

获取任务历史列表。

### 8.5 配置管理 API

#### 租户（公司）管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tenants` | 列出所有公司 |
| POST | `/api/tenants` | 创建公司（自动生成目录和默认配置） |
| GET | `/api/tenants/{company_id}/config` | 获取公司配置 |
| PUT | `/api/tenants/{company_id}/config` | 更新公司配置 |
| GET | `/api/tenants/{company_id}/strategy` | 获取公司策略文档 |
| PUT | `/api/tenants/{company_id}/strategy` | 更新公司策略文档（Markdown 文本） |
| DELETE | `/api/tenants/{company_id}` | 删除公司（同时清理目录） |

#### 店铺管理

| 方法 | 路径 | 说明 |
|------|------|------|
| GET | `/api/tenants/{company_id}/stores` | 列出公司下所有店铺 |
| POST | `/api/tenants/{company_id}/stores` | 新增店铺 |
| GET | `/api/tenants/{company_id}/stores/{store_id}/config` | 获取店铺配置 |
| PUT | `/api/tenants/{company_id}/stores/{store_id}/config` | 更新店铺配置 |
| GET | `/api/tenants/{company_id}/stores/{store_id}/strategy` | 获取店铺策略 |
| PUT | `/api/tenants/{company_id}/stores/{store_id}/strategy` | 更新店铺策略 |
| GET | `/api/tenants/{company_id}/stores/{store_id}/state` | 获取店铺动态状态 |
| PUT | `/api/tenants/{company_id}/stores/{store_id}/state` | 人工修改店铺状态（如暂停自动调价） |
| DELETE | `/api/tenants/{company_id}/stores/{store_id}` | 删除店铺 |

**实现要点**：
- 后端验证字段合法性（如价格比例范围、brand_positioning 枚举值）
- 写入文件使用原子操作（临时文件 → 替换），避免并发损坏
- `strategy.md` 直接保存文本内容，无需解析

---

## 9. 前端界面设计

### 9.1 Agent 对话界面（三栏布局）

```
┌──────────────┬────────────────────────────────────┬───────────────────┐
│   左栏 240px │           中栏（flex: 1）           │   右栏 280px      │
│              │                                    │                    │
│ [Logo]       │  ┌────────────────────────────────┐ │  店铺选择器         │
│              │  │      Agent 对话区域            │ │  ┌──────────────┐  │
│ 功能菜单     │  │                                │ │  │ ▼ 店铺 A     │  │
│ ○ 选品       │  │  User: 帮我上架瑜伽裤          │ │  └──────────────┘  │
│ ○ 上架       │  │                                │ │                    │
│ ○ 定价       │  │  Agent: 正在上架到店铺 A...     │ │  店铺信息          │
│ ○ 广告       │  │  [工具调用: ozon_product_create] │ │  ├ API 状态: 正常  │
│ ○ 全托管     │  │  [工具执行成功]                 │ │  ├ 商品数: 156     │
│              │  │                                │ │  ├ 今日订单: 23    │
│ ─────────── │  │  Agent: 已成功上架！商品ID:      │ │  └ 评分: 4.8      │
│ Session列表  │  │  123456789                       │ │                    │
│ ○ 选品-瑜伽裤 │  │                                │ │  ──────────────   │
│ ○ 上架-运动鞋 │  └────────────────────────────────┘ │  Agent 任务状态     │
│ ○ 定价-连衣裙 │                                    │  ├ 运行中: 2       │
│              │  ┌────────────────────────────────┐ │  ├ 待确认: 1       │
│              │  │ 输入框...                    ➤ │ │  └ 今日完成: 15   │
│              │  └────────────────────────────────┘ │                    │
└──────────────┴────────────────────────────────────┴───────────────────┘
```

**交互说明**：

| 交互 | 行为 |
|------|------|
| 点击功能菜单 | 切换到该功能上下文，创建新的 Session |
| 输入消息 | 发送到 Agent，支持 Enter 发送，Shift+Enter 换行 |
| 工具调用展示 | Agent 调用工具时，显示工具名称和参数，用户可点击展开详情 |
| 流式输出 | Agent 回复逐字输出，工具执行过程实时展示 |
| 切换店铺 | 右侧下拉选择，左侧 Session 列表按该店铺过滤 |
| Session 点击 | 加载该 Session 的历史对话 |

### 9.2 Hub 后台页面

| 页面 | 路由 | 核心组件 |
|------|------|----------|
| 仪表盘 | `/hub/dashboard` | KPI 卡片 + 店铺状态 + 告警流 |
| 商品管理 | `/hub/products` | 商品列表 + 草稿箱 + 图片素材库 |
| 选品中心 | `/hub/selection` | 热销榜单 + 候选品详情 + 采纳/忽略 |
| 订单看板 | `/hub/orders` | 订单明细 + 利润分析 + 调价效果 |
| 任务日志 | `/hub/tasks` | 任务历史 + 日志详情 + 错误日志 |
| 系统配置 | `/hub/settings` | 店铺管理 + 定价规则 + 广告规则 |

### 9.3 配置管理界面

在 Agent 对话界面和运营中心之外，新增配置管理页面（嵌入运营中心 Tab 或独立页面）：

#### 公司管理 Tab

- 表格列出所有公司（租户），含名称、创建时间、店铺数
- 按钮：新增公司（弹窗表单）、编辑配置、编辑策略、进入店铺管理、删除

#### 公司配置编辑表单

表单字段（对应 `config.json`）：

| 字段 | 组件 | 说明 |
|------|------|------|
| 品牌定位 | 下拉选择 | 高端/性价比/niche |
| 目标毛利率 | 数字输入框 | 范围 0~1 |
| 自动定价 | 开关 | 启用/禁用 |
| 最低/最高价格系数 | 数字输入 | 如 0.8 ~ 1.5 |
| 竞品跟随策略 | 下拉选择 | 领先/滞后/忽略 |
| Listing 语气 | 下拉选择 | 专业/友好/数据驱动 |
| 库存缓冲天数 | 数字输入 | 如 7 天 |

#### 公司策略编辑页（strategy.md）

- 大型 Markdown 编辑器（如 SimpleMDE / Vditor）
- 支持实时预览
- 保存后直接写入 `strategy.md`

#### 店铺管理 Tab

- 选定公司下显示所有店铺
- 新增店铺：弹窗输入店铺 ID、Ozon API Key、品牌定位（可继承公司）
- 每行操作：编辑配置、编辑策略、查看状态

#### 店铺状态查看页面

- 只读展示：上次调价时间、当前价格表、待上架列表、绩效快照
- 可修改字段：暂停自动调价、手动修正某个 SKU 价格

### 9.4 设计规范

| 元素 | 规范 |
|------|------|
| 配色 | 主色 #1677FF（Ant Design 蓝），辅助色 #52C41A（成功），强调色 #FF4D4F（告警） |
| 字体 | 中文：PingFang SC / Microsoft YaHei；俄语：Roboto；数字：Roboto Mono |
| 组件库 | Ant Design 5.x |
| 图标 | Ant Design Icons |
| 响应式 | 桌面端优先（最小宽度 1280px） |

---

## 10. 错误处理与容错策略

### 10.1 错误分类与处理

| 错误类型 | 示例 | 处理策略 |
|----------|------|----------|
| **用户输入错误** | 商品价格格式错误 | 友好提示，引导用户修正 |
| **工具执行失败** | Ozon API 超时 | 自动重试 3 次 + 告知用户 |
| **Agent 解析失败** | LLM 输出格式解析错误 | 返回错误信息，请求重试 |
| **外部服务不可用** | 1688 网站崩溃 | 降级到手动导入，告知用户 |
| **图片生成失败** | SD GPU 内存不足 | 降低分辨率重试，告知用户 |
| **数据存储失败** | 数据库连接断开 | 写入重试，写入失败则内存缓冲后重试 |
| **API 限流** | Ozon API 超过 QPS | 指数退避等待，重新请求 |

### 10.2 Agent 错误处理流程

```
Tool 执行失败
    │
    ├── 重试次数 < 3？
    │   ├── 是 → 指数退避重试
    │   └── 否 → 进入降级路径
    │
    ├── 降级路径？
    │   ├── 爬虫失败 → 提示用户手动导入数据
    │   ├── 图片失败 → 使用源商品图（不去背景）
    │   ├── Ozon API 失败 → 返回错误 + 建议
    │   └── LLM 失败 → 切换备用模型
    │
    └── 记录错误日志 + 更新任务状态
```

### 10.3 系统容错

| 组件 | 容错方式 |
|------|----------|
| Agent 服务 | 多副本部署，Gateway 负载均衡 |
| 数据库 | PostgreSQL 主从复制 |
| 缓存 | Redis 主从 + 哨兵 |
| 任务队列 | Celery 任务持久化到 Redis |
| 图片服务 | SD WebUI 多实例（GPU 负载均衡） |
| 爬虫服务 | 独立部署，降级方案 |

---

## 11. 安全模型

### 11.1 认证与授权

```
用户认证：
  Web 前端 → OAuth 2.0 / 手机号验证码
  Telegram → Bot Token 验证
  API 调用 → API Key

授权层级：
  ├── 超级管理员 → 所有店铺 + 系统配置
  ├── 店铺管理员 → 所管店铺 + Hub 操作
  └── 操作员 → 仅 Agent 对话 + 查看

Agent 操作权限（通过 Hub 配置）：
  ├── 可上架 → ozon_product_create
  ├── 可调价 → ozon_update_price
  ├── 可创建广告 → ozon_ad_create
  └── 不可删除 → 禁用商品删除权限
```

### 11.2 敏感数据保护

| 数据 | 保护措施 |
|------|----------|
| Ozon API Key | 加密存储（AES-256），不在日志中输出 |
| 用户对话内容 | 不用于模型训练（可配置） |
| 店铺数据 | 租户隔离，Agent 仅能访问授权店铺 |
| 支付信息 | 不存储，通过 Ozon 官方接口 |

### 11.3 Agent 安全边界

- Agent 执行任何操作前，验证用户身份
- 批量操作（>5 个商品）需要二次确认
- 所有操作写入完整审计日志
- 关键操作（删除、下架）需要额外确认

---

## 12. 项目工程结构

### 12.1 整体目录结构

```
icross-agent/
│
├── pyproject.toml               # Python 项目配置 (uv)
├── CLAUDE.md                    # Claude Code 项目说明
│
├── src/
│   └── icross/                 # 主源码包
│       ├── __init__.py
│       │
│       ├── api/                # FastAPI 应用
│       │   ├── __init__.py
│       │   ├── main.py         # 应用入口
│       │   └── routers/
│       │       ├── __init__.py
│       │       ├── chat.py      # Agent 对话接口 (WebSocket)
│       │       ├── sessions.py  # Session CRUD
│       │       ├── shops.py     # 店铺管理
│       │       ├── products.py  # 商品管理
│       │       ├── drafts.py    # 草稿审核
│       │       ├── ozon.py      # Ozon 操作
│       │       ├── crawler.py   # 爬虫搜索
│       │       ├── templates.py # Listing 模板
│       │       └── categories.py# 类目管理
│       │
│       ├── agents/              # Agent 层 (LangGraph)
│       │   └── master/
│       │       ├── __init__.py
│       │       ├── agent.py     # create_react_agent 包装
│       │       ├── llm.py       # 多模型工厂
│       │       ├── tools.py     # @tool 装饰器工具
│       │       └── tools_product.py  # 选品/Listing 工具
│       │
│       ├── services/            # 外部服务封装
│       │   ├── __init__.py
│       │   ├── crawler.py       # 1688/拼多多爬虫
│       │   └── ozon/
│       │       ├── __init__.py
│       │       └── client.py    # Ozon API 客户端包装
│       │
│       ├── core/                # 核心基础设施
│       │   ├── __init__.py
│       │   ├── memory/
│       │   │   ├── __init__.py
│       │   │   └── manager.py   # SessionMemoryManager
│       │   └── storage/
│       │       ├── __init__.py
│       │       ├── postgres.py      # asyncpg 基础操作
│       │       ├── session_postgres.py
│       │       ├── shop_postgres.py
│       │       └── product_postgres.py
│       │
│       └── services/            # 配置管理服务（待实现）
│           └── config_service.py  # 租户/店铺配置 CRUD
│
├── frontend/                    # 前端静态页面
│   ├── index.html              # Agent 对话界面（三栏布局）
│   ├── operations.html         # 运营中心（选品/商品/草稿）
│   ├── products.html           # 商品管理旧版
│   └── static/                 # 静态资源
│
├── tests/                       # 测试
│   └── __init__.py
│
├── vendors/                    # 开源项目源码（已克隆/安装）
│   ├── langchain/              # LangChain 框架
│   ├── langgraph/              # LangGraph 框架
│   ├── OzonAPI-main/           # OzonAPI 客户端
│   ├── dify/                   # Dify（参考架构）
│   ├── next.js/                # Next.js 框架
│   ├── ant-design/             # Ant Design 组件库
│   ├── celery/                 # Celery 任务队列
│   ├── fastapi/                # FastAPI Web 框架
│   ├── rembg/                  # 图片去背景
│   ├── DrissionPage/           # 爬虫框架
│   └── stable-diffusion-webui/ # Stable Diffusion WebUI
│
├── docs/                        # 文档
│   ├── Design.md
│   └── research.md
│
└── tenants/                     # 租户配置目录（待实现）
    └── example_company/
        ├── config.json
        ├── strategy.md
        └── stores/
            └── example_store/
                ├── config.json
                ├── strategy.md
                └── state.json
```

### 12.2 环境变量配置

```bash
# .env.example

# 数据库
DATABASE_URL=postgresql://user:pass@localhost:5432/icross

# Redis
REDIS_URL=redis://localhost:6379/0

# LLM API Keys
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...
DEEPSEEK_API_KEY=sk-...

# Ozon API
OZON_CLIENT_ID=...
OZON_API_KEY=...

# Stable Diffusion WebUI
SD_WEBUI_URL=http://localhost:7860
SD_WEBUI_AUTH=

# 前端
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_WS_URL=ws://localhost:8000

# 安全
SECRET_KEY=your-secret-key-here
API_RATE_LIMIT=100/minute

# 日志
LOG_LEVEL=INFO
LOG_FORMAT=json
```

---

## 13. 分阶段开发计划

### 第一阶段：核心骨架（2~3周）— ✅ 已完成

**目标**：验证 LangGraph Agent + Web 对话 + 工具调用链路

| 任务 | 状态 | 验收标准 |
|------|------|----------|
| 项目骨架初始化 | ✅ | uv 项目创建，目录结构就绪 |
| LangGraph Agent 实现 | ✅ | `create_react_agent` + AsyncPostgresSaver |
| FastAPI 网关搭建 | ✅ | WebSocket `/chat` 流式输出 |
| 前端三栏布局 | ✅ | 前端正常渲染 |
| Session + Memory 管理 | ✅ | PostgreSQL checkpointer 持久化 |
| 简单示例 Tool | ✅ | Agent 能调用计算器/时间工具 |

**交付物**：MVP，可用 Web 与 Agent 简单对话

---

### 第二阶段：Ozon 基础运营（4周）— ✅ 已完成

**目标**：Agent 拥有真实 Ozon 操作能力

| 任务 | 状态 | 验收标准 |
|------|------|----------|
| Ozon API 客户端封装 | ✅ | 所有接口跑通（31k 代码） |
| `ozon_product_list` 等 8 个工具 | ✅ | 可通过对话查询/操作 Ozon |
| 店铺选择器动态化 | ✅ | 从数据库读取店铺 |
| Hub 运营中心 | ✅ | 选品/商品/草稿管理页面 |
| 草稿审核流程 | ✅ | 创建草稿→审核→发布/驳回 |
| PostgreSQL JSONB 存储 | ✅ | 商品属性灵活扩展 |

**交付物**：通过对话完成 Ozon 商品查询/改价，Hub 审核草稿

---

### 第三阶段：智能选品与 Listing（3周）— 🔄 开发中

**目标**：自动化选品到文案全流程

| 任务 | 状态 | 验收标准 |
|------|------|----------|
| DrissionPage 爬虫模块 | ✅ | 1688/拼多多搜索实现 |
| `search_1688_products` 工具 | ✅ | 对话中可搜索选品 |
| `search_pinduoduo_products` 工具 | ✅ | 拼多多搜索 |
| `get_product_detail_from_url` 工具 | ✅ | 商品详情获取 |
| `generate_listing` 工具 | ✅ | 生成俄语 Listing + SEO 关键词 |
| `translate_text` 工具 | ✅ | 多语言翻译 |
| Hub 选品中心前端 | ✅ | 选品 Tab + 商品卡片展示 |
| Listing 模板管理 | ✅ | 3 种预设模板 + API CRUD |
| 反爬容错处理 | ✅ | 登录检测 + HTTP 回退 + 错误提示 |
| 配置管理系统 | ⬜ | 公司/店铺配置前端管理（待实现） |

**交付物**：选品→文案→一键发布完整流程

---

### 第四阶段：视觉自动化与智能调价（3周）— ⏳ 未开始

**目标**：补齐图片能力和定价能力

| 任务 | 状态 | 验收标准 |
|------|------|----------|
| SD WebUI 部署 + API | ⬜ | HTTP API 可用 |
| `generate_product_image` 工具 | ⬜ | 生成场景图 |
| rembg 集成 | ⬜ | 去背景功能可用 |
| Hub 图片素材库 | ⬜ | AI 图片管理 |
| Celery 任务队列 | ⬜ | 批量任务和定时任务 |
| `auto_pricing` 工具 | ⬜ | 自动定价 |
| Hub 订单与利润看板 | ⬜ | 利润数据展示 |

**交付物**：全自动上架流程 + 每日定时调价

---

### 第五阶段：全店托管与广告（2周）— ⏳ 未开始

**目标**：实现全托管 + 广告智能管理

| 任务 | 状态 | 验收标准 |
|------|------|----------|
| `ozon_ad_create` / `ozon_ad_manage` 工具 | ⬜ | 广告创建和管理 |
| Master Agent 编排 | ⬜ | 全托管流程串联 |
| Hub 广告管理看板 | ⬜ | 广告数据展示 |
| Hub 任务与日志中心 | ⬜ | 思考链展示 |
| 多渠道接入 | ⬜ | Telegram Bot 集成 |
| 监控和告警 | ⬜ | 异常告警通知 |

**交付物**：周报自动推送，半自动/全自动托管

---

### 后续规划：配置管理模块

在所有阶段之上增加配置管理模块，所有阶段的配置均通过 Web UI 管理。

| 任务 | 状态 | 验收标准 |
|------|------|----------|
| 租户管理 API | ⬜ | CRUD 公司配置 |
| 店铺管理 API | ⬜ | CRUD 店铺配置 |
| 前端配置管理页面 | ⬜ | 公司/店铺表单 + Markdown 编辑器 |
| 智能体配置热加载 | ⬜ | 每次调用前重新读取配置文件 |

---

## 14. 技术依赖清单

### 14.1 Python 依赖

```toml
# pyproject.toml (uv)

[project]
name = "icross-agent"
version = "0.1.0"
requires-python = ">=3.11"

dependencies = [
    # Agent & LLM
    "openai>=1.0.0",
    "anthropic>=0.21.0",
    "httpx>=0.27.0",
    "minimax-agent>=0.1.0",       # MiniMax Agent SDK

    # Web 框架
    "fastapi>=0.115.0",
    "uvicorn[standard]>=0.30.0",
    "starlette>=0.40.0",

    # 数据库
    "sqlalchemy>=2.0.0",
    "asyncpg>=0.30.0",
    "alembic>=1.14.0",

    # 任务队列
    "celery>=5.4.0",
    "redis>=5.0.0",

    # 图片处理
    "rembg>=3.0.0",
    "Pillow>=10.0.0",
    "numpy>=1.26.0",
    "opencv-python>=4.9.0",

    # 爬虫
    "DrissionPage>=4.0.0",

    # 前端 (仅内部使用)
    "python-multipart>=0.0.9",
    "python-jose[cryptography]>=3.3.0",
    "passlib[bcrypt]>=1.7.4",

    # 其他
    "pydantic>=2.0.0",
    "pydantic-settings>=2.0.0",
    "structlog>=24.0.0",
    "tenacity>=8.0.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0.0",
    "pytest-asyncio>=0.24.0",
    "pytest-cov>=5.0.0",
    "ruff>=0.6.0",
    "mypy>=1.10.0",
]
```

### 14.2 前端依赖

```json
// frontend/package.json
{
  "dependencies": {
    "next": "^15.0.0",
    "react": "^19.0.0",
    "antd": "^5.22.0",
    "@ant-design/icons": "^5.5.0",
    "zustand": "^5.0.0",
    "@tanstack/react-query": "^5.0.0",
    "axios": "^1.7.0",
    "swr": "^2.2.0"
  }
}
```

> **前端源码**：已克隆至 `vendors/next.js/` 和 `vendors/ant-design/`，前端开发时直接参考

### 14.3 OzonAPI 依赖配置

```toml
# OzonAPI 已集成到 vendors/OzonAPI-main/
# 通过直接导入使用：
# from vendors.OzonAPI.main.src.ozonapi import SellerAPI
#
# 或在 pyproject.toml 中引用：
[project]
dependencies = [
    "ozonapi-async @ file://./vendors/OzonAPI-main",
]
```

> **注意**：OzonAPI 使用 `src/` 目录结构，导入路径为 `from ozonapi import SellerAPI`

---

## 15. 部署与运维

### 15.1 Docker 部署架构

```
┌─────────────────────────────────────────────────────────┐
│                    Docker Compose                       │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌─────────┐ │
│  │ API      │  │ Worker   │  │ Beat     │  │ SD      │ │
│  │ (FastAPI)│  │ (Celery) │  │ (Beat)  │  │ WebUI   │ │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬────┘ │
│       │             │             │             │      │
│  ┌────┴─────────────┴─────────────┴─────────────┴────┐ │
│  │                PostgreSQL + Redis                  │ │
│  └───────────────────────────────────────────────────┘ │
│                                                         │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐              │
│  │ Next.js  │  │ MinIO    │  │ nginx    │              │
│  │ (FE)     │  │ (Files)  │  │ (Proxy)  │              │
│  └──────────┘  └──────────┘  └──────────┘              │
└─────────────────────────────────────────────────────────┘
```

### 15.2 硬件需求

| 组件 | 最低配置 | 推荐配置 |
|------|----------|----------|
| API 服务器 | 2 核 CPU / 4GB RAM | 4 核 CPU / 8GB RAM |
| Celery Worker | 2 核 CPU / 4GB RAM | 4 核 CPU / 8GB RAM |
| SD WebUI | **8GB VRAM GPU** | **12GB+ VRAM GPU** |
| PostgreSQL | 2 核 CPU / 4GB RAM | 4 核 CPU / 16GB RAM |
| Redis | 1 核 CPU / 2GB RAM | 2 核 CPU / 4GB RAM |
| MinIO | 2 核 CPU / 4GB RAM | 4 核 CPU / 8GB RAM |

### 15.3 环境说明

| 环境 | 用途 | 说明 |
|------|------|------|
| `dev` | 本地开发 | 本地启动所有服务 |
| `staging` | 测试验证 | 部署到测试服务器 |
| `prod` | 生产环境 | 高可用多副本部署 |

### 15.4 监控方案

| 指标 | 工具 | 告警 |
|------|------|------|
| API 错误率 | Prometheus + Grafana | >1% 告警 |
| Agent 响应时间 | Prometheus | P99 >10s 告警 |
| Celery 任务失败率 | Flower | >5% 告警 |
| 磁盘使用率 | 系统监控 | >80% 告警 |
| Ozon API 限流 | 自建监控 | 触发限流立即告警 |

---



---

## 16. 前端可配置化设计

### 16.1 总体思路

- **后端负责**：读取/写入 `tenants/` 下的 JSON 和 MD 文件，并提供 RESTful API
- **前端负责**：提供表单页面，让运营人员**可视化管理**公司、店铺、策略规则
- **数据存储格式不变**（依然本地 JSON + MD），但所有文件由后端 API 自动生成、修改、删除，不允许手动编辑
- **智能体启动时**：仍然读取本地文件系统中的文件，不受前端影响
- **前端修改配置后**：后端直接覆盖对应文件，智能体下一次读取时自动生效，无需重启

### 16.2 后端 API

| 功能 | 方法 | 路径 | 说明 |
|------|------|------|------|
| 列出所有公司 | GET | `/api/tenants` | 返回公司列表及基本信息 |
| 创建公司 | POST | `/api/tenants` | 传入公司名、API密钥等，后端自动创建目录和默认配置 |
| 编辑公司配置 | PUT | `/api/tenants/{company_id}/config` | 更新公司级 config.json |
| 编辑公司策略 | PUT | `/api/tenants/{company_id}/strategy` | 更新公司级 strategy.md（文本域提交） |
| 列出某公司下所有店铺 | GET | `/api/tenants/{company_id}/stores` | |
| 创建店铺 | POST | `/api/tenants/{company_id}/stores` | 传入店铺配置，后端自动创建子目录及默认文件 |
| 编辑店铺配置 | PUT | `/api/tenants/{company_id}/stores/{store_id}/config` | 更新店铺 config.json |
| 编辑店铺策略 | PUT | `/api/tenants/{company_id}/stores/{store_id}/strategy` | 更新店铺 strategy.md（支持Markdown） |
| 查看/编辑店铺动态状态 | GET/PUT | `/api/tenants/.../stores/{store_id}/state` | 允许人工干预部分字段 |
| 删除公司/店铺 | DELETE | 对应路径 | 同时删除整个目录 |

**实现要点**：
- 后端验证请求字段合法性（价格比例范围、枚举值等）
- 写入文件使用原子操作（先写临时文件再替换），避免并发损坏
- strategy.md 直接保存文本内容，无需额外解析

### 16.3 前端界面功能模块

#### 16.3.1 公司管理页

- 列表展示所有电商公司
- 按钮：新增公司（弹窗填写名称、Ozon API Key、通知邮箱等）
- 每行操作：编辑配置、编辑策略、进入店铺管理、删除

#### 16.3.2 公司配置编辑表单（对应 config.json）

| 字段 | 组件 | 说明 |
|------|------|------|
| 品牌定位 | 下拉 | 高端/性价比/niche |
| 目标毛利率 | 数字输入 | 范围 0~1 |
| 自动定价开关 | 开关 | 启用/禁用 |
| 最低价格系数 | 数字输入 | 如 0.8 |
| 最高价格系数 | 数字输入 | 如 1.5 |
| 竞品跟随策略 | 下拉 | 领先/滞后/忽略 |
| Listing 语气 | 下拉 | 专业/友好/数据驱动 |
| 库存缓冲天数 | 数字输入 | 如 7 天 |

#### 16.3.3 公司策略编辑页（对应 strategy.md）

- 大型 Markdown 编辑器（如 SimpleMDE、Vditor），支持实时预览
- 保存后直接写入 `strategy.md`

#### 16.3.4 店铺管理页

- 显示所选公司下的所有店铺
- 新增店铺：弹窗输入店铺 ID、品牌定位等（可继承公司默认值）
- 每个店铺的操作：编辑配置、编辑策略、查看状态、进入运营仪表板

#### 16.3.5 店铺状态查看/干预页（state.json）

- 只读展示：上次调价时间、当前价格表、待上架列表、绩效快照
- 允许人工修改部分字段（如手动修正某个 SKU 价格，或暂停自动调价）

### 16.4 与智能体运行时的集成

**配置热加载机制**：

```
Agent 执行技能前
    │
    ├── 重新读取 config.json
    │       ↓
    ├── 重新读取 strategy.md
    │       ↓
    └── 使用最新配置执行任务
```

**并发处理**：

- 简单方案：Agent 每次执行关键技能前，重新加载一次配置文件（推荐，配置很小）
- 进阶方案：加入版本号或文件监听，检测到文件变化时中断当前任务并重试

### 16.5 改造实施步骤

1. **设计后端配置 API**：实现上述 CRUD 接口（`/api/tenants/` 系列）
2. **实现前端管理界面**：嵌入运营中心 Tab，使用表单 + Markdown 编辑器
3. **导入现有配置**：将现有 JSON/MD 文件保留为初始数据，通过 API 导入/展示
4. **Agent 代码适配**：确保 Agent 每次调用前读取最新配置（文件路径不变）
5. **测试与部署**：验证前端修改→文件写入→Agent 读取的完整闭环

### 16.6 预期效果

- 运营人员无需接触代码、文件夹，所有策略调整在前端完成
- 智能体即时响应配置变化（下次执行时自动生效）
- 一套代码支持无限多个租户/店铺，配置隔离且可视化

---

## 附录

### A. 术语表

| 术语 | 定义 |
|------|------|
| **Listing** | 商品在平台上的展示页面，包含标题、描述、图片等 |
| **Session** | 用户与 Agent 的一次对话会话 |
| **Tool** | Agent 可调用的工具，执行特定操作 |
| **Draft** | Agent 生成的待审核草稿，需要人工确认后才能发布 |
| **ACOS** | 广告销售成本比，广告花费/广告带来的销售额 |
| **Human-in-the-Loop** | 人工在环，关键操作需要人工确认 |
| **Master Agent** | 主导 Agent，负责理解用户目标并编排子 Agent |
| **子 Agent** | 专业 Agent，负责特定领域（如选品、文案） |
| **Adapter** | 适配器模式，用于封装不同平台的 API 差异 |

### B. 参考文档（vendor 源码位置）

| 文档 | 位置 | 说明 |
|------|------|------|
| Dify（参考） | `vendors/dify/` | 后端 `api/core/`，前端 `web/` |
| Next.js | `vendors/next.js/` | pnpm monorepo，`packages/next/src/` 为核心源码 |
| Ant Design | `vendors/ant-design/` | TypeScript 组件库，`components/component-name/` |
| OzonAPI | `vendors/OzonAPI-main/` | 异步 Pydantic 客户端，`src/ozonapi/seller/` |
| Celery | `vendors/celery/` | 任务队列，`celery/` 主包 |
| FastAPI | `vendors/fastapi/` | Web 框架，`fastapi/` 主包 |
| DrissionPage | `vendors/DrissionPage/` | 爬虫框架，双引擎架构 |
| rembg | `vendors/rembg/` | 图片去背景，`rembg/` 主包 |
| SD WebUI | `vendors/stable-diffusion-webui/` | 图像生成，`webui.py` 入口 |

### C. 决策记录

| 决策 | 选项 | 最终选择 | 原因 |
|------|------|----------|------|
| Agent 框架 | LangGraph Pregel vs Hermes-style While-Loop | **Hermes-style While-Loop** | 轻量简单，MiniMax/Claude 原生 function calling，代码量少易维护，不需要 LangGraph 复杂特性 |
| 多渠道接入 | 自研 vs Dify 参考 | 参考 Dify 设计 | 自研成本高，Dify 开源可借鉴 |
| 图片生成 | DALL-E vs SD WebUI | SD WebUI | 成本可控，可定制化强，ControlNet/LoRA 生态完整 |
| 爬虫框架 | Scrapy vs DrissionPage | DrissionPage | 双引擎（浏览器自动化 + HTTP），无需 Selenium，CDP 协议 |
| 图片去背景 | rembg vs 付费 API | rembg | 开源免费，`birefnet-general` 精度高，HTTP API 支持 |
| 任务队列 | Celery vs RQ | Celery | 功能丰富，Redis 集成成熟，beat_schedule 定时任务 |
| 数据库 | PostgreSQL vs MySQL | PostgreSQL | JSON 支持好，向量检索可扩展（Qdrant） |
| 前端 | Next.js (App Router) + Ant Design | **Next.js + Ant Design** | 成熟生态，Design Token 主题系统，暗黑模式，150+ 国际化 |