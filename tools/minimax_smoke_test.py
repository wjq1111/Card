import argparse
from pathlib import Path
import sys


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from src.server.minimax_bots.minimax_client import create_message, first_text_block, read_api_key


DEFAULT_SYSTEM = "You are a concise assistant helping verify API connectivity."
DEFAULT_PROMPT = "Reply with exactly: MiniMax API call succeeded."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Smoke-test MiniMax Anthropic-compatible API access.")
    parser.add_argument(
        "--api-key-file",
        default="api.key",
        help="Path to the MiniMax API key file. Default: api.key",
    )
    parser.add_argument(
        "--base-url",
        default="https://api.minimaxi.com/anthropic",
        help="Anthropic-compatible base URL. Default: https://api.minimaxi.com/anthropic",
    )
    parser.add_argument(
        "--model",
        default="MiniMax-M2.7",
        help="Model name. Default: MiniMax-M2.7",
    )
    parser.add_argument(
        "--system",
        default=DEFAULT_SYSTEM,
        help="System prompt for the smoke test.",
    )
    parser.add_argument(
        "--prompt",
        default=DEFAULT_PROMPT,
        help="User prompt for the smoke test.",
    )
    parser.add_argument(
        "--max-tokens",
        type=int,
        default=128,
        help="Maximum output tokens for the test call.",
    )
    parser.add_argument(
        "--transport",
        choices=("auto", "sdk", "http"),
        default="auto",
        help="Call transport. 'auto' prefers the Anthropic SDK and falls back to HTTP.",
    )
    return parser.parse_args()


def emit_blocks(blocks) -> int:
    saw_text = False
    for block_type, text in blocks:
        if block_type == "thinking":
            print("=== thinking ===")
            print(text)
            print()
        elif block_type == "text":
            saw_text = True
            print("=== text ===")
            print(text)
            print()

    if not saw_text:
        print("No text block returned by MiniMax response.", file=sys.stderr)
        return 1
    return 0


def main() -> int:
    args = parse_args()
    api_key = read_api_key(str(Path(args.api_key_file)))
    try:
        blocks = create_message(
            api_key=api_key,
            system=args.system,
            prompt=args.prompt,
            base_url=args.base_url,
            model=args.model,
            max_tokens=args.max_tokens,
            transport=args.transport,
        )
    except ValueError as exc:
        raise SystemExit(str(exc))
    return emit_blocks(blocks)


if __name__ == "__main__":
    raise SystemExit(main())
