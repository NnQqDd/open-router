#!/usr/bin/env python3
"""Query OpenRouter with inline text or the contents of a Markdown file."""

import argparse
import math
from pathlib import Path
import sys

from utilities import TextGenerationError, generate_text, redact


class QueryError(Exception):
    """An error that can be displayed to the user."""


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Query OpenRouter; reads OPEN_ROUTER_KEY from .env beside query.py.",
        epilog="Examples: query.py --prompt \"Hello\" | query.py --markdown prompt.md",
        allow_abbrev=False,
    )
    prompt_group = parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt", help="Prompt text")
    prompt_group.add_argument(
        "--markdown", type=Path, metavar="FILE",
        help="Read the entire prompt from a UTF-8 Markdown file",
    )
    parser.add_argument(
        "--model", default="openrouter/auto",
        help="OpenRouter model ID (default: openrouter/auto)",
    )
    parser.add_argument(
        "--timeout", type=float, default=180,
        help="HTTP timeout in seconds (default: 180)",
    )
    args = parser.parse_args(argv)
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise QueryError("--timeout must be a finite positive number.")
        model = args.model.strip()
        if not model:
            raise QueryError("--model must not be empty.")
        prompt = args.prompt
        if args.markdown is not None:
            prompt_path = args.markdown.expanduser()
            try:
                prompt = prompt_path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError) as exc:
                raise QueryError(f"Cannot read --markdown file '{prompt_path}': {exc}") from None
        if not prompt.strip():
            raise QueryError("The prompt must not be empty.")

        answer = generate_text(model, {
            "messages": [{"role": "user", "content": prompt}],
            "timeout": args.timeout,
        })
        # Preserve Unicode answers when stdout is redirected on Windows.
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        print(answer)
        return 0
    except (QueryError, TextGenerationError, OSError) as exc:
        print(f"Error: {redact(str(exc))}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
