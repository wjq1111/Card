import json
from pathlib import Path
from urllib import error, request


DEFAULT_BASE_URL = "https://api.minimaxi.com/anthropic"
DEFAULT_MODEL = "MiniMax-M2.7"


def read_api_key(path: str) -> str:
    key = Path(path).read_text(encoding="utf-8").strip()
    if not key:
        raise ValueError("API key file is empty: {}".format(path))
    return key


def _sdk_blocks(base_url: str, api_key: str, model: str, system: str, prompt: str, max_tokens: int):
    try:
        import anthropic
    except ImportError:
        return None

    client = anthropic.Anthropic(base_url=base_url, api_key=api_key)
    message = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        system=system,
        messages=[
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt,
                    }
                ],
            }
        ],
    )
    blocks = []
    for block in message.content:
        if block.type == "thinking":
            blocks.append(("thinking", block.thinking))
        elif block.type == "text":
            blocks.append(("text", block.text))
    return blocks


def _build_http_url(base_url: str) -> str:
    trimmed = base_url.rstrip("/")
    if trimmed.endswith("/v1"):
        return trimmed + "/messages"
    return trimmed + "/v1/messages"


def _http_blocks(base_url: str, api_key: str, model: str, system: str, prompt: str, max_tokens: int):
    payload = {
        "model": model,
        "max_tokens": max_tokens,
        "system": system,
        "messages": [
            {
                "role": "user",
                "content": prompt,
            }
        ],
    }
    body = json.dumps(payload).encode("utf-8")
    req = request.Request(
        _build_http_url(base_url),
        data=body,
        headers={
            "Authorization": "Bearer " + api_key,
            "Content-Type": "application/json",
        },
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=60) as response:
            data = json.loads(response.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise ValueError("MiniMax HTTP call failed with status {}: {}".format(exc.code, detail))
    except error.URLError as exc:
        raise ValueError("MiniMax HTTP call failed: {}".format(exc))

    blocks = []
    for block in data.get("content") or []:
        if not isinstance(block, dict):
            continue
        block_type = block.get("type", "")
        if block_type == "thinking":
            blocks.append(("thinking", block.get("thinking", "")))
        elif block_type == "text":
            blocks.append(("text", block.get("text", "")))
    return blocks


def create_message(
    *,
    api_key: str,
    system: str,
    prompt: str,
    base_url: str = DEFAULT_BASE_URL,
    model: str = DEFAULT_MODEL,
    max_tokens: int = 512,
    transport: str = "auto",
):
    blocks = None
    if transport in ("auto", "sdk"):
        blocks = _sdk_blocks(base_url, api_key, model, system, prompt, max_tokens)
        if blocks is None and transport == "sdk":
            raise ValueError("Anthropic SDK is unavailable in the current interpreter.")
    if blocks is None:
        blocks = _http_blocks(base_url, api_key, model, system, prompt, max_tokens)
    return blocks


def first_text_block(blocks) -> str:
    for block_type, text in blocks:
        if block_type == "text":
            return text
    raise ValueError("No text block returned by MiniMax response.")


def combined_text_blocks(blocks) -> str:
    texts = [text for block_type, text in blocks if block_type == "text" and text]
    if not texts:
        raise ValueError("No text block returned by MiniMax response.")
    return "\n".join(texts).strip()
