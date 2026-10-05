# Third-party notices — Zetalvx Image Lab — SDXL Edition

The application source is distributed under Apache-2.0. Third-party software,
model weights, datasets, trademarks and external services retain their own
licenses and terms. This document is a practical boundary summary, not a full
SBOM for every environment a user may install.

## Python/runtime dependencies

The application uses third-party Python packages including Flask/Werkzeug/Jinja2,
Requests, Pillow, PyTorch/torchvision, Hugging Face libraries, cryptography and
psutil. Their exact licenses and notices are determined by the versions installed
in the user environment.

Some optional dependencies have LGPL, MPL, MIT, BSD-family or other terms. When
redistributing a prebuilt environment, review the licenses and notices of the
actual resolved packages and bundled native libraries.

## Models

Model weights are not covered by the application’s Apache-2.0 license. Examples
include SDXL checkpoints, LoRAs, InstantID weights, InsightFace pretrained
models, Face Swap models and Vision models. Always review the terms of the exact
model you download or link.

The ability to select a model file in the interface does not grant additional
rights to use, redistribute or commercialize that model.

## External binaries

FFmpeg licensing depends on the specific build and enabled components. No FFmpeg
binary is included in this source distribution.

The optional managed llama.cpp runtime is downloaded separately from its upstream
project when explicitly requested. llama.cpp and any libraries included in an
upstream binary archive retain their own licenses and notices.

## References

- Apache-2.0: https://www.apache.org/licenses/LICENSE-2.0
- SDXL Base: https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0
- InstantID: https://github.com/instantX-research/InstantID
- InsightFace: https://github.com/deepinsight/insightface
- llama.cpp: https://github.com/ggml-org/llama.cpp
- FFmpeg legal information: https://ffmpeg.org/legal.html

See also docs/ATTRIBUTION_AND_LICENSES.md and docs/MODELS_AND_LICENSES.md.
