"""Image generation & management API endpoints (Phase 4)."""

import base64
import json
from io import BytesIO

import httpx
from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

router = APIRouter(prefix="/images", tags=["images"])


class GenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=1000)
    size: str = "2048x2048"
    n: int = 1
    shop_id: str = ""
    product_id: int | None = None


class RemoveBgRequest(BaseModel):
    image_url: str = Field(..., min_length=1)
    shop_id: str = ""


@router.post("/generate")
def generate_image(req: GenerateRequest):
    """Generate product image using Seedream API."""
    try:
        # Validate minimum pixel size (Seedream requires >= 3686400)
        def _parse_pixels(size_str: str) -> int:
            size_str = size_str.strip().upper()
            if size_str == "2K":
                return 2560 * 1440
            if size_str == "4K":
                return 3840 * 2160
            if "X" in size_str:
                parts = size_str.split("X")
                return int(parts[0]) * int(parts[1])
            if "x" in size_str:
                parts = size_str.split("x")
                return int(parts[0]) * int(parts[1])
            return 0

        pixels = _parse_pixels(req.size)
        if 0 < pixels < 3686400:
            raise HTTPException(
                status_code=400,
                detail=f"图片尺寸太小（{pixels} 像素），Seedream 要求至少 3686400 像素（如 2048x2048）"
            )

        from icross.services.image_gen import SeedreamClient

        client = SeedreamClient()
        results = client.generate(
            prompt=req.prompt,
            size=req.size,
            n=min(max(req.n, 1), 4),
            response_format="url",
        )

        images = []
        for item in results:
            url = item.get("url")
            if url:
                images.append({"url": url, "prompt": req.prompt})

        # Save to storage
        from icross.agents.master.tools_product import ImageStorage
        store = ImageStorage()
        saved = []
        for img in images:
            record = store.save_image({
                "url": img["url"],
                "prompt": img["prompt"],
                "shop_id": req.shop_id,
                "product_id": req.product_id,
                "source": "generated",
            })
            saved.append(record)

        return {
            "success": True,
            "count": len(saved),
            "images": saved,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/remove-bg")
def remove_background(req: RemoveBgRequest):
    """Remove background from an image."""
    try:
        import rembg

        resp = httpx.get(req.image_url, timeout=30)
        resp.raise_for_status()
        input_bytes = resp.content

        output_bytes = rembg.remove(input_bytes)

        b64 = base64.b64encode(output_bytes).decode("utf-8")

        result = {
            "success": True,
            "image_b64": f"data:image/png;base64,{b64}",
            "size_bytes": len(output_bytes),
        }

        # Save to storage
        from icross.agents.master.tools_product import ImageStorage
        store = ImageStorage()
        store.save_image({
            "url": result["image_b64"],
            "prompt": f"remove-bg from {req.image_url}",
            "shop_id": req.shop_id,
            "source": "remove-bg",
        })

        return result

    except ImportError:
        raise HTTPException(status_code=500, detail="rembg 模块未安装，请执行 pip install rembg")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=400, detail=f"下载图片失败: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("")
def list_images(
    shop_id: str = "",
    limit: int = Query(default=50, le=200),
    offset: int = Query(default=0, ge=0),
):
    """List generated images."""
    from icross.agents.master.tools_product import ImageStorage

    store = ImageStorage()
    return store.list_images(shop_id=shop_id or None, limit=limit, offset=offset)


@router.delete("/{image_id}")
def delete_image(image_id: str):
    """Delete an image record."""
    from icross.agents.master.tools_product import ImageStorage

    store = ImageStorage()
    if store.delete_image(image_id):
        return {"success": True}
    raise HTTPException(status_code=404, detail="Image not found")
