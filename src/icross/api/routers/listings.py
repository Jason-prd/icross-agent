"""REST API endpoints for listing management (Phase 3)."""

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from icross.core.storage.ozon_data import ListingStorage, DraftStorage

router = APIRouter(prefix="/listings", tags=["listings"])
listing_store = ListingStorage()
draft_store = DraftStorage()


class GenerateListingRequest(BaseModel):
    shop_id: str
    product_name_cn: str
    product_description_cn: str = ""
    category: str = ""
    keyword_str: str = ""
    target_market: str = "俄罗斯"
    skus: list[dict] = []
    template_id: str | None = None


@router.post("/generate")
async def generate_listing_api(req: GenerateListingRequest):
    """Generate a Russian listing using AI."""
    from icross.agents.master.tools_product import generate_listing

    custom_prompt = None
    if req.template_id:
        from icross.core.storage.ozon_data import ListingTemplateStorage
        store = ListingTemplateStorage()
        tmpl = await store.get_template(req.template_id)
        if tmpl:
            custom_prompt = tmpl.get("prompt_template")

    keywords = [k.strip() for k in req.keyword_str.split(",") if k.strip()]
    kwargs = dict(
        product_name_cn=req.product_name_cn,
        product_description_cn=req.product_description_cn,
        category=req.category,
        keywords=keywords,
        target_market=req.target_market,
        skus=req.skus,
    )
    if custom_prompt:
        kwargs["custom_prompt"] = custom_prompt

    result_str = generate_listing(**kwargs)

    import json
    try:
        result = json.loads(result_str)
        return {"success": True, "listing": result}
    except json.JSONDecodeError:
        return {"success": True, "listing": {"raw": result_str}}


@router.post("/translate")
async def translate_text(text: str = Query(default=...), target_lang: str = Query(default="俄语")):
    """Translate text to specified language."""
    try:
        from icross.agents.master.tools_product import translate_text
        import json
        result = translate_text.func(text=text, target_lang=target_lang)
        return json.loads(result)
    except Exception as e:
        return {"success": False, "error": str(e)}


class ListingSaveRequest(BaseModel):
    shop_id: str
    product_name_cn: str
    title: str
    description: str = ""
    keywords: list[str] = Field(default_factory=list)
    category: str = ""
    description_category_id: int = 0
    type_id: int = 0
    template_id: str | None = None


@router.get("")
async def list_listings(shop_id: str = ""):
    """List generated listings."""
    listings = await listing_store.list_listings(shop_id=shop_id or None)
    return {"listings": listings, "total": len(listings)}


@router.post("")
async def save_listing(req: ListingSaveRequest):
    """Save a generated listing."""
    listing = await listing_store.save_listing(
        shop_id=req.shop_id,
        data=req.model_dump(),
    )
    return {"success": True, "listing": listing}


@router.get("/{listing_id}")
async def get_listing(listing_id: str):
    """Get a listing by ID."""
    listing = await listing_store.get_listing(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")
    return listing


@router.delete("/{listing_id}")
async def delete_listing(listing_id: str):
    """Delete a listing."""
    if await listing_store.delete_listing(listing_id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="Listing not found")


@router.post("/{listing_id}/to-draft")
async def listing_to_draft(listing_id: str, shop_id: str = ""):
    """Convert a listing to a publish draft.

    Creates a pending draft from the listing's content so it can
    be reviewed and approved for publishing to Ozon.
    """
    listing = await listing_store.get_listing(listing_id)
    if not listing:
        raise HTTPException(status_code=404, detail="Listing not found")

    sid = shop_id or listing.get("shop_id", "")
    if not sid:
        raise HTTPException(status_code=400, detail="shop_id is required")

    draft = await draft_store.create_draft(
        shop_id=sid,
        draft_type="listing",
        title=listing.get("title", ""),
        description=listing.get("description", ""),
        price=0,
        offer_id="",
        source_url="",
        images=[],
        attrs={
            "description_category_id": listing.get("description_category_id", 0),
            "type_id": listing.get("type_id", 0),
            "source_listing_id": listing_id,
        },
    )

    # Mark listing as converted
    await listing_store.update_listing(listing_id, status="converted")

    return {"success": True, "draft_id": draft["id"], "draft": draft}


class QualityCheckRequest(BaseModel):
    title: str = ""
    description: str = ""
    keywords: list[str] = Field(default_factory=list)


@router.post("/check-quality")
async def check_listing_quality(req: QualityCheckRequest):
    """Check listing quality and provide suggestions."""
    title = req.title
    description = req.description
    keywords = req.keywords
    issues = []
    score = 100

    if not title:
        issues.append("标题不能为空")
        score -= 30
    elif len(title) < 30:
        issues.append("标题过短 ({len(title)}字符)，建议50-150字符")
        score -= 10
    elif len(title) > 200:
        issues.append("标题过长 ({len(title)}字符)，建议不超过150字符")
        score -= 5

    if not description:
        issues.append("描述不能为空")
        score -= 30
    elif len(description) < 300:
        issues.append("描述过短 ({len(description)}字符)，建议500-2000字符")
        score -= 10

    if not keywords:
        issues.append("关键词不能为空")
        score -= 20
    elif len(keywords) < 3:
        issues.append("关键词太少 ({len(keywords)}个)，建议5-10个")
        score -= 10

    return {
        "score": max(0, score),
        "issues": issues,
        "summary": "优秀" if score >= 80 else ("良好" if score >= 60 else "需要改进"),
    }
