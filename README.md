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
| `--speed` | `1.0` | Positive playback speed multiplier; support depends on the model |
| `--timeout` | `180` | HTTP timeout in seconds |
| `--overwrite` | Off | Allows replacing an existing output |

The client requests MP3 audio. For WAV output, FFmpeg converts it to signed
16-bit PCM, preserving the returned sample rate and channel count.

To generate speech from Python:

```python
from utilities import generate_audio

saved_path = generate_audio(
    model_id="fish-audio/s2.1-pro-free:free",
    voice_id=None,
    text="Xin chào!",
    speed=1.0,
    save_path="outputs/hello.mp3",
)
```

The helper creates parent directories, saves the audio, and returns its absolute
`pathlib.Path` without printing. Use `voice_id=None` for the provider's default
voice. It loads `OPEN_ROUTER_KEY` from the environment or `.env`, and raises
`AudioGenerationError` on failure. Optional keyword arguments are `timeout=180`
and `overwrite=False`. Existing output is preserved unless you explicitly set
`overwrite=True`.

The helper defaults to MP3 responses. Pass `response_format="pcm"` for models
such as Gemini TTS that require raw PCM; it converts 24 kHz, 16-bit mono PCM
to the requested file format using FFmpeg. `speed` is passed directly to OpenRouter;
models can support it, ignore it, or reject a non-default value. See the
[OpenRouter speech parameters](https://openrouter.ai/docs/guides/overview/multimodal/tts#request-parameters).

## Generate text

```powershell
python query.py --prompt "Hello" --model google/gemini-3.1-flash-lite
python query.py --markdown prompt.md
```

The text CLI uses the shared helper in `utilities.py`:

```python
from utilities import generate_text

text = generate_text("google/gemini-3.1-flash-lite", "Say hello in Vietnamese.")
```

The helper loads `OPEN_ROUTER_KEY` from the environment or `.env` and returns
only the response text, preserving its whitespace. It raises
`TextGenerationError` on failure. It also accepts a chat request dictionary
with `messages`, optional OpenRouter parameters such as `response_format`,
and a local `timeout` in seconds (default: 180).

## Generate multiple responses

`generate_texts.py` accepts the same `--prompt` / `--markdown`, `--model`, and
`--timeout` arguments as `query.py`. It runs the same prompt independently
to fill `--N` numbered response files under `--save-dir`, skipping files
that already exist:

```powershell
python generate_texts.py --markdown prompts/first.md --model google/gemini-3.1-flash-lite --N 11 --save-dir outputs/run --json
python generate_texts.py --prompt "Return a JSON object describing a city." --N 101 --save-dir outputs/cities --json
```

Numbering starts at zero and uses the width of `N - 1`: `N=10` produces
`0.txt` through `9.txt`, `N=11` produces `00.txt` through `10.txt`, and `N=101`
produces `000.txt` through `100.txt`. Text responses are saved verbatim.

A tqdm progress bar on stderr shows completed responses, elapsed time, and
estimated time remaining. Existing files count as complete when the bar starts;
new responses advance it after saving. Retry messages appear above the bar.

With `--json`, files use `.json`. The script trims whitespace and a leading
BOM, removes an optional enclosing Markdown code fence, and checks JSON
syntax. It accepts any valid JSON value without schema or content checks,
and preserves the JSON's formatting. It does not extract JSON from prose
or repair malformed JSON. Make sure your prompt asks for JSON.

Network failures, HTTP 408/429 and server errors, and invalid JSON are retried
without a limit for the same file index, with delays starting at 1 second and
capped at 30 seconds. Other HTTP 4xx errors (such as an invalid model ID,
authentication failure, or insufficient credits) stop immediately. A
successful run leaves all `N` numbered destinations present. Existing files are
skipped without API requests or content validation. Ctrl+C stops the run and
keeps completed files; rerun the same command to generate only missing files.
Keep `--N`, `--save-dir`, and the output format the same when resuming so the
filenames match. Add `--overwrite` to regenerate existing numbered responses;
each existing file stays intact until its new response is ready to save.
The final summary reports saved and skipped counts. Directories at response
paths and file writing errors stop the run.

## Generate audio from a directory

```bash
python3 generate_audios.py --model fish-audio/s2.1-pro-free:free --timeout 180 --text-dir outputs/first-1000-lite --save-dir outputs/audio --start-idx 0 --end-idx 999
```

Add `--voice "PROVIDER_VOICE_ID"` for an explicit voice, or omit it for the
provider default. The default model matches `tts.py`; the default timeout is
180 seconds per request. FFmpeg must be on PATH to produce WAV audio.
Use `--response-format pcm` for Gemini TTS; the default API format is `mp3`.

The script reads `.txt` files as UTF-8 text and `.json` files as JSON objects
with a non-empty string field `normalized_text`. Other JSON fields are ignored.
Each input produces a WAV with the same filename stem, such as `007.json` →
`007.wav`. It scans the input directory directly, without visiting subdirectories.

Both index bounds are optional and **inclusive**, and match the number in a
filename: `--start-idx 10 --end-idx 20` selects `010.txt` through `020.txt`
(or `.json`), including both endpoints. Either bound may be omitted. With a
bound supplied, files without numeric stems are ignored. Without bounds, all
`.txt` and `.json` files are selected. Numbered files run in numeric order,
followed by other filenames in alphabetical order.

Existing WAV destinations are skipped without API calls or input validation,
and tqdm counts them as complete. Rerun the same command to resume. Pending
inputs are validated before any speech requests; two inputs with the same stem
are rejected because they would share an output. Generation runs sequentially
at speed 1.0 and stops on an API or file error. Ctrl+C keeps completed WAV files.

## Compare ten speech models

```bash
./10_models.sh
```

This generates 100 WAVs per model from input indices 0–99 in `outputs/first`,
using the same texts for each model. The ten models are Gemini 3.8 Flash TTS,
Gemini 3.8 Flash Lite TTS, Gemini 3.1 Flash TTS Preview, Eleven v4, Eleven v4
Turbo, Eleven v3, MAI-Voice-2.1, MAI-Voice-2.1-Flash, MiniMax Speech 2.8 HD,
and MiniMax Speech 2.8 Turbo. These are a curated comparison set, not a quality
ranking. Model and preset voice IDs were checked against the
[OpenRouter speech catalog](https://openrouter.ai/api/v1/models?output_modalities=speech)
on 26 October 2026.

Most models use ten voices, each reading ten texts. The MAI models use their
two Vietnamese voices, each reading fifty texts, because the voice locale sets
their synthesis language. WAVs are grouped under
`outputs/10_models/<model>/<voice>/<input-stem>.wav`. Gemini uses PCM requests;
the other selected models use MP3 requests. Existing WAVs are skipped, so the
same command resumes an interrupted run. The script stops on an error.

Preview all commands without speech requests:

```bash
DRY_RUN=1 ./10_models.sh
```

Environment overrides: `PYTHON` (default `python3`), `TEXT_DIR`, `SAVE_ROOT`,
`TIMEOUT` (default `180`), and `START_IDX` (default `0`, selecting 100 consecutive
indices). For example, `PYTHON=.venv/bin/python TIMEOUT=300 ./10_models.sh`.
The script validates all 100 source texts before requesting speech. It uses
the repository's existing `OPEN_ROUTER_KEY` configuration.

## Files

```text
tts.py                                     Speech CLI
query.py                                   Text query CLI
generate_texts.py                          Repeated prompt generation CLI
generate_audios.py                         Batch text/JSON to WAV CLI
10_models.sh                               Ten-model speech sample comparison
utilities.py                               Shared text and audio generation helpers
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
