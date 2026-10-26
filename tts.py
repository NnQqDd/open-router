#!/usr/bin/env python3
"""Generate speech with OpenRouter. Load OPEN_ROUTER_KEY from .env."""

import argparse
from pathlib import Path
import sys

from utilities import AudioGenerationError, generate_audio, redact

DEFAULT_MODEL = "fish-audio/s2.1-pro-free:free"


def main(argv=None):
    parser = argparse.ArgumentParser(
        description="OpenRouter TTS; reads OPEN_ROUTER_KEY from .env next to this script."
    )
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Full OpenRouter model ID (default: {DEFAULT_MODEL})")
    parser.add_argument("--text", required=True, help="Text to speak")
    parser.add_argument("--output", type=Path, default=Path("output.wav"),
                        help="Destination .wav or .mp3 (default: output.wav)")
    parser.add_argument("--voice", help="Provider voice ID, passed unchanged; omit for provider default")
    parser.add_argument("--speed", type=float, default=1.0,
                        help="Provider playback speed multiplier (default: 1.0)")
    parser.add_argument("--timeout", type=float, default=180,
                        help="HTTP timeout in seconds (default: 180)")
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args(argv)
    try:
        output = generate_audio(
            args.model, args.voice, args.text, args.speed, args.output,
            timeout=args.timeout, overwrite=args.overwrite,
        )
        print(f"Saved: {output}")
        print(f"Model: {args.model.strip()}")
        print(f"Voice: {args.voice if args.voice is not None else 'provider default'}")
        return 0
    except (AudioGenerationError, OSError) as exc:
        message = str(exc).replace("Set overwrite=True", "Use --overwrite")
        print(f"Error: {redact(message)}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        return 130


if __name__ == "__main__":
    sys.exit(main())
