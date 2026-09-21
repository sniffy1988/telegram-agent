from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


class ReverseImageTool:
    name = "reverse_image"
    description = (
        "Reverse-search the photo the user sent in this message. "
        "No URL parameter; uses the attached Telegram photo only."
    )
    input_schema = {
        "type": "object",
        "properties": {},
    }

    async def execute(
        self, arguments: dict[str, Any], context: dict[str, Any]
    ) -> dict[str, Any]:
        photo_path = context.get("photo_path")
        if not photo_path or not Path(photo_path).is_file():
            return {"ok": False, "error": "no_photo_attached", "matches": []}
        try:
            from ddgs import DDGS

            path = Path(photo_path)
            caption = str(context.get("caption") or "").strip()
            search_q = caption or "similar images identify source"

            def _reverse() -> list[dict[str, str]]:
                rows: list[dict[str, str]] = []
                with DDGS() as ddgs:
                    for item in ddgs.images(search_q, max_results=5):
                        rows.append(
                            {
                                "title": str(item.get("title", ""))[:200],
                                "image_url": str(
                                    item.get("image", item.get("thumbnail", ""))
                                )[:800],
                                "source_url": str(item.get("url", ""))[:500],
                            }
                        )
                if not rows and caption:
                    with DDGS() as ddgs:
                        for item in ddgs.text(caption, max_results=5):
                            rows.append(
                                {
                                    "title": str(item.get("title", ""))[:200],
                                    "image_url": "",
                                    "source_url": str(
                                        item.get("href", item.get("url", ""))
                                    )[:500],
                                }
                            )
                _ = path  # photo kept for future visual backends
                return rows

            matches = await asyncio.to_thread(_reverse)
            if not matches:
                return {
                    "ok": False,
                    "error": "reverse_search_no_results",
                    "matches": [],
                }
            return {"ok": True, "matches": matches}
        except Exception as exc:
            logger.warning("reverse_image failed: %s", exc)
            return {"ok": False, "error": "reverse_search_failed", "matches": []}
