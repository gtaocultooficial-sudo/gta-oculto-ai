"""Optional, guarded Higgsfield API client for manual short-scene generation.

The feature is OFF by default. Credentials must only live in server environment
variables; never add API keys to source control, logs, browser code, or chat.
"""
from __future__ import annotations

import hmac
import os
import re
from typing import Any
from urllib.parse import urlparse

import requests

API_BASE = "https://api.higgsfield.ai"
MODEL_PATH = "alibaba/wan-3.0/text-to-video"
DEFAULT_DURATION = 3
DEFAULT_RESOLUTION = "480p"
DEFAULT_ASPECT_RATIO = "9:16"
MAX_PROMPT_LENGTH = 1500
REQUEST_TIMEOUT = (10, 25)


def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _api_key() -> str:
    # Higgsfield supplies one combined KEY_ID:KEY_SECRET credential.
    # Support the documented environment names, but never return it to callers.
    return (
        os.getenv("HIGGSFIELD_API_KEY", "").strip()
        or os.getenv("HF_KEY", "").strip()
        or os.getenv("HF_CREDENTIALS", "").strip()
    )


def feature_status() -> dict[str, Any]:
    enabled = _truthy(os.getenv("HIGGSFIELD_API_ENABLED", "0"))
    key_present = bool(_api_key())
    action_guard_present = bool(os.getenv("HIGGSFIELD_ACTION_TOKEN", "").strip())
    return {
        "enabled": enabled,
        "key_present": key_present,
        "action_guard_present": action_guard_present,
        "ready": enabled and key_present and action_guard_present,
        "model": MODEL_PATH,
        "duration_seconds": DEFAULT_DURATION,
        "resolution": DEFAULT_RESOLUTION,
        "aspect_ratio": DEFAULT_ASPECT_RATIO,
    }


def action_token_valid(provided: str | None) -> bool:
    expected = os.getenv("HIGGSFIELD_ACTION_TOKEN", "").strip()
    supplied = str(provided or "").strip()
    return bool(expected and supplied and hmac.compare_digest(expected, supplied))


