# Manual Linux setup — public source

**Zetalvx Image Lab — SDXL Edition · Zetalvx Labs.**

This guide is for the source checkout, **not** the packaged installer. Run commands from the extracted repository root containing `source.py`. Use a normal user and an already available **64-bit Python 3.11 with venv support**. Installing system prerequisites is outside this source package; do not use `sudo pip` or the data home of the packaged app.

Commands below use the dependency pins shipped with this repository. They do not silently downgrade packages or install drivers. Network access to the configured official package indexes is required. The full resolved environments and GPU behavior still need validation on the target machine.

## 1. Application environment / web-only check

This block creates only the source app venv and application data. It installs no model weights and no Torch. A failed command stops the block without closing the parent terminal.

```bash
(
  set -euo pipefail
  test -f source.py || { echo 'Run this from the extracted source root.'; exit 1; }
  python3.11 -c 'import sys; assert sys.version_info[:2] == (3,11) and sys.maxsize > 2**32'
  data="$(python3.11 source.py home)"
  app="$data/runtime/app/bin/python"
  if [ ! -x "$app" ]; then python3.11 -m venv "$data/runtime/app"; fi
  "$app" -m pip --isolated install --only-binary=:all: --index-url https://pypi.org/simple -r requirements-tools.txt
  "$app" -m pip --isolated install --only-binary=:all: --index-url https://pypi.org/simple -r requirements-app.txt
  "$app" -m pip check
  "$app" source.py init
  "$app" source.py start --local --no-browser
  "$app" source.py status
)
```

Open `https://127.0.0.1:8298` on the host. A self-signed certificate warning is expected; verify you are connecting to your own host. Create the first account. For remote/headless setup, see **LAN** below. No default password is supplied.

The app is running but AI workers are not available yet. Stop it before preparing the AI environment:

```bash
(
  set -euo pipefail
  data="$(python3.11 source.py home)"
  "$data/runtime/app/bin/python" source.py stop
)
```

## 2. AI environment (SDXL + Identity libraries)

The default below reproduces the packages' **`cu126` NVIDIA backend**. Set `backend=cpu` instead before running the block for the documented CPU route; CPU execution is not a performance recommendation. No AMD/ROCm or macOS setup is claimed here. NVIDIA users need a functioning driver already on the host; the source setup does not install CUDA toolkits or drivers globally.

```bash
(
  set -euo pipefail
  backend=cu126
  test -f source.py || { echo 'Run this from the extracted source root.'; exit 1; }
  data="$(python3.11 source.py home)"
  ai="$data/runtime/sdxl/bin/python"
  if [ ! -x "$ai" ]; then python3.11 -m venv "$data/runtime/sdxl"; fi
  "$ai" -m pip --isolated install --only-binary=:all: --index-url https://pypi.org/simple -r requirements-tools.txt
  "$ai" -m pip --isolated install --only-binary=:all: --index-url "https://download.pytorch.org/whl/$backend" torch==2.14.0 torchvision==0.29.0
  "$ai" -c 'import sys,torch; from core.runtime_security import require_reviewed_torch; require_reviewed_torch(); assert sys.argv[1]=="cpu" or torch.cuda.is_available(), "CUDA selected but unavailable"; print(torch.__version__, "CUDA:",torch.cuda.is_available())' "$backend"
  "$ai" -m pip --isolated install --only-binary=:all: --index-url https://pypi.org/simple -r requirements-sdxl.txt
  "$ai" -m pip --isolated install --only-binary=:all: --index-url https://pypi.org/simple -r requirements-identity-base.txt
  "$ai" -m pip --isolated install --only-binary=:all: --no-deps --index-url https://pypi.org/simple insightface==1.0.1
  ort=onnxruntime-gpu
  if [ "$backend" = cpu ]; then ort=onnxruntime; fi
  "$ai" -m pip --isolated install --only-binary=:all: --index-url https://pypi.org/simple "$ort==1.20.2"
  "$ai" tools/check_runtime.py --backend "$backend"
  "$data/runtime/app/bin/python" source.py doctor
)
```

`requirements-identity-base.txt` is only an exact split of the non-InsightFace lines from the unchanged `requirements-identity.txt`. Installing InsightFace with `--no-deps` preserves the supplied installer choice of **headless OpenCV and one backend-specific ONNX Runtime**. It does not download Identity weights.

`pip check` in this AI environment can report the known InsightFace distribution-name aliases (`opencv-python` versus `opencv-python-headless`, and `onnxruntime` versus `onnxruntime-gpu`). Do not blindly install both variants to silence those messages. Inspect any other conflict as a real problem. The tiny runtime check validates imports and selected providers; it does not prove generation or training correctness.

If pip cannot resolve the exact pins, or the smoke check fails, stop and keep the output. Do not weaken `core/runtime_security.py`, change package pins or use the packaged app's environment to make this source test pass.

The `cpu` package backend does not automatically change the application's saved model settings. The supplied model defaults still select CUDA / float16. For CPU use, explicitly select CPU and a compatible precision in the model configuration; no CPU performance or end-to-end acceptance result is claimed here.

## 3. Models and start

The UI can link existing model files. Standard source model folders are `models/SDXL`, `models/loras/SDXL` and `models/Identity`, under the source data home. Model/tokenizer configurations can be prepared without SDXL weight download:

```bash
(
  set -euo pipefail
  data="$(python3.11 source.py home)"
  "$data/runtime/app/bin/python" source.py download-configs
  "$data/runtime/app/bin/python" source.py start --local
)
```

After reading and accepting the model's own license, an **explicit** optional SDXL Base download is:

```bash
(
  set -euo pipefail
  data="$(python3.11 source.py home)"
  "$data/runtime/app/bin/python" source.py download-base --accept-license
)
```

`source.py identity-code` prepares the existing revision-pinned InstantID **code-only** integration. Identity/face weights are supplied separately and retain their own terms. Do not interpret code availability as a weight license.

## LAN / remote first setup

```bash
(
  set -euo pipefail
  data="$(python3.11 source.py home)"
  app="$data/runtime/app/bin/python"
  "$app" source.py stop
  "$app" source.py network lan
  "$app" source.py start --no-browser
  "$app" source.py setup-code
)
```

Use the host's displayed HTTPS LAN address from the phone/other computer. The host-issued setup code is for **initial account creation**, not the normal password. `setup-code` rotates it while setup is incomplete; it does not reset an existing account. Only expose the UI port to a trusted LAN; do not forward worker ports or publish this server directly to the Internet. The source command does not edit Linux firewall rules.

For normal management use the same interpreter with `source.py stop`, `status`, `doctor`, or `network local`. Logs: `<source-home>/shared/logs`. [More operation details](SOURCE_OPERATION.md).

The direct venv interpreter paths intentionally avoid activation. Python documents this supported approach: https://docs.python.org/3.11/library/venv.html . The paths, commands and dependency pins above are the ones documented for this repository.
