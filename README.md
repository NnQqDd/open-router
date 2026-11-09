# Python CLI usage

Set `OPEN_ROUTER_KEY` in the environment or the repository's `.env`. WAV output
requires FFmpeg on PATH. All scripts accept `--help`.

## `query.py` — generate text

```bash
python query.py --prompt "Say hello in Vietnamese."
python query.py --markdown prompts/first.md --model openrouter/auto
```

| Argument | Meaning / default |
| --- | --- |
| `--prompt TEXT` | Inline prompt; choose exactly one of `--prompt` or `--markdown` |
| `--markdown FILE` | Read the prompt from a UTF-8 Markdown file |
| `--model ID` | OpenRouter model ID; default: `openrouter/auto` |
| `--timeout SECONDS` | Request timeout; default: `180` |

Prints the response to stdout.

## `generate_texts.py` — save multiple responses

```bash
python generate_texts.py --markdown prompts/first.md --N 100 --save-dir outputs/texts --json
```

Accepts the same `--prompt` / `--markdown`, `--model`, and `--timeout` arguments
as `query.py`, plus:

| Argument | Meaning / default |
| --- | --- |
| `--N COUNT` | Required total number of response files, including existing files; minimum: `1` |
| `--save-dir DIR` | Required output directory |
| `--json` | Save validated `.json` instead of `.txt`; retries invalid JSON |
| `--overwrite` | Regenerate existing numbered files; otherwise skip them |

Files are numbered from zero, padded to the width of `N - 1`. Rerun with the
same arguments to resume. With `--json`, the prompt must request JSON.

## `tts.py` — generate speech

```bash
python tts.py --text "Xin chào!" --output outputs/hello.mp3
```

| Argument | Meaning / default |
| --- | --- |
| `--text TEXT` | Required text to speak |
| `--model ID` | Full OpenRouter model ID; default: `fish-audio/s2.1-pro-free:free` |
| `--output FILE` | Destination `.wav` or `.mp3`; default: `output.wav` |
| `--voice ID` | Provider voice ID; omitted for the provider default |
| `--speed NUMBER` | Positive speed multiplier; default: `1.0` |
| `--timeout SECONDS` | Request timeout; default: `180` |
| `--overwrite` | Replace an existing output file |

## `generate_audios.py` — convert a directory to WAV

```bash
python generate_audios.py --text-dir outputs/texts --save-dir outputs/audio --start-idx 0 --end-idx 99
```

| Argument | Meaning / default |
| --- | --- |
| `--text-dir DIR` | Required input directory containing `.txt` and/or `.json` files |
| `--save-dir DIR` | Required WAV output directory; existing files are skipped |
| `--model ID` | Full OpenRouter model ID; default: `fish-audio/s2.1-pro-free:free` |
| `--voice ID` | Provider voice ID; omitted for the provider default |
| `--response-format FORMAT` | API format: `mp3` (default) or `pcm` (for Gemini TTS) |
| `--timeout SECONDS` | Request timeout per file; default: `180` |
| `--start-idx NUMBER` | Optional first numeric filename index, inclusive |
| `--end-idx NUMBER` | Optional last numeric filename index, inclusive |

JSON inputs require a non-empty `normalized_text` string. Each input becomes
`<stem>.wav`. Scans only the input directory; index bounds select numeric stems.
Rerun the same command to resume.

## `generate_audios_all_models.py` — generate both languages for every voice

```bash
python generate_audios_all_models.py --part-num-audios 20 --metadata-path .temp/PhoMT_test.csv --save-path outputs/all_models --resume
```

| Argument | Meaning |
| --- | --- |
| `--part-num-audios N` | Required count per language per voice: N Vietnamese + N English |
| `--metadata-path CSV` | Required UTF-8 CSV with `en` and `vi` columns |
| `--save-path DIR` | Required output root for `audios/` and `metadatas/` |
| `--resume` | Skip complete WAV/JSON pairs and retry missing or invalid WAVs |

Uses the ten-model comparison set with 84 voice profiles: `N=20` produces
3,360 recordings. Every profile reads the same first N non-empty Vietnamese
entries and last N non-empty English entries, in reverse order for English.
Microsoft Grant/Harper use `vi-VN` IDs for Vietnamese and `en-US` IDs for English.

Each WAV/JSON pair shares a UUIDv4 filename. JSON contains `model`, `text`,
the actual provider `voice` ID, and `language` (`vi` or `en`; `null` if unknown).
Resume also accepts older metadata without `language`, matches model/text/voice, and validates
the WAV; duplicate text occurrences count separately. Keep the CSV and selected
count the same when resuming. Metadata is saved before synthesis, so interrupted
recordings retain their UUID. Moderation rejections are remembered in `rejected/`;
the script takes the next text in the same language to fill that voice's quota.
Resume excludes those rejected texts. Other API errors stop the run; rerun with `--resume`.
Without `--resume`, the recording directories must be empty.
`tqdm` is optional for this script; when unavailable, it prints plain progress.
