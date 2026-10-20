# Model and pipeline research

Researched 17 October 2026. Model selection is an engineering judgment for the requested CPU / 8 GB RAM limit, not a measured ranking or a promise of human-level narration.

## Local script model

**Selected: Qwen3-4B-Instruct-2507 Q4_K_M.** The Ollama registry lists an explicit 4B instruction variant at about 2.5 GB. Using the explicit tag avoids a mutable generic `qwen3:4b` alias selecting a thinking variant. The app uses a short context, bounded source processing and CPU inference. This leaves more room than an 8B-class model for Windows and the browser. The 1.7B Q4_K_M option is about 1.4 GB and trades quality for headroom.

- [Ollama Qwen3 tags and weight sizes](https://registry.ollama.com/library/qwen3/tags)
- [Qwen3-4B-Instruct-2507 model card](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507)
- [Ollama chat API](https://docs.ollama.com/api/chat)
- [Ollama Windows portable distribution](https://docs.ollama.com/windows)

## Speech options compared

| Option | English / Arabic / Farsi | Decision |
|---|---|---|
| Piper medium voices | Separate voices for all three | Offline default; native Windows wheel, compact ONNX voices and no GPU. Limited emotional control. |
| Kokoro 82M | English supported; does not cover this complete language set | Excellent size candidate for English, but adding it does not solve Arabic and Farsi. Kept out of the base pipeline to reduce installation complexity. |
| Qwen3-TTS 0.6B | Its documented ten-language list omits Arabic and Farsi | Not a valid single-model solution for this brief. |
| OuteTTS 1B | Lists Arabic and English with high training coverage; Persian with moderate coverage | Plausible future experimental local backend. Its model-card language coverage is not evidence of reliable expressive output or tested Windows / 8 GB behavior. Not wired into this version. |
| ElevenLabs v3 | Lists all three, with emotional and nonverbal tags | Optional online expressive backend; requires key, voice access, credits and internet. |
| Azure Neural Speech | Lists English, Arabic and Persian voices | Optional online backend; emotion styles vary by voice and are not presumed for Arabic or Farsi. |

Sources:

- [Piper Python API: model loading and synthesis controls](https://github.com/OHF-Voice/piper1-gpl/blob/main/docs/API_PYTHON.md)
- [Piper 1.8.0 PyPI: Windows x64 wheel and GPL license](https://pypi.org/project/piper-tts/)
- [Official Piper voice manifest](https://huggingface.co/rhasspy/piper-voices/blob/main/voices.json)
- [Piper Persian voice directory](https://huggingface.co/rhasspy/piper-voices/tree/main/fa/fa_IR)
- [Kokoro model card](https://huggingface.co/hexgrad/Kokoro-82M)
- [Qwen3-TTS model card and language list](https://huggingface.co/Qwen/Qwen3-TTS-12Hz-0.6B-Base)
- [OuteTTS 1B model card and language coverage](https://huggingface.co/OuteAI/Llama-OuteTTS-1.0-1B)
- [ElevenLabs models and supported languages](https://elevenlabs.io/docs/overview/models)
- [ElevenLabs audio tags and delivery guidance](https://elevenlabs.io/docs/overview/capabilities/text-to-speech/best-practices)
- [ElevenLabs text-to-speech API](https://elevenlabs.io/docs/api-reference/text-to-speech/convert)
- [Azure supported voices and voice-specific styles](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/language-support)
- [Azure Speech REST / SSML API](https://learn.microsoft.com/en-us/azure/ai-services/speech-service/rest-text-to-speech)

ElevenLabs documentation also lists newer v4 models. This implementation uses the explicit v3 API model and documented expressive-tag workflow; it does not claim v3 is the newest or best overall voice model. It should be auditioned with the user's chosen voice in all intended languages.

## Installation and rendering

- [uv managed Python installation](https://docs.astral.sh/uv/guides/install-python/)
- [Pillow text direction / layout options](https://pillow.readthedocs.io/en/stable/reference/ImageDraw.html)
- [imageio-ffmpeg and bundled executables](https://github.com/imageio/imageio-ffmpeg)
- [FFmpeg documentation](https://ffmpeg.org/ffmpeg.html)

No large image/video-generation model is needed for template slides. Rendering uses the laptop's installed Arial fonts on Windows, with text shaping for Arabic/Farsi. A copied installation on a system without those fonts can use Noto Sans Arabic TTF files in `fonts/`.

## Slide design and animation

Slide layouts, palettes, artwork and transitions are local rules in `deck.py` and `visuals.py`; no image-generation model or design API is involved. Artwork is made only of circles, rectangles and polylines, so it can be drawn with Pillow and exported as SVG from the same primitives (no SVG parser or external file is executed). Transitions are FFmpeg's built-in [`xfade`](https://ffmpeg.org/ffmpeg-filters.html#xfade) filters; the zoom uses `scale` with per-frame evaluation followed by `crop`. The whole video is one filter graph, so no intermediate clips are encoded.

## Licenses and validation limits

Piper's current engine is GPL-3.0-or-later. Voice datasets and weights have their own model cards; for example Kareem's card points to its training dataset for license terms. Setup preserves those cards beside the models. Review them for the intended redistribution/commercial use rather than assuming every voice shares the engine's license. Online usage follows the provider account's terms.

No model weights or provider keys are bundled. The app downloads official release artifacts, checks upstream release checksums where available, and validates voice files against the official manifest's MD5 hashes for download integrity. Network access and model/provider behavior remain dependencies. Model quality, actual RAM peaks, speech pronunciation, rendering speed and final browser playback need a real installation run; this environment could not download the dependencies.
