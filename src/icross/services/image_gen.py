"""Seedeam (火山引擎) image generation API client.

Uses the OpenAI-compatible /v1/images/generations endpoint.
Supports text-to-image and image-to-image via Seedream 5.0/4.5/4.0.
"""

import base64
import os
from typing import Literal

import httpx

DEFAULT_MODEL = "doubao-seedream-5-0-260128"
DEFAULT_BASE_URL = "https://ark.cn-beijing.volces.com/api/v3"


class SeedreamClient:
    """Synchronous Seedream image generation client.

    Usage:
        client = SeedreamClient(api_key="...")
        # text-to-image
        urls = client.generate(prompt="一只白猫")
        # image-to-image
        urls = client.generate(prompt="...", image=image_bytes)
    """

    def __init__(
        self,
        api_key: str | None = None,
        base_url: str = DEFAULT_BASE_URL,
        model: str = DEFAULT_MODEL,
    ):
        self.api_key = api_key or os.getenv("VOLC_ACCESS_KEY", "")
        self.base_url = base_url
        self.model = model

        if not self.api_key:
            raise ValueError(
                "VOLC_ACCESS_KEY environment variable is required"
            )

    def generate(
        self,
        prompt: str,
        image: bytes | None = None,
        size: str = "2048x2048",
        n: int = 1,
        response_format: Literal["url", "b64_json"] = "url",
        watermark: bool = False,
        stream: bool = False,
    ) -> list[dict]:
        """Generate image(s) via Seedream API.

        Args:
            prompt: Text description of the desired image.
            image: Optional reference image bytes for image-to-image.
            size: Image size, e.g. "2048x2048", "2K", "4K".
            n: Number of images to generate (1-4).
            response_format: "url" or "b64_json".
            watermark: Whether to add "AI生成" watermark.
            stream: Enable streaming mode.

        Returns:
            List of dicts with "url" or "b64_json" keys.
        """
        payload: dict = {
            "model": self.model,
            "prompt": prompt,
            "size": size,
            "n": n,
            "response_format": response_format,
            "watermark": watermark,
            "stream": stream,
            "sequential_image_generation": "disabled",
        }

        if image is not None:
            b64 = base64.b64encode(image).decode("utf-8")
            payload["image"] = f"data:image/png;base64,{b64}"

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        with httpx.Client(timeout=120) as client:
            resp = client.post(
                f"{self.base_url}/images/generations",
                json=payload,
                headers=headers,
            )
            if resp.status_code >= 400:
                detail = resp.text[:500]
                raise RuntimeError(
                    f"Seedream API returned {resp.status_code}: {detail}"
                )
            data = resp.json()

        return data.get("data", [])

    def generate_b64(
        self,
        prompt: str,
        image: bytes | None = None,
        size: str = "2048x2048",
    ) -> list[bytes]:
        """Convenience: generate and return raw image bytes directly."""
        results = self.generate(
            prompt=prompt,
            image=image,
            size=size,
            response_format="b64_json",
        )
        out = []
        for item in results:
            raw = item.get("b64_json")
            if raw:
                out.append(base64.b64decode(raw))
        return out