def _headers() -> dict[str, str]:
    key = _api_key()
    if not key:
        raise RuntimeError("HIGGSFIELD_API_KEY_MISSING")
    return {
        "Authorization": f"Key {key}",
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def submit_scene(prompt: str) -> dict[str, Any]:
    """Submit one intentionally triggered, short, low-resolution vertical scene.

    This function never retries a POST: a timeout can be ambiguous, and a retry
    could create a second billable generation.
    """
    cfg = feature_status()
    if not cfg["enabled"]:
        return {"ok": False, "reason": "HIGGSFIELD_FEATURE_DISABLED"}
    if not cfg["key_present"]:
        return {"ok": False, "reason": "HIGGSFIELD_API_KEY_MISSING"}
    if not cfg["action_guard_present"]:
        return {"ok": False, "reason": "HIGGSFIELD_ACTION_TOKEN_MISSING"}

    prompt = str(prompt or "").strip()
    if not prompt:
        return {"ok": False, "reason": "PROMPT_REQUIRED"}
    if len(prompt) > MAX_PROMPT_LENGTH:
        return {"ok": False, "reason": "PROMPT_TOO_LONG", "max_length": MAX_PROMPT_LENGTH}

    payload = {
        "prompt": prompt,
        "duration": DEFAULT_DURATION,
        "resolution": DEFAULT_RESOLUTION,
        "aspect_ratio": DEFAULT_ASPECT_RATIO,
        "generate_audio": False,
        "enable_thinking": False,
    }
    try:
        response = requests.post(
            f"{API_BASE}/{MODEL_PATH}",
            headers=_headers(),
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.Timeout:
        return {
            "ok": False,
            "reason": "SUBMIT_TIMEOUT_CHECK_REQUESTS",
            "message": "O envio expirou e o resultado pode ser ambíguo. Confira a área Requests da Higgsfield antes de tentar novamente.",
        }
    except requests.RequestException:
        return {"ok": False, "reason": "HIGGSFIELD_NETWORK_ERROR"}

    if response.status_code in (401, 403):
        return {"ok": False, "reason": "HIGGSFIELD_CREDENTIALS_REJECTED"}
    if response.status_code == 402:
        return {"ok": False, "reason": "HIGGSFIELD_BALANCE_OR_PAYMENT_REQUIRED"}
    if response.status_code == 422:
        return {"ok": False, "reason": "HIGGSFIELD_INPUT_REJECTED"}
    if response.status_code == 429:
        return {"ok": False, "reason": "HIGGSFIELD_RATE_LIMIT"}
    if response.status_code >= 500:
        return {"ok": False, "reason": "HIGGSFIELD_PROVIDER_ERROR"}
    if not response.ok:
        return {"ok": False, "reason": f"HIGGSFIELD_HTTP_{response.status_code}"}

    try:
        data = response.json()
    except ValueError:
        return {"ok": False, "reason": "HIGGSFIELD_INVALID_RESPONSE"}
    request_id = str(data.get("request_id") or data.get("id") or "").strip()
    if not request_id or not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id):
        return {"ok": False, "reason": "HIGGSFIELD_REQUEST_ID_MISSING"}
    return {
        "ok": True,
        "request_id": request_id,
        "status": str(data.get("status") or "queued").lower(),
    }


def _find_video_url(value: Any) -> str:
    if isinstance(value, str):
        parsed = urlparse(value)
        return value if parsed.scheme == "https" and parsed.netloc else ""
    if isinstance(value, dict):
        direct = value.get("url") or value.get("video_url") or value.get("output_url")
        if direct:
            found = _find_video_url(direct)
            if found:
                return found
        for key in ("video", "output", "result", "outputs", "media", "data"):
            if key in value:
                found = _find_video_url(value[key])
                if found:
                    return found
    if isinstance(value, list):
        for item in value:
            found = _find_video_url(item)
            if found:
                return found
    return ""


def request_status(request_id: str) -> dict[str, Any]:
    """Read status and expose only a validated HTTPS media URL, never credentials."""
    if not feature_status()["enabled"]:
        return {"ok": False, "reason": "HIGGSFIELD_FEATURE_DISABLED"}
    try:
        headers = _headers()
    except RuntimeError:
        return {"ok": False, "reason": "HIGGSFIELD_API_KEY_MISSING"}

    request_id = str(request_id or "").strip()
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", request_id):
        return {"ok": False, "reason": "INVALID_REQUEST_ID"}
    try:
        response = requests.get(
            f"{API_BASE}/requests/{request_id}/status",
            headers=headers,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.Timeout:
        return {"ok": False, "reason": "STATUS_TIMEOUT"}
    except requests.RequestException:
        return {"ok": False, "reason": "HIGGSFIELD_NETWORK_ERROR"}

    if response.status_code in (401, 403):
        return {"ok": False, "reason": "HIGGSFIELD_CREDENTIALS_REJECTED"}
    if response.status_code == 404:
        return {"ok": False, "reason": "HIGGSFIELD_REQUEST_NOT_FOUND"}
    if response.status_code == 429:
        return {"ok": False, "reason": "HIGGSFIELD_RATE_LIMIT"}
    if not response.ok:
        return {"ok": False, "reason": f"HIGGSFIELD_HTTP_{response.status_code}"}
    try:
        data = response.json()
    except ValueError:
        return {"ok": False, "reason": "HIGGSFIELD_INVALID_RESPONSE"}

    state = str(data.get("status") or data.get("state") or "unknown").lower()
    video_url = _find_video_url(data) if state in {"completed", "complete", "succeeded", "success"} else ""
    return {
        "ok": True,
        "request_id": request_id,
        "status": state,
        "video_url": video_url or None,
        "message": (
            "Cena pronta. Baixe o arquivo pela URL gerada."
            if video_url
            else ("A geração foi concluída, mas a resposta não trouxe uma URL de vídeo reconhecível."
                  if state in {"completed", "complete", "succeeded", "success"}
                  else ("A geração falhou no provedor." if state in {"failed", "canceled", "cancelled", "nsfw"}
                        else "A cena ainda está sendo processada."))
        ),
    }
