#!/usr/bin/env python3
"""Query OpenRouter with inline text or the contents of a Markdown file."""

import argparse
import json
import math
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request

try:
    from dotenv import load_dotenv
except ImportError:
    raise SystemExit("Install the dependency: python -m pip install python-dotenv")

ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


class QueryError(Exception):
    """An error that can be displayed to the user."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        # Avoid forwarding the API key to another URL.
        return None


def redact(message, key):
    if key:
        message = message.replace(key, "[REDACTED]")
    return re.sub(r"sk-or-[A-Za-z0-9_-]+", "[REDACTED]", message)


def error_detail(data):
    if not isinstance(data, dict):
        return ""
    error = data.get("error")
    if isinstance(error, dict):
        error = error.get("message")
    return error if isinstance(error, str) else ""


def request_completion(prompt, model, key, timeout):
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "stream": False,
    }
    request = urllib.request.Request(
        ENDPOINT,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method="POST",
    )
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=timeout) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = error_detail(json.loads(exc.read(65536)))
        except (ValueError, OSError):
            pass
        hints = {
            401: "Check OPEN_ROUTER_KEY in .env.",
            402: "Check your balance and key spending limit.",
            429: "The request was rate limited; try again later.",
        }
        detail = redact(detail, key).replace("\r", " ").replace("\n", " ")[:500]
        message = detail or hints.get(exc.code, "Check the model and provider.")
        raise QueryError(f"OpenRouter HTTP {exc.code}: {message}") from None
    except (urllib.error.URLError, TimeoutError, OSError):
        raise QueryError("Could not reach OpenRouter or the request timed out.") from None
    except ValueError:
        raise QueryError("OpenRouter returned invalid JSON.") from None

    if isinstance(data, dict) and "error" in data:
        detail = redact(error_detail(data), key).replace("\r", " ").replace("\n", " ")[:500]
        raise QueryError(f"OpenRouter error: {detail or 'The request failed.'}")
    try:
        message = data["choices"][0]["message"]
        content = message.get("content")
    except (KeyError, IndexError, TypeError, AttributeError):
        raise QueryError("OpenRouter returned an unexpected response.") from None
    if not isinstance(content, str) or not content.strip():
        refusal = message.get("refusal")
        if isinstance(refusal, str) and refusal.strip():
            raise QueryError(f"Model refused the request: {refusal}")
        raise QueryError("OpenRouter returned no text.")
    return content


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="Query OpenRouter; reads OPEN_ROUTER_KEY from .env beside query.py.",
        epilog="Examples: query.py --prompt \"Hello\" | query.py --prompt-md prompt.md",
        allow_abbrev=False,
    )
    prompt_group = parser.add_mutually_exclusive_group(required=True)
    prompt_group.add_argument("--prompt", help="Prompt text")
    prompt_group.add_argument(
        "--prompt-md", type=Path, metavar="FILE",
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
    key = ""
    try:
        if not math.isfinite(args.timeout) or args.timeout <= 0:
            raise QueryError("--timeout must be a finite positive number.")
        model = args.model.strip()
        if not model:
            raise QueryError("--model must not be empty.")
        prompt = args.prompt
        if args.prompt_md is not None:
            prompt_path = args.prompt_md.expanduser()
            try:
                prompt = prompt_path.read_text(encoding="utf-8-sig")
            except (OSError, UnicodeError) as exc:
                raise QueryError(f"Cannot read --prompt-md file '{prompt_path}': {exc}") from None
        if not prompt.strip():
            raise QueryError("The prompt must not be empty.")

        load_dotenv(Path(__file__).with_name(".env"), encoding="utf-8-sig")
        key = os.getenv("OPEN_ROUTER_KEY", "").strip()
        if not key:
            raise QueryError("Set OPEN_ROUTER_KEY=your_key in .env beside query.py.")
        if any(char.isspace() for char in key):
            raise QueryError("OPEN_ROUTER_KEY must not contain whitespace.")

        answer = request_completion(prompt, model, key, args.timeout)
        # Preserve Unicode answers when stdout is redirected on Windows.
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8")
        print(answer)
        return 0
    except (QueryError, OSError) as exc:
        print(f"Error: {redact(str(exc), key)}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
