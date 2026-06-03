"""FastAPI application entry point."""

import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

# Load .env at app startup
_env_path = Path(__file__).parent.parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


app = FastAPI(
    title="iCross Agent API",
    description="AI-powered e-commerce operations system for managing Ozon shops",
    version="0.1.0",
)

# Serve uploaded product images at /uploads
_UPLOADS_DIR = Path(__file__).parent.parent.parent.parent / "uploads"
_UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(_UPLOADS_DIR)), name="uploads")


async def seed_default_templates():
    """Seed default listing templates on first startup and recover agent tasks."""
    from icross.core.storage.ozon_data import ListingTemplateStorage
    store = ListingTemplateStorage()
    existing = await store.list_templates()
    if not existing:
        await store.create_template(
            name="标准专业型",
            prompt_template="""你是一个专业的电商Listing生成专家。请为Ozon电商平台生成俄语产品Listing。

产品信息：
- 中文名称：{product_name_cn}
- 中文描述：{product_description_cn or '无'}
- 类目：{category or '未分类'}
- 关键词：{keyword_str or '无'}
- 目标市场：{target_market}

请生成：
1. 俄语产品标题（50-150字符，SEO优化，包含关键词）
2. 俄语产品描述（500-2000字符，详细描述产品特点、规格、使用方法）
3. 俄语关键词（5-10个，用逗号分隔）

只返回JSON格式：
{{"title": "俄语标题", "description": "俄语描述", "keywords": ["关键词1", "关键词2", ...]}}

只返回JSON，不要其他文字。""",
            is_default=True,
        )
        await store.create_template(
            name="促销营销型",
            prompt_template="""你是一个专业的电商营销文案专家。请为Ozon电商平台生成具有强烈促销感的俄语产品Listing。

产品信息：
- 中文名称：{product_name_cn}
- 中文描述：{product_description_cn or '无'}
- 类目：{category or '未分类'}
- 关键词：{keyword_str or '无'}
- 目标市场：{target_market}

要求：
1. 标题必须包含「Скидка」「Распродажа」「Хит」等促销词汇
2. 描述要突出限时优惠、限量等紧迫感
3. 使用表情符号和分隔符增加可读性
4. 5-10个俄语关键词

只返回JSON格式：
{{"title": "俄语标题", "description": "俄语描述", "keywords": ["关键词1", "关键词2", ...]}}

只返回JSON，不要其他文字。""",
        )
        await store.create_template(
            name="简洁实用型",
            prompt_template="""你是一个电商Listing生成专家。请为Ozon生成简洁实用的俄语产品Listing。

产品信息：
- 中文名称：{product_name_cn}
- 中文描述：{product_description_cn or '无'}
- 类目：{category or '未分类'}
- 关键词：{keyword_str or '无'}
- 目标市场：{target_market}

要求：
1. 标题简洁（50-80字符），包含核心关键词
2. 描述简明扼要（300-500字符），用短句和列表
3. 只包含最重要的规格参数
4. 3-5个俄语关键词

只返回JSON格式：
{{"title": "俄语标题", "description": "俄语描述", "keywords": ["关键词1", "关键词2", ...]}}

只返回JSON，不要其他文字。""",
        )

    # Recover interrupted agent tasks from previous server lifecycle
    from icross.services.agent_task_manager import agent_task_manager
    interrupted = await agent_task_manager.recover_from_restart()
    if interrupted:
        import logging
        logging.getLogger(__name__).warning(
            f"Recovered {len(interrupted)} interrupted agent tasks: "
            f"{[t['session_id'] for t in interrupted]}"
        )


@app.on_event("startup")
async def _startup():
    """Run startup tasks."""
    import os
    await seed_default_templates()

    # Seed default shop from .env if none exist
    from icross.core.storage.ozon_data import ShopStorage
    shop_store = ShopStorage()
    existing = await shop_store.list_shops()
    if not existing:
        env_client_id = os.getenv("OZON_CLIENT_ID", "").strip()
        env_api_key = os.getenv("OZON_API_KEY", "").strip()
        if env_client_id and env_api_key:
            await shop_store.add_shop(
                shop_id="shop-1",
                name="默认店铺",
                client_id=env_client_id,
                api_key=env_api_key,
            )
            import logging
            logging.getLogger(__name__).info("Seeded default shop from .env")

    # Start the scheduler service
    from icross.services.scheduler import scheduler_service
    await scheduler_service.start()


@app.on_event("shutdown")
async def _shutdown():
    """Clean up resources on shutdown."""
    from icross.services.notification import close_notification_service
    await close_notification_service()

    # Stop the scheduler service
    from icross.services.scheduler import scheduler_service
    await scheduler_service.stop()

# Import routers (JSON-based)
from .routers import chat, sessions, shops, products, drafts, ozon, templates, categories, images, pricing, rules, listings, tasks, workflows, uploads, reports, dashboard, notifications, providers, scheduler, parser, auto_pilot, auto_pilot_prompt, sourcing, ai_product, ai_config, ai_orders, ai_returns, ai_finance, ai_reports, ai_marketing, ai_service, ai_operations, ai_autopilot, ai_pricing, ai_drafts, compound_tasks, extension
# Import report service for @register_task registration
import icross.services.report_service  # noqa: F401

app.include_router(chat.router, prefix="/api")
app.include_router(sessions.router, prefix="/api")
app.include_router(shops.router, prefix="/api")
app.include_router(products.router, prefix="/api")
app.include_router(drafts.router, prefix="/api")
app.include_router(ozon.router, prefix="/api")

app.include_router(templates.router, prefix="/api")
app.include_router(categories.router, prefix="/api")
app.include_router(images.router, prefix="/api")
app.include_router(pricing.router, prefix="/api")
app.include_router(rules.router, prefix="/api")
app.include_router(listings.router, prefix="/api")
app.include_router(tasks.router, prefix="/api")
app.include_router(workflows.router, prefix="/api")
app.include_router(uploads.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
app.include_router(notifications.router, prefix="/api")
app.include_router(providers.router, prefix="/api")
app.include_router(scheduler.router, prefix="/api")
app.include_router(auto_pilot.router, prefix="/api")
app.include_router(auto_pilot_prompt.router, prefix="/api")
app.include_router(parser.router, prefix="/api")
app.include_router(sourcing.router, prefix="/api")
app.include_router(ai_product.router, prefix="/api")
app.include_router(ai_config.router, prefix="/api")
app.include_router(ai_orders.router, prefix="/api")
app.include_router(ai_returns.router, prefix="/api")
app.include_router(ai_finance.router, prefix="/api")
app.include_router(ai_reports.router, prefix="/api")
app.include_router(ai_marketing.router, prefix="/api")
app.include_router(ai_service.router, prefix="/api")
app.include_router(ai_operations.router, prefix="/api")
app.include_router(ai_autopilot.router, prefix="/api")
app.include_router(ai_pricing.router, prefix="/api")
app.include_router(ai_drafts.router, prefix="/api")
app.include_router(compound_tasks.router, prefix="/api")
app.include_router(extension.router, prefix="/api")


@app.get("/health")
def health():
    """Health check endpoint."""
    return {"status": "ok", "service": "icross-agent", "storage": "json"}


@app.get("/")
def root():
    """Root endpoint."""
    return {
        "service": "icross-agent",
        "version": "0.1.0",
        "docs": "/docs",
        "storage": "json",
    }