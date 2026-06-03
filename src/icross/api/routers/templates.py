"""REST API endpoints for Listing template management (Phase 3)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from icross.core.storage.ozon_data import ListingTemplateStorage

router = APIRouter()
template_storage = ListingTemplateStorage()


class TemplateCreate(BaseModel):
    name: str
    prompt_template: str
    shop_id: str | None = None
    is_default: bool = False


class TemplateUpdate(BaseModel):
    name: str | None = None
    prompt_template: str | None = None
    is_default: bool | None = None


@router.get("/templates")
async def list_templates(shop_id: str | None = None):
    """List listing templates."""
    templates = await template_storage.list_templates(shop_id=shop_id)
    return {"templates": templates, "total": len(templates)}


@router.get("/templates/default")
async def get_default_template():
    """Get the default listing template."""
    template = await template_storage.get_default_template()
    if not template:
        return {"template": None}
    return {"template": template}


@router.get("/templates/{template_id}")
async def get_template(template_id: str):
    """Get a template by ID."""
    template = await template_storage.get_template(template_id)
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"template": template}


@router.post("/templates")
async def create_template(body: TemplateCreate):
    """Create a new listing template."""
    if not body.name or not body.prompt_template:
        raise HTTPException(status_code=400, detail="name and prompt_template are required")
    template = await template_storage.create_template(
        name=body.name,
        prompt_template=body.prompt_template,
        shop_id=body.shop_id,
        is_default=body.is_default,
    )
    return {"success": True, "template": template}


@router.put("/templates/{template_id}")
async def update_template(template_id: str, body: TemplateUpdate):
    """Update a listing template."""
    template = await template_storage.update_template(
        template_id=template_id,
        name=body.name,
        prompt_template=body.prompt_template,
        is_default=body.is_default,
    )
    if not template:
        raise HTTPException(status_code=404, detail="Template not found")
    return {"success": True, "template": template}


@router.delete("/templates/{template_id}")
async def delete_template(template_id: str):
    """Delete a listing template."""
    await template_storage.delete_template(template_id)
    return {"success": True}
