"""REST API endpoints for AI model configuration management."""
from fastapi import APIRouter
from pydantic import BaseModel

from icross.api.ai_utils import get_ai_llm_config, update_ai_llm_config

router = APIRouter(prefix="/ai-model-config", tags=["ai_model_config"])


class AiModelConfigUpdate(BaseModel):
    tiers: dict | None = None
    features: dict | None = None


@router.get("")
async def get_config():
    """Get full AI model configuration (tiers + features)."""
    return get_ai_llm_config()


@router.put("")
async def put_config(body: AiModelConfigUpdate):
    """Update AI model configuration (merge).

    Send the full config or partial updates.
    Missing keys are preserved from the existing config.
    """
    payload = {}
    if body.tiers is not None:
        payload["tiers"] = body.tiers
    if body.features is not None:
        payload["features"] = body.features

    ok = update_ai_llm_config(payload)
    return {"success": ok}
