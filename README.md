# OpenRouter TTS

Python CLI for OpenRouter's hosted speech API. Requires Python 3.10+.

## Setup

From this repository's directory:

```powershell
python -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
```

Set your key in the existing or newly copied `.env`:

```dotenv
OPEN_ROUTER_KEY=your_openrouter_key
```

The script reads `.env` beside `tts.py`. Existing environment variables take priority.
WAV output requires FFmpeg on PATH; MP3 output does not.

## Generate speech

```powershell
python tts.py --text "Hello!" --output outputs/hello.mp3
```

The default model is `fish-audio/s2.1-pro-free:free`, listed at $0 on OpenRouter
when checked on 23 October 2026. The free tier has no production latency or
availability guarantees.

Use a different model or voice by passing the provider's full IDs:

```powershell
python tts.py --model microsoft/mai-voice-2.1-flash --voice "vi-VN-Harper:MAI-Voice-2.1-Flash" --text "Xin chao!" --output outputs/vietnamese.wav
```

Model IDs and voice IDs are passed directly to OpenRouter. There are no model
aliases or language-to-voice mappings. If `--voice` is omitted, the request omits
`voice` so the provider can use its default. Models without a provider default
require an explicit `--voice`. Supported voices and language behavior depend on
the selected model.

## Flags

| Flag | Default | Meaning |
| --- | --- | --- |
| `--model` | `fish-audio/s2.1-pro-free:free` | Full OpenRouter `provider/model` ID |
| `--text` | Required | Text to speak |
| `--output` | `output.wav` | Destination `.wav` or `.mp3`, relative to the current working directory |
| `--voice` | Omitted | Provider voice ID, passed unchanged |
| `--timeout` | `180` | HTTP timeout in seconds |
| `--overwrite` | Off | Allows replacing an existing output |

The client requests MP3 audio. For WAV output, FFmpeg converts it to signed
16-bit PCM, preserving the returned sample rate and channel count.

## Files

```text
tts.py                                     Speech CLI
query.py                                   Text query CLI
requirements.txt                           Python dependency
.env.example                               Configuration template
.env                                       Local credential (ignored by Git)
examples/OpenRouter_TTS_Vietnamese_Test.txt  Example transcript
outputs/                                   Generated audio (ignored by Git)
```

## References

- [Default model and current pricing](https://openrouter.ai/fish-audio/s2.1-pro-free:free)
- [OpenRouter speech endpoint, voices, and formats](https://openrouter.ai/docs/guides/overview/multimodal/tts)
- [python-dotenv configuration](https://bbc2.github.io/python-dotenv/)
