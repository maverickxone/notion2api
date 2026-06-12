from typing import Dict, Any

from fastapi import APIRouter

from app.model_registry import list_available_models

router = APIRouter()


@router.get("/models", tags=["models"])
async def list_models() -> Dict[str, Any]:
    """
    列出可用的模型，兼容 OpenAI 格式。
    """
    return {
        "object": "list",
        "data": [
            {
                "id": model_id,
                "object": "model",
                "created": 0,
                "owned_by": "notion2api",
            }
            for model_id in list_available_models()
        ],
    }
