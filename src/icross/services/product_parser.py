"""Product material parser — extracts structured SPU/SKU data from uploaded materials.

Replaces the old 1688/Pinduoduo crawler approach. Users upload product materials
(PDF, Excel, Word, images, URLs) and this service parses them into structured
SPU (Standard Product Unit) + SKU data using LLM.

Usage:
    from icross.services.product_parser import parse_product_materials

    result = parse_product_materials({
        "files": ["/path/to/spec.pdf", "/path/to/photo.jpg"],
        "urls": ["https://example.com/product/123"],
    })
    # Returns: { "spu": {...}, "skus": [...], "raw": "..." }
"""

import json
import os
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from langchain_core.messages import HumanMessage, SystemMessage
from pydantic import BaseModel

from icross.services.document_reader import read_document
from icross.api.ai_utils import get_ai_llm

# Load .env for API keys when used standalone (not via FastAPI/Agent)
_env_path = Path(__file__).parent.parent.parent.parent / ".env"
if _env_path.exists():
    load_dotenv(_env_path)


# ── Pydantic output models ─────────────────────────────────────────


class ProductSPU(BaseModel):
    """Standard Product Unit — product-level information."""

    name: str = ""
    brand: str = ""
    category: str = ""
    description: str = ""
    attributes: dict[str, str] = {}
    images: list[str] = []


class ProductSKU(BaseModel):
    """Stock Keeping Unit — variant-level information."""

    name: str = ""
    attributes: dict[str, str] = {}
    price: float = 0.0
    stock: int = 0
    images: list[str] = []


class ParseResult(BaseModel):
    """Top-level parse result returned by the parser."""

    success: bool
    spu: ProductSPU | None = None
    skus: list[ProductSKU] = []
    raw_materials: list[str] = []
    error: str | None = None


# ── Data model helpers ─────────────────────────────────────────────

SPU_SCHEMA = {
    "spu": {
        "name": "产品名称",
        "brand": "品牌",
        "category": "产品类目",
        "description": "产品详细描述",
        "attributes": {"属性名": "属性值"},
        "images": ["图片URL列表"],
    },
    "skus": [
        {
            "name": "SKU名称（如：黑色/L码）",
            "attributes": {"规格属性名": "属性值"},
            "price": 0.0,
            "stock": 0,
            "images": ["SKU图片URL列表"],
        }
    ],
}

PARSING_PROMPT = """你是一个电商产品信息提取专家。请根据用户提供的商品材料，提取出完整的SPU和SKU信息。

要求：
1. SPU（Standard Product Unit）是产品级别的信息，包括产品名称、品牌、类目、描述、通用属性
2. SKU（Stock Keeping Unit）是库存单位级别的信息，包括不同规格变体的价格、库存、规格属性
3. 如果材料中有价格信息，填入对应SKU的price字段（必须为**数字**，不能是字符串）
4. 如果材料中有库存信息，填入对应SKU的stock字段（必须为**整数**，不能是字符串）
5. 如果材料中有图片URL，填入对应SPU或SKU的images字段（字符串列表，每个元素是完整的URL）
6. 如果某些字段在材料中找不到，留空字符串或合理的默认值（如stock默认为0）
7. 品牌如果不能从材料中确认，填"自主品牌"
8. 类目尽量细分，如"蓝牙耳机"而不是"电子产品"
9. 所有内容使用中文
10. attributes 的键和值**必须都是字符串类型**
11. images 字段必须是字符串数组（URL列表），没有图片时给空列表 []

请严格按照以下JSON格式返回，不要添加任何额外说明：

{
  "spu": {
    "name": "产品名称",
    "brand": "品牌",
    "category": "类目",
    "description": "详细描述",
    "attributes": {},
    "images": []
  },
  "skus": [
    {
      "name": "SKU名称",
      "attributes": {},
      "price": 0.0,
      "stock": 0,
      "images": []
    }
  ]
}

示例输出：
{
  "spu": {
    "name": "无线蓝牙耳机 Pro",
    "brand": "SoundTech",
    "category": "蓝牙耳机",
    "description": "高品质无线蓝牙耳机，支持主动降噪、蓝牙5.3连接，续航30小时。",
    "attributes": {
      "连接方式": "蓝牙5.3",
      "佩戴方式": "入耳式",
      "电池续航": "30小时"
    },
    "images": ["https://example.com/main.jpg"]
  },
  "skus": [
    {
      "name": "黑色/L码",
      "attributes": {
        "颜色": "黑色",
        "尺寸": "L"
      },
      "price": 199.00,
      "stock": 100,
      "images": []
    },
    {
      "name": "白色/M码",
      "attributes": {
        "颜色": "白色",
        "尺寸": "M"
      },
      "price": 189.00,
      "stock": 50,
      "images": ["https://example.com/sku-white.jpg"]
    }
  ]
}

注意：
- 如果材料中没有明显的SKU区分，创建一个默认SKU
- SPU的attributes存放产品级别的通用属性（如材质、连接方式等）
- SKU的attributes存放规格变体属性（如颜色、尺寸等）
"""


