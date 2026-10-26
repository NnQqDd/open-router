#!/usr/bin/env python3
"""Run one prompt repeatedly, skipping existing response files by default."""

import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
import tempfile
import time

from tqdm import tqdm

from utilities import TextGenerationError, generate_text, redact


class GenerateError(Exception):
    """An input or output error that can be displayed to the user."""


def _reject_json_constant(value):
    raise ValueError(f"{value} is not valid JSON.")


def _json_text(text):
    """Strip whitespace, a leading BOM, and an optional enclosing code fence."""
    text = text.strip().lstrip("\ufeff").strip()
    fenced = re.fullmatch(r"```(?:json)?[ \t]*\r?\n(.*?)\r?\n```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip().lstrip("\ufeff").strip()
    json.loads(text, parse_constant=_reject_json_constant)
    return text


def _save_response(text, output, overwrite=False):
    # Publish only a complete file; replace an existing one when requested.
    with tempfile.TemporaryDirectory(prefix=".openrouter-generate-", dir=output.parent) as tmp:
        temporary = Path(tmp) / "response"
        temporary.write_text(text, encoding="utf-8", newline="")
        if overwrite:
            os.replace(temporary, output)
        else:
            os.link(temporary, output)


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Run a prompt N times with OpenRouter and save the responses.",
        epilog="Example: generate_texts.py --markdown prompt.md --N 11 --save-dir outputs/run --json",
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
    parser.add_argument("--N", type=int, required=True,
                        help="Total response files wanted, including existing files")
    parser.add_argument("--save-dir", type=Path, required=True, help="Destination directory")
    parser.add_argument(
        "--json", action="store_true", dest="json_output",
        help="Save .json files; strip optional code fences and retry invalid JSON",
    )
    parser.add_argument(
        "--overwrite", action="store_true",
        help="Replace existing numbered response files",
    )
    args = parser.parse_args(argv)
    try:
        if args.N < 1:
            raise GenerateError("--N must be at least 1.")
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise GenerateError("--timeout must be a finite positive number.")
        model = args.model.strip()
        if not model:
            raise GenerateError("--model must not be empty.")
        prompt = args.prompt
        if args.markdown is not None:
            prompt_path = args.markdown.expanduser()
            try:
                prompt = prompt_path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError) as exc:
                raise GenerateError(f"Cannot read --markdown file '{prompt_path}': {exc}") from None
        if not prompt.strip():
            raise GenerateError("The prompt must not be empty.")

        save_dir = args.save_dir.expanduser().absolute()
        save_dir.mkdir(parents=True, exist_ok=True)
        width = len(str(args.N - 1))
        suffix = ".json" if args.json_output else ".txt"
        pending = []
        skipped = 0
        for index in range(args.N):
            output = save_dir / f"{index:0{width}d}{suffix}"
            if output.is_dir():
                raise GenerateError(f"'{output}' must be a file path, not a directory.")
            if os.path.lexists(output) and not args.overwrite:
                skipped += 1
            else:
                pending.append(output)
        # Check write permission before making a paid request.
        if pending:
            with tempfile.TemporaryFile(dir=save_dir):
                pass

        request = {
            "messages": [{"role": "user", "content": prompt}],
            "timeout": args.timeout,
        }
        saved = 0
        with tqdm(total=args.N, initial=skipped, desc="Generating", unit="response",
                  dynamic_ncols=True, file=sys.stderr) as progress:
            for output in pending:
                if output.is_dir():
                    raise GenerateError(f"'{output}' must be a file path, not a directory.")
                if os.path.lexists(output) and not args.overwrite:
                    skipped += 1
                    progress.update(1)
                    continue
                delay = 1
                while True:
                    try:
                        answer = generate_text(model, request)
                        if args.json_output:
                            try:
                                answer = _json_text(answer)
                            except ValueError:
                                raise GenerateError("The response is not valid JSON.") from None
                    except (TextGenerationError, GenerateError) as exc:
                        if (
                            isinstance(exc, TextGenerationError)
                            and exc.status_code is not None
                            and 400 <= exc.status_code < 500
                            and exc.status_code not in (408, 429)
                        ):
                            raise GenerateError(str(exc)) from None
                        tqdm.write(
                            f"Retrying {output.name} in {delay}s: {redact(str(exc))}",
                            file=sys.stderr,
                        )
                        time.sleep(delay)
                        delay = min(delay * 2, 30)
                        continue
                    try:
                        _save_response(answer, output, overwrite=args.overwrite)
                    except FileExistsError:
                        # Another writer may have finished this response during the request.
                        if args.overwrite or output.is_dir():
                            raise
                        skipped += 1
                    else:
                        saved += 1
                    progress.update(1)
                    break
        print(f"Saved {saved} responses to {save_dir}; skipped {skipped} existing files.")
        return 0
    except (GenerateError, OSError) as exc:
        print(f"Error: {redact(str(exc))}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
