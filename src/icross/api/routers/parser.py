"""REST API endpoints for product material parsing (替代已废弃的爬虫选品)."""

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

router = APIRouter()


class ParseRequest(BaseModel):
    materials: list[dict[str, str]] = []


@router.post("/parse/product-materials")
async def parse_product_materials(req: ParseRequest):
    """Parse uploaded product materials into structured SPU/SKU data.

    Request body:
        materials: list of {type, path|url|content}
            - type "text":  {type, content}
            - type "file":   {type, path}
            - type "url":    {type, url}

    Returns structured SPU + SKU data.
    """
    if not req.materials:
        raise HTTPException(status_code=400, detail="未提供任何商品材料")

    from icross.services.product_parser import parse_product_materials as _parse
    result = _parse(req.materials)
    return result
