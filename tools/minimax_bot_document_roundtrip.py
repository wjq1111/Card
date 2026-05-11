from __future__ import annotations

import argparse
import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = REPO_ROOT / "src"
for path in (SRC_ROOT, REPO_ROOT):
    path_text = str(path)
    if path_text not in sys.path:
        sys.path.insert(0, path_text)

from src.server.minimax_bots.document_io import SYSTEM_PROMPT, load_bot_document, write_bot_output
from src.server.minimax_bots.minimax_client import combined_text_blocks, create_message, read_api_key


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Read a MiniMax bot turn document and write the model reply back to it.")
    parser.add_argument("--document", required=True, help="Path to the markdown document containing MiniMax bot input/output sections.")
    parser.add_argument("--api-key-file", default="api.key", help="Path to the MiniMax API key file.")
    parser.add_argument("--transport", choices=("auto", "sdk", "http"), default="auto", help="MiniMax transport mode.")
    parser.add_argument("--max-tokens", type=int, default=2048, help="Maximum output tokens.")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    document = load_bot_document(args.document)
    api_key = read_api_key(args.api_key_file)
    blocks = create_message(
        api_key=api_key,
        system=SYSTEM_PROMPT,
        prompt=document.input_text,
        transport=args.transport,
        max_tokens=args.max_tokens,
    )
    output_text = combined_text_blocks(blocks)
    write_bot_output(args.document, output_text)
    print(output_text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
