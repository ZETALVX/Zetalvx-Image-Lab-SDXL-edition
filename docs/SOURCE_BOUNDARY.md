# Source distribution boundary

This repository is the manual Source distribution of **Zetalvx Image Lab — SDXL Edition**.

It contains application code, configuration templates, documentation and tests. It does not contain:

- AI model weights;
- user datasets or generated media;
- credentials or account data;
- prebuilt Python environments;
- FFmpeg binaries;
- NVIDIA drivers or a global CUDA toolkit;
- the packaged Linux/Windows application installer.

The Source edition uses a separate default data directory (`CreatorStudioSDXL-Source`) so it does not overwrite a packaged installation. `SOURCE_RELEASE.json` is a small source marker used by lifecycle guards to distinguish this checkout from an installed package.

The manual Source setup creates its own Python environments under the Source data home. Models can be linked from external locations; linked model ownership and licensing remain independent of the application.

Packaged update, rollback, desktop integration and managed uninstall workflows are intentionally separate from the Source checkout.
