"""Gemini client and the per-patent extraction request."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor

from google import genai
from google.genai import types

from . import bq
from .prompt import SYSTEM
from .schema import Extraction

MODEL = "gemini-3.6-flash"  # gemini-3.6-pro costs ~10x more for equivalent output
REGION = "global"  # 3.x models are served only from global, not us-central1
THINKING_BUDGET = 0  # tested equal to the default budget on output quality


def client():
    """Return a Vertex AI Gemini client, billed to the project bq.py uses."""
    return genai.Client(
        vertexai=True,
        project=bq.project(),
        location=REGION,
        # 429 is retried with exponential backoff, so concurrency need not be
        # held low to avoid it.
        http_options=types.HttpOptions(
            retry_options=types.HttpRetryOptions(attempts=6, initial_delay=2)
        ),
    )


def extract_one(cl, patent: str, text: str) -> list[dict]:
    """Extract every measurement from one patent, in one call."""
    if not text:
        return []
    r = cl.models.generate_content(
        model=MODEL,
        contents=f"Patent {patent}\n\n{text}",
        config=types.GenerateContentConfig(
            system_instruction=SYSTEM,
            response_mime_type="application/json",
            response_schema=Extraction,
            temperature=0,  # deterministic; reduces run-to-run variation
            thinking_config=types.ThinkingConfig(thinking_budget=THINKING_BUDGET),
        ),
    )
    return [m.model_dump() | {"patent": patent} for m in r.parsed.measurements]


def extract_safe(cl, patent: str, text: str) -> list[dict]:
    """Extract, recording an error instead of raising, so one bad patent does
    not stop a batch."""
    try:
        return extract_one(cl, patent, text)
    except Exception as e:  # noqa: BLE001
        return [{"patent": patent, "error": f"{type(e).__name__}: {e}"[:300]}]


def extract_batch(cl, patents: list[str], texts: list[str], workers: int = 20):
    """Run extract_safe over many patents concurrently."""
    with ThreadPoolExecutor(workers) as pool:
        return list(pool.map(lambda a: extract_safe(cl, *a), zip(patents, texts)))
