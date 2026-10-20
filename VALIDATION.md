# Validation record

Last checked on Windows with Python 3.14 (the installer itself targets Python 3.11), Pillow 12 without RAQM (so the Arabic/Farsi reshaper fallback was in use), Piper 1.8.0 and the FFmpeg 7.1 build from imageio-ffmpeg.

## Verified

- `python -m unittest test_studio.py test_design.py`: 43 tests pass. 5 drawing tests are skipped when Pillow is missing and run otherwise.
- **Designed templates and animation, real run:** the English example (`examples/solar-lesson-en.json`, Vivid) was rendered through the actual pipeline with a real Piper English voice and real FFmpeg, producing a 51.9 s H.264/AAC MP4 whose length matches the narration (51.87 s). Frames taken at the fade-in and at the transitions between slides 1 and 2 and between slides 2 and 3 show the expected transition and zoom.
- The Arabic example (`examples/solar-lesson-ar.json`, Dark) was rendered the same way, with the Arabic Piper voice, giving a 86.5 s MP4 whose length matches the narration (86.46 s). Its slides were not inspected frame by frame.
- The sample video in `docs/` (`examples/explainer-studio-explained.json`, Vivid, 83.4 s) was made with the same real run. Rendering it exposed a layout bug (four steps overlapped), which is fixed.
- Every layout was drawn at 720p in English, Arabic and Farsi with 1 to 4 points, including 180-character points. Layouts that cannot hold the text fall back to a roomier one.
- English, Arabic and Farsi contact sheets were inspected by eye. Farsi slides were checked as images only.
- The browser UI loads with no console errors; template groups, palette buttons and animation switches appear; an imported project opens, redraws its slides and shows each slide's layout, artwork subject and transition.
- The local HTTP server served the UI and the project library and accepted the browser's token-bearing save request. The rejection of requests without the session token (HTTP 403) was checked in an earlier version and not re-run.

## Not verified

- The full dependency installer (`setup.ps1`) and the real Qwen model download were not re-run for this change.
- Real Qwen script generation, Farsi speech (the Farsi Piper voice was not installed on the test machine), the online speech providers, and 1080p encoding of a full video.
- Browser end-to-end generation of a video with the new template controls, and peak RAM / speed on an 8 GB laptop.
- RAQM-based text shaping (the reshaper fallback was what ran).

The unit tests replace speech and encoding with doubles in places; they check pipeline logic and file assembly, not voice or video quality. The first Windows setup runs real English, Arabic and Farsi voice preflights and stops if they fail.
