"""Auto-pilot prompt management API.

Endpoints for managing per-shop auto-pilot prompt templates
and generating prompts from natural language descriptions using LLM.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from icross.core.storage.ozon_data import AutoPilotConfigStorage

router = APIRouter(prefix="/auto-pilot", tags=["auto-pilot"])
config_store = AutoPilotConfigStorage()


class PromptSaveRequest(BaseModel):
    prompt_template: str


class PromptGenerateRequest(BaseModel):
    shop_id: str
    description: str


@router.get("/prompt/{shop_id}")
async def get_auto_pilot_prompt(shop_id: str):
    """Get the auto-pilot prompt template for a shop."""
    config = await config_store.get_config(shop_id)
    return {
        "prompt": config.get("prompt_template", ""),
        "generated_at": config.get("prompt_generated_at"),
    }


@router.put("/prompt/{shop_id}")
async def save_auto_pilot_prompt(shop_id: str, body: PromptSaveRequest):
    """Save auto-pilot prompt template for a shop."""
    config = await config_store.get_config(shop_id)
    config["prompt_template"] = body.prompt_template
    await config_store.save_config(shop_id, config)
    return {"success": True, "prompt": body.prompt_template}


@router.post("/prompt/generate")
async def generate_auto_pilot_prompt(body: PromptGenerateRequest):
    """Generate an auto-pilot prompt from a natural language description using LLM.

    The user describes their operations needs in natural language,
    and the LLM converts it into a structured auto-pilot prompt template.
    """
    try:
        from icross.api.ai_utils import get_ai_llm

        llm = get_ai_llm("auto-pilot.prompt")

        prompt = f"""你是一个电商运营专家。根据用户的运营需求描述，生成一个结构化的自动运营 prompt 模板。

这个模板将发送给 AI Agent 来执行自动运营任务。模板应包含具体的执行步骤。

店铺 ID 用 {{shop_id}} 代替。

用户需求描述：
{body.description}

请生成一个清晰、可执行的自动运营 prompt，包含具体的步骤和检查项。只返回 prompt 内容，不要解释。"""

        response = await llm.ainvoke([{"role": "user", "content": prompt}])
        raw = response.content
        if isinstance(raw, list):
            texts = []
            for block in raw:
                if isinstance(block, dict) and block.get("type") == "text":
                    texts.append(block.get("text", ""))
            raw = "\n".join(texts)

        generated = raw.strip().strip('"').strip("```").strip()

        # Save the generated prompt
        config = await config_store.get_config(body.shop_id)
        config["prompt_template"] = generated
        config["prompt_generated_at"] = datetime.now().isoformat()
        await config_store.save_config(body.shop_id, config)

        return {
            "success": True,
            "prompt": generated,
            "model_used": getattr(response, "model", "unknown"),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"生成失败: {e}")