# ── URL content fetcher ────────────────────────────────────────────

def _fetch_url_text(url: str) -> str:
    """Fetch a URL and extract readable text content using simple HTTP."""
    try:
        req = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/125.0.0.0 Safari/537.36"
                ),
                "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
                "Accept-Language": "zh-CN,zh;q=0.9",
            },
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read()
            # Try UTF-8 first, fall back to GBK (common for Chinese sites)
            try:
                text = raw.decode("utf-8")
            except UnicodeDecodeError:
                text = raw.decode("gbk", errors="replace")
    except Exception as e:
        return f"[抓取失败] {url}: {e}"

    # Strip HTML tags
    import re
    text = re.sub(r"<style[^>]*>.*?</style>", "", text, flags=re.DOTALL)
    text = re.sub(r"<script[^>]*>.*?</script>", "", text, flags=re.DOTALL)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text[:15000]  # limit length


# ── Document parsing ───────────────────────────────────────────────

def _parse_file(file_path: str) -> str:
    """Parse a local file and return text content."""
    path = Path(file_path)
    if not path.exists():
        return f"[文件不存在] {file_path}"

    ext = path.suffix.lower()

    # Text-based files: read directly
    if ext in (".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml"):
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                return f.read()[:20000]
        except UnicodeDecodeError:
            with open(file_path, "r", encoding="gbk") as f:
                return f.read()[:20000]

    # Documents: use Docling
    result = read_document(file_path)
    if result.get("success"):
        content = result.get("markdown", "")
        return content[:20000] if content else "[文档为空]"

    return f"[解析失败] {result.get('error', '未知错误')}"


# ── LLM parsing ────────────────────────────────────────────────────

def _extract_json_text(response_content: Any) -> str | None:
    """Extract JSON text from LLM response content (handles multimodal)."""
    if isinstance(response_content, list):
        texts = [b.get("text", "") if isinstance(b, dict) else str(b) for b in response_content]
        raw = "".join(texts)
    else:
        raw = str(response_content)

    # Strip markdown code fence if present
    if raw.startswith("```"):
        raw = raw.split("\n", 1)[-1]
        raw = raw.rsplit("```", 1)[0]
    raw = raw.strip()

    # Try direct JSON parse to verify
    try:
        json.loads(raw)
        return raw
    except json.JSONDecodeError:
        pass

    # Fallback: balanced-brace extraction (handles nested JSON, trailing text)
    brace_start = raw.find("{")
    if brace_start == -1:
        return None

    depth = 0
    for i in range(brace_start, len(raw)):
        c = raw[i]
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                candidate = raw[brace_start : i + 1]
                try:
                    json.loads(candidate)
                    return candidate
                except json.JSONDecodeError:
                    return None  # first root-level JSON object failed to parse
    return None


def _validate_parsed(parsed: dict) -> tuple[dict[str, Any] | None, str | None]:
    """Validate parsed JSON data against Pydantic models.

    Returns:
        (validated_dict, None) on success,
        (None, error_message) on failure.
    """
    try:
        spu_data = parsed.get("spu", {})
        skus_data = parsed.get("skus", [])

        spu = ProductSPU(**spu_data) if spu_data else None
        skus = [ProductSKU(**sku) for sku in skus_data]

        return {
            "spu": spu.model_dump() if spu else {},
            "skus": [sku.model_dump() for sku in skus],
        }, None
    except Exception as e:
        return None, str(e)


