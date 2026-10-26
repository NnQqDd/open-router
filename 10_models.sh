#!/usr/bin/env bash
# 10 models x 100 texts = 1,000 WAVs, with multiple preset voices per model.
# Verified model/voice IDs on 2026-10-26:
# https://openrouter.ai/api/v1/models?output_modalities=speech
# https://openrouter.ai/docs/guides/overview/multimodal/tts
# Run: ./10_models.sh | Preview without speech requests: DRY_RUN=1 ./10_models.sh
set -euo pipefail

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd -- "$SCRIPT_DIR"
PYTHON="${PYTHON:-python3}"
TEXT_DIR="${TEXT_DIR:-outputs/texts/first}"
SAVE_ROOT="${SAVE_ROOT:-$SCRIPT_DIR/outputs/10_models}"
TIMEOUT="${TIMEOUT:-180}"
START_IDX="${START_IDX:-0}"
DRY_RUN="${DRY_RUN:-0}"

if [[ "$DRY_RUN" != 0 && "$DRY_RUN" != 1 ]]; then
    printf 'DRY_RUN must be 0 or 1.\n' >&2
    exit 1
fi
if [[ "$DRY_RUN" == 0 ]] && ! command -v ffmpeg >/dev/null 2>&1; then
    printf 'FFmpeg must be installed and on PATH.\n' >&2
    exit 1
fi

# Validate all 100 texts before any model can incur speech charges.
"$PYTHON" - "$TEXT_DIR" "$START_IDX" "$TIMEOUT" <<'PY'
import math
from pathlib import Path
import sys

from generate_audios import GenerateAudiosError, _read_text, _select_sources

try:
    directory = Path(sys.argv[1]).expanduser().absolute()
    if not sys.argv[2].isascii() or not sys.argv[2].isdecimal():
        raise ValueError("START_IDX must contain only decimal digits.")
    start = int(sys.argv[2])
    timeout = float(sys.argv[3])
    if start < 0 or not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("START_IDX must be non-negative and TIMEOUT finite and positive.")
    sources = _select_sources(directory, start, start + 99)
    indexed = {}
    for source in sources:
        index = int(source.stem)
        if index in indexed:
            raise ValueError(f"More than one input file has index {index}.")
        indexed[index] = source
        _read_text(source)
    missing = sorted(set(range(start, start + 100)) - indexed.keys())
    if missing:
        raise ValueError(f"Expected 100 texts; missing indices: {missing}")
except (ValueError, OSError, GenerateAudiosError) as exc:
    raise SystemExit(f"Input check failed: {exc}") from None
print(f"Validated 100 texts, indices {start} through {start + 99}, in {directory}")
PY
# Normalize decimal input so values such as START_IDX=008 work in Bash arithmetic.
START_IDX=$((10#$START_IDX))

gemini_voices=(Kore Puck Charon Zephyr Fenrir Leda Orus Aoede Callirrhoe Autonoe)
eleven_voices=(george sarah adam alice bella brian charlie daniel jessica laura)
minimax_voices=(
    English_expressive_narrator English_radiant_girl English_magnetic_voiced_man
    English_compelling_lady1 English_Aussie_Bloke English_captivating_female1
    English_Upbeat_Woman English_Trustworth_Man English_CalmWoman English_Gentle-voiced_man
)

model_number=0
run_model() {
    local model="$1" format="$2"
    shift 2
    local -a voices=("$@")
    local count="${#voices[@]}"
    local per_voice=$((100 / count))
    local model_slug="${model//\//__}"
    local voice voice_slug first last position=0
    local -a command
    model_number=$((model_number + 1))
    printf '\nModel %d/10: %s (%d voices, %d texts per voice)\n' \
        "$model_number" "$model" "$count" "$per_voice"
    for voice in "${voices[@]}"; do
        voice_slug="${voice//[^a-zA-Z0-9._-]/_}"
        first=$((START_IDX + position * per_voice))
        last=$((first + per_voice - 1))
        command=(
            "$PYTHON" "$SCRIPT_DIR/generate_audios.py"
            --model "$model" --voice "$voice" --response-format "$format"
            --timeout "$TIMEOUT" --text-dir "$TEXT_DIR"
            --save-dir "$SAVE_ROOT/$model_slug/$voice_slug"
            --start-idx "$first" --end-idx "$last"
        )
        printf '  Voice %s: text indices %d-%d\n' "$voice" "$first" "$last"
        if [[ "$DRY_RUN" == 1 ]]; then
            printf '%q ' "${command[@]}"
            printf '\n'
        else
            "${command[@]}"
        fi
        position=$((position + 1))
    done
}

# Same 100 texts for each model. Voices change every 10 texts (50 for MAI).
# Gemini TTS accepts PCM only; the shared audio helper converts it to WAV.
run_model google/gemini-3.8-flash-tts pcm "${gemini_voices[@]}"
run_model google/gemini-3.8-flash-lite-tts pcm "${gemini_voices[@]}"
run_model google/gemini-3.1-flash-tts-preview pcm "${gemini_voices[@]}"
run_model elevenlabs/eleven-v4 mp3 "${eleven_voices[@]}"
run_model elevenlabs/eleven-v4-turbo mp3 "${eleven_voices[@]}"
run_model elevenlabs/eleven-v3 mp3 "${eleven_voices[@]}"
run_model microsoft/mai-voice-2.1 mp3 \
    vi-VN-Grant:MAI-Voice-2.1 vi-VN-Harper:MAI-Voice-2.1
run_model microsoft/mai-voice-2.1-flash mp3 \
    vi-VN-Grant:MAI-Voice-2.1-Flash vi-VN-Harper:MAI-Voice-2.1-Flash
run_model minimax/speech-2.8-hd mp3 "${minimax_voices[@]}"
run_model minimax/speech-2.8-turbo mp3 "${minimax_voices[@]}"

if [[ "$DRY_RUN" == 1 ]]; then
    printf '\nPreview complete: 1,000 WAVs planned; no speech requests made.\n'
else
    printf '\nComplete: 100 WAVs per model, grouped by model and voice under %s\n' "$SAVE_ROOT"
fi
