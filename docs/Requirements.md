# iCross Agent 智能电商运营系统 — 需求规格说明书

> **版本**：v0.3
> **日期**：2026-04-25
> **状态**：已废弃 — 详细内容已合并至 `docs/Design.md`
> **概述**：本文档已废弃，所有详细需求规格请参考 `docs/Design.md`

---

> **⚠️ 重要说明**：详细的产品设计、技术规格、数据模型、API 契约、界面设计等已移至 `docs/Design.md`。本文档仅保留需求概述性内容作为补充参考。

---

## 补充参考：产品定位

### 目标用户

**中小型跨境电商卖家**，特征：
- 通常运营 1~5 个 Ozon 店铺
- 人工操作重复性高（选品、上架、调价、上新）
- 缺乏 AI 和技术能力，但愿意为提效工具付费
- 主要面向俄罗斯市场，需俄语文案能力

### 开发原则

- **按阶段开发，每阶段闭环验证**：不追求一步到位，每个阶段交付可用的产品
- **开源项目主导**：核心能力基于成熟开源项目二次开发，不重复造轮子
- **AI 模型无预算限制**：优先使用最强模型保证效果

### 技术选型（与 CLAUDE.md 一致）

| 层级 | 技术方案 | 参考路径 |
|------|----------|----------|
| **Agent 框架** | **LangGraph Pregel** | `vendors/langgraph/libs/langgraph/langgraph/pregel/main.py` |
| **Ozon API Client** | **ozonapi-async** | `vendors/OzonAPI-main/src/ozonapi/` |
| **Web 框架** | FastAPI | `vendors/fastapi/` |
| **任务队列** | Celery + Redis | `vendors/celery/` |
| **Web 爬虫** | DrissionPage | `vendors/DrissionPage/` |
| **图片去背景** | rembg | `vendors/rembg/` |
| **图片生成** | Stable Diffusion WebUI | `vendors/stable-diffusion-webui/` |
| **前端** | Next.js (App Router) + Ant Design | `vendors/next.js/` + `vendors/ant-design/` |
| **参考架构** | Dify | `vendors/dify/` |

---

## 补充参考：竞品分析

| 竞品 | 优点 | 缺点 | iCross Agent 的差异化 |
|------|------|------|----------------------|
| **店小秘** | ERP 功能全，用户多 | 无 AI 能力，操作繁琐 | AI 原生，Agent 对话驱动 |
| **芒果店长** | 简单易用 | 无选品/文案生成能力 | Agent 自动化选品和文案 |
| **ChatGPT** | AI 能力强大 | 无电商工具集成，无法直接操作 Ozon | 深度集成 Ozon API，Agent 直接执行 |
| **Jungle Scout** | 选品数据专业 | 贵，按月订阅 | 开源+AI，选品不收费 |

---

## 补充参考：分阶段实施计划（概述）

| 阶段 | 周期 | 核心目标 |
|------|------|----------|
| **第一阶段** | 2~3 周 | 核心骨架 — Agent 对话 + 工具调用 + 三栏前端 |
| **第二阶段** | 4 周 | Ozon 基础运营 — API 封装 + 商品管理 + Hub 草稿审核 |
| **第三阶段** | 3 周 | 智能选品与 Listing — 爬虫 + 俄语文案生成 |
| **第四阶段** | 3 周 | 视觉自动化与智能调价 — SD 图片生成 + Celery 定时任务 |
| **第五阶段** | 2 周 | 全托管与广告 — Master Agent + 多渠道接入 |

---

> 详细开发计划、技术设计、数据模型、API 契约请参考 `docs/Design.md`。