def _llm_parse_to_spu(materials_text: str) -> dict[str, Any]:
    """Use LLM to parse material text into structured SPU/SKU data.

    Validates output against Pydantic models and retries once on failure.
    """
    llm = get_ai_llm("product.parse")

    def _attempt(messages: list) -> dict[str, Any]:
        """Single attempt: invoke LLM, extract JSON, validate."""
        try:
            response = llm.invoke(messages)
            json_text = _extract_json_text(response.content)
            if json_text is None:
                return {"error": "LLM返回格式错误", "raw": getattr(response, "content", "")[:500]}

            parsed = json.loads(json_text)
            validated, error = _validate_parsed(parsed)
            if validated is not None:
                return validated

            # Validation failed — return error info for retry
            return {"_validation_error": error, "_parsed": parsed, "_raw": json_text[:500]}
        except Exception as e:
            return {"error": f"LLM调用失败: {str(e)}"}

    first_messages = [
        SystemMessage(content=PARSING_PROMPT),
        HumanMessage(content=f"以下是商品材料内容，请提取SPU和SKU信息：\n\n{materials_text[:30000]}"),
    ]

    result = _attempt(first_messages)

    # If the result has a _validation_error key, retry once with feedback
    if "_validation_error" in result:
        error_msg = result["_validation_error"]
        retry_prompt = (
            f"上次返回的JSON格式验证失败，请修正后重新输出。\n\n"
            f"验证错误：{error_msg}\n\n"
            f"请确保：\n"
            f"1. price 必须是数字（不是字符串），如 199.00\n"
            f"2. stock 必须是整数（不是字符串），如 100\n"
            f"3. attributes 的键和值都必须是字符串\n"
            f"4. images 必须是URL字符串列表，没有图片时给 []\n\n"
            f"商品材料内容：\n{materials_text[:20000]}"
        )
        retry_messages = [
            SystemMessage(content=PARSING_PROMPT),
            HumanMessage(content=retry_prompt),
        ]
        result = _attempt(retry_messages)

        if "_validation_error" in result:
            return {
                "error": f"重试后验证仍失败: {result['_validation_error']}",
                "raw_llm_output": result.get("_raw", ""),
            }

    return result


# ── Main entry point ───────────────────────────────────────────────

def parse_product_materials(
    materials: list[dict[str, str]],
) -> dict[str, Any]:
    """Parse product materials into structured SPU/SKU data.

    Args:
        materials: List of material items, each with:
            - type: "file" | "url" | "text"
            - path: file path (for type "file")
            - url: URL string (for type "url")
            - content: raw text (for type "text")

    Returns:
        Dict with:
            - success: bool
            - spu: dict (SPU data)
            - skus: list[dict] (SKU list)
            - raw_materials: list[str] (parsed text per material)
            - error: str (if failed)
    """
    if not materials:
        return {"success": False, "error": "未提供任何商品材料"}

    parsed_texts = []

    for item in materials:
        item_type = item.get("type", "")

        if item_type == "file":
            text = _parse_file(item.get("path", ""))
            parsed_texts.append(f"--- 文件: {item.get('path', '')} ---\n{text}")

        elif item_type == "url":
            text = _fetch_url_text(item.get("url", ""))
            parsed_texts.append(f"--- 链接: {item.get('url', '')} ---\n{text}")

        elif item_type == "text":
            parsed_texts.append(f"--- 用户输入 ---\n{item.get('content', '')}")

    if not parsed_texts:
        return {"success": False, "error": "所有材料解析结果为空"}

    combined = "\n\n".join(parsed_texts)
    result = _llm_parse_to_spu(combined)

    if "error" in result:
        # Build error ParseResult then dump to dict
        pr = ParseResult(
            success=False,
            raw_materials=parsed_texts,
            error=result["error"],
        )
        return pr.model_dump()

    # Build success ParseResult then dump to dict
    spu_obj = ProductSPU(**result.get("spu", {})) if result.get("spu") else None
    skus_objs = [ProductSKU(**s) for s in result.get("skus", [])]
    pr = ParseResult(
        success=True,
        spu=spu_obj,
        skus=skus_objs,
        raw_materials=parsed_texts,
    )
    return pr.model_dump()
