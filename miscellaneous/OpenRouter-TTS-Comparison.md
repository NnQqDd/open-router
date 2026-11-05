# OpenRouter TTS Model Comparison

Checked: **21 October 2026**

This comparison covers the 25 models listed in the [OpenRouter text-to-speech collection](https://openrouter.ai/collections/text-to-speech-models).

## Pricing basis

The final two columns show **estimated USD per 1 million input text tokens**. These are budgeting estimates, not official per-token tariffs: most models bill by characters, UTF-8 bytes, or generated audio duration.

Assumptions:

- 1 input text token ≈ 4 English characters / 4 UTF-8 bytes.
- Speech ≈ 1,000 characters per minute.
- Gemini estimates include input text and generated audio charges, using 25 audio tokens per second.
- Estimates exclude taxes, payment fees, applicable BYOK fees, and external voice-creation charges.
- Actual costs depend on language, tokenization, speaking speed, and current discounts.

Conversion examples:

- Character-billed model: price per 1M input tokens ≈ 4 × price per 1M characters.
- Gemini 3.8 Flash TTS: $0.50 text input + (6M audio tokens × $9 / 1M audio tokens) ≈ $54.50.
- Seed Audio 1.0: 4M characters ÷ 1,000 characters/minute × $0.15/minute ≈ $600.

## Open weights and open source

**Open weights does not automatically mean open source.** Open weights means the model parameters are downloadable. The license can still restrict commercial use or redistribution. The [OSI Open Source AI Definition](https://opensource.org/ai/open-source-ai-definition) also requires appropriate freedoms and released code/data information.

The release column identifies the actual license or public-weight status. “Apache-2.0 code + weights” describes the released artifacts; it is not a certification that the complete training release satisfies every OSI requirement.

## Comparison

- **OR:** available directly through OpenRouter with an OpenRouter API key.
- **Native:** the provider's own API or a local deployment.
- **BYOK:** bring your own provider API key, connected to OpenRouter.
- **—:** cloning is not exposed directly through the listed OpenRouter endpoint.
- Voice counts are the IDs listed in OpenRouter's models API when checked; they are not necessarily the provider's complete voice catalog.

| Model | Open release / license | Voice cloning supported? | Select voice IDs on OR? | TTS: estimated USD / 1M input tokens | Voice clone on OR: estimated USD / 1M input tokens |
|---|---|---|---|---:|---:|
| Gemini 3.8 Flash TTS | Closed | Yes; Google setup [1] | Yes — 30 listed | ≈$54.50 | Setup required |
| Gemini 3.8 Flash Lite TTS | Closed | Yes; Google setup [1] | Yes — 30 listed | ≈$36.50 | Setup required |
| Gemini 3.1 Flash TTS Preview | Closed | No | Yes — 30 listed | ≈$121 | — |
| Kokoro 82M | [Apache-2.0 code + weights](https://huggingface.co/hexgrad/Kokoro-82M) | No | Yes — 54 listed | ≈$2.48 | — |
| Fish Drama 3 | [Open weights; restricted license](https://huggingface.co/fishaudio/drama-3/blob/main/LICENSE) | Yes; OR | Yes — Fish voice IDs | ≈$8 | ≈$8 |
| ElevenLabs v4 | Closed | Yes; BYOK [2] | Yes — 21 listed | ≈$320 | BYOK required |
| ElevenLabs v4 Turbo | Closed | Yes; BYOK [2] | Yes — 21 listed | ≈$160 | BYOK required |
| Grok Voice TTS 1.0 | Closed | Yes; [native, gated](https://docs.x.ai/developers/model-capabilities/audio/custom-voices) | Yes — 5 listed | ≈$60 | — |
| Fish S2.1 Pro Free | No public weights identified [4] | Yes; OR | Yes — Fish voice IDs | $0 | $0 |
| Fish S2.1 Pro | No public weights identified [4] | Yes; OR | Yes — Fish voice IDs | ≈$60 | ≈$60 |
| ElevenLabs Turbo v2.5 | Closed | Yes; BYOK [2] | Yes — 21 listed | ≈$160 | BYOK required |
| ElevenLabs v3 | Closed | Yes; BYOK [2] | Yes — 21 listed | ≈$320 | BYOK required |
| ElevenLabs Flash v2.5 | Closed | Yes; BYOK [2] | Yes — 21 listed | ≈$160 | BYOK required |
| MAI-Voice-2 | Closed | Yes; Azure approval [3] | Yes — 4 listed | ≈$88 | — |
| MAI-Voice-2.1-Flash | Closed | Yes; Azure approval [3] | Yes — 97 listed | ≈$60 | — |
| ElevenLabs Multilingual v2 | Closed | Yes; BYOK [2] | Yes — 21 listed | ≈$320 | BYOK required |
| MAI-Voice-2.1 | Closed | Yes; Azure approval [3] | Yes — 97 listed | ≈$88 | — |
| Seed Audio 1.0 | Closed | Yes; OR | Yes — Seed speaker IDs | ≈$600 | ≈$600 |
| Qwen-Audio-3.0-TTS Plus | Closed | Yes; [native](https://www.alibabacloud.com/help/en/model-studio/voice-clone-design-http-api) | Yes — 2 listed | ≈$80 | — |
| HeyGen Voice Turbo | Closed | Yes; OR | Yes — 10 listed | ≈$16 | ≈$16 |
| Deepgram Aura-2 | Closed | No documented public cloning | Yes — 90 listed | ≈$120 | — |
| MiniMax Speech 2.8 HD | Closed | Yes; [native](https://platform.minimax.io/docs/pricing/overview) | Yes — 45 listed | ≈$400 | — |
| Qwen-Audio-3.0-TTS Flash | Closed | Yes; [native](https://www.alibabacloud.com/help/en/model-studio/voice-clone-design-http-api) | Yes — 2 listed | ≈$60 | — |
| Voxtral Mini TTS | [Open weights; CC BY-NC 4.0](https://huggingface.co/mistralai/Voxtral-4B-TTS-2603) | Yes; [local/native](https://docs.mistral.ai/models/voxtral-tts-26-03) | Yes — 30 listed | ≈$64 | — |
| MAI-Voice-2-Flash | Closed | Yes; Azure approval [3] | Yes — 4 listed | ≈$60 | — |

## Capability and license notes

Selecting a preset voice ID is a separate feature from cloning your own voice. In OpenRouter speech requests, the voice is selected with the voice parameter. Compatible endpoints accept a reference recording through input_references for direct cloning.

1. **Google setup:** create the cloned voice through [Google's Voices API](https://ai.google.dev/gemini-api/docs/voice-replication). The model supports cloned voice IDs, but OpenRouter does not expose direct reference-audio cloning on the listed Gemini endpoints.
2. **ElevenLabs BYOK:** account-specific cloned voices require an [ElevenLabs API key connected through BYOK](https://openrouter.ai/blog/announcements/elevenlabs-on-openrouter/). Their charges and account requirements apply.
3. **Microsoft approval:** [instant cloning requires gated Azure access](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/mai-voices#custom-voice---personal-voiceinstant-voice-cloning-gated-access). The listed OpenRouter endpoints do not expose reference-audio cloning.
4. **Fish S2.1 Pro:** the free API is distinct from a public checkpoint release. Fish's [official repository](https://github.com/fishaudio/fish-speech) lists Drama 3 and S2-Pro as downloadable models.
5. **Drama 3:** its community license allows certain commercial uses below $500,000 annual revenue; offering a hosted TTS, cloning, or inference service requires a separate license. See the [publisher's license explanation](https://fish.audio/blog/fish-audio-drama-3/).
6. **Voxtral:** the downloadable model uses CC BY-NC 4.0, which restricts commercial use. Its local/native cloning capability is separate from OpenRouter endpoint availability.
7. **Grok:** native custom voices have regional and access restrictions; consult the linked xAI documentation.

## Sources

- [OpenRouter TTS collection and advertised prices](https://openrouter.ai/collections/text-to-speech-models)
- [OpenRouter speech models API and supported voice IDs](https://openrouter.ai/api/v1/models?output_modalities=speech)
- [OpenRouter TTS parameters and voice cloning](https://openrouter.ai/docs/guides/overview/multimodal/tts)
- [Google Gemini API pricing and audio token conversion](https://ai.google.dev/gemini-api/docs/pricing)
- [OSI Open Source AI Definition](https://opensource.org/ai/open-source-ai-definition)