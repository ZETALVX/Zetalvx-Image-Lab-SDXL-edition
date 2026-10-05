# Manual Windows setup — PowerShell

**Zetalvx Image Lab — SDXL Edition · Zetalvx Labs.**

This guide is for the **public source**, not `INSTALL.cmd`. Extract the repository to a normal writable folder outside the packaged app's installation, open **PowerShell as your normal user**, and change to the folder containing `source.py`.

Use an already installed **64-bit Python 3.11** with the `py -3.11` launcher available. When Python is installed without `py`, replace only the `py` executable / `-3.11` selection with the explicit path to that Python. Do not use the packaged Zetalvx Image Lab interpreter or its data home. The source package does not install Python, a driver or a global CUDA toolkit.

The blocks invoke the venv's `python.exe` directly. There is no `Activate.ps1`, global `Set-ExecutionPolicy`, admin batch installer or disappearing batch window. Native command exit codes are checked explicitly, including in Windows PowerShell 5.1.

## 1. Application environment / web-only check

Run this block from the source root:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    function Invoke-Checked([string]$Program, [string[]]$Arguments) {
        & $Program @Arguments
        if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $Program $Arguments" }
    }
    if (-not (Test-Path -LiteralPath '.\source.py')) { throw 'Open PowerShell in the extracted source root.' }
    Invoke-Checked 'py' @('-3.11','-c','import sys; assert sys.version_info[:2] == (3,11) and sys.maxsize > 2**32')
    $data = (& py -3.11 source.py home | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $data) { throw 'Could not resolve the isolated source data home.' }
    $appEnv = Join-Path $data 'runtime\app'
    $app = Join-Path $appEnv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $app)) { Invoke-Checked 'py' @('-3.11','-m','venv',$appEnv) }
    Invoke-Checked $app @('-m','pip','--isolated','install','--only-binary=:all:','--index-url','https://pypi.org/simple','-r','requirements-tools.txt')
    Invoke-Checked $app @('-m','pip','--isolated','install','--only-binary=:all:','--index-url','https://pypi.org/simple','-r','requirements-app.txt')
    Invoke-Checked $app @('-m','pip','check')
    Invoke-Checked $app @('source.py','init')
    Invoke-Checked $app @('source.py','start','--local','--no-browser')
    Invoke-Checked $app @('source.py','status')
}
```

Default data home: `%LOCALAPPDATA%\CreatorStudioSDXL-Source`. Open `https://127.0.0.1:8298`, verify it is your host, accept the expected local self-signed certificate warning and create the first account. There is no default password. This verifies web setup, **not** AI generation.

Before preparing AI, stop this source instance:

```powershell
& {
    $data = (& py -3.11 source.py home | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $data) { throw 'Source home unavailable.' }
    & (Join-Path $data 'runtime\app\Scripts\python.exe') source.py stop
    if ($LASTEXITCODE -ne 0) { throw 'Stop failed; read the output above.' }
}
```

## 2. AI environment (SDXL + Identity libraries)

`$backend = 'cu126'` preserves the supplied NVIDIA package selection. Use `'cpu'` instead for the CPU route; CPU operation is not a speed recommendation. A functioning NVIDIA driver must already exist for CUDA. No other GPU backend is claimed by this guide.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $backend = 'cu126'
    function Invoke-Checked([string]$Program, [string[]]$Arguments) {
        & $Program @Arguments
        if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $Program $Arguments" }
    }
    if (-not (Test-Path -LiteralPath '.\source.py')) { throw 'Open PowerShell in the extracted source root.' }
    $data = (& py -3.11 source.py home | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $data) { throw 'Could not resolve the isolated source data home.' }
    $aiEnv = Join-Path $data 'runtime\sdxl'
    $ai = Join-Path $aiEnv 'Scripts\python.exe'
    if (-not (Test-Path -LiteralPath $ai)) { Invoke-Checked 'py' @('-3.11','-m','venv',$aiEnv) }
    Invoke-Checked $ai @('-m','pip','--isolated','install','--only-binary=:all:','--index-url','https://pypi.org/simple','-r','requirements-tools.txt')
    Invoke-Checked $ai @('-m','pip','--isolated','install','--only-binary=:all:','--index-url',"https://download.pytorch.org/whl/$backend",'torch==2.14.0','torchvision==0.29.0')
    Invoke-Checked $ai @('-c',"import sys,torch; from core.runtime_security import require_reviewed_torch; require_reviewed_torch(); assert sys.argv[1]=='cpu' or torch.cuda.is_available(), 'CUDA selected but unavailable'; print(torch.__version__, 'CUDA:',torch.cuda.is_available())",$backend)
    Invoke-Checked $ai @('-m','pip','--isolated','install','--only-binary=:all:','--index-url','https://pypi.org/simple','-r','requirements-sdxl.txt')
    Invoke-Checked $ai @('-m','pip','--isolated','install','--only-binary=:all:','--index-url','https://pypi.org/simple','-r','requirements-identity-base.txt')
    Invoke-Checked $ai @('-m','pip','--isolated','install','--only-binary=:all:','--no-deps','--index-url','https://pypi.org/simple','insightface==1.0.1')
    $ort = if ($backend -eq 'cu126') { 'onnxruntime-gpu==1.20.2' } else { 'onnxruntime==1.20.2' }
    Invoke-Checked $ai @('-m','pip','--isolated','install','--only-binary=:all:','--index-url','https://pypi.org/simple',$ort)
    Invoke-Checked $ai @('tools/check_runtime.py','--backend',$backend)
    Invoke-Checked (Join-Path $data 'runtime\app\Scripts\python.exe') @('source.py','doctor')
}
```

This copies the existing dependency-selection policy, including headless OpenCV, InsightFace without its default dependency bundle, and one selected ONNX Runtime. It downloads **libraries, not Identity/face model weights**. `requirements-identity-base.txt` is the exact non-InsightFace subset of the original requirement file.

This Source setup intentionally uses `opencv-python-headless` / `onnxruntime-gpu` for the corresponding InsightFace requirements. `pip check` may report those aliases; do not install both backends to silence them. Other conflicts or missing imports require investigation. The tiny smoke checker uses the application's isolated CUDA library-path helper; it does not edit system PATH or load model weights.

If exact packages cannot be resolved or CUDA/provider checks fail, stop and preserve the output. Do not downgrade pins or weaken the existing Torch gate. A successful source-web check alone does not validate the AI environment.

The `cpu` package backend does not automatically change the application's saved model settings. The supplied model defaults still select CUDA / float16. For CPU use, explicitly select CPU and a compatible precision in the model configuration; no CPU performance or end-to-end acceptance result is claimed here.

## 3. Models and normal start

Link existing model files in the GUI, or explicitly prepare the tokenizer/model configurations:

```powershell
& {
    $data = (& py -3.11 source.py home | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $data) { throw 'Source home unavailable.' }
    $app = Join-Path $data 'runtime\app\Scripts\python.exe'
    & $app source.py download-configs
    if ($LASTEXITCODE -ne 0) { throw 'Configuration download failed.' }
    & $app source.py start --local
    if ($LASTEXITCODE -ne 0) { throw 'Startup failed; read source shared\logs.' }
}
```

After reading and accepting the model license, `source.py download-base --accept-license` explicitly downloads SDXL Base. `source.py identity-code` prepares only the existing revision-pinned InstantID code integration. Neither the app license nor a file-selection checkbox grants extra rights to supplied weights/media. See [model notices](MODELS_AND_LICENSES.md).

## LAN / remote first setup

```powershell
& {
    $ErrorActionPreference = 'Stop'
    function Invoke-Checked([string]$Program, [string[]]$Arguments) {
        & $Program @Arguments
        if ($LASTEXITCODE -ne 0) { throw "Command failed (exit $LASTEXITCODE): $Program $Arguments" }
    }
    $data = (& py -3.11 source.py home | Out-String).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $data) { throw 'Source home unavailable.' }
    $app = Join-Path $data 'runtime\app\Scripts\python.exe'
    Invoke-Checked $app @('source.py','stop')
    Invoke-Checked $app @('source.py','network','lan')
    Invoke-Checked $app @('source.py','start','--no-browser')
    Invoke-Checked $app @('source.py','setup-code')
}
```

Connect to the displayed HTTPS host LAN address from the other device. The temporary setup code is for initial account creation; it is not the login password and it does not reset an already configured account. Windows Firewall may require a separate, explicit host authorization for trusted-LAN inbound access. Do not run the whole application as another administrator user to bypass a firewall prompt, and do not expose worker ports or forward the app directly to the Internet.

Use the same app interpreter and `source.py stop`, `status`, `doctor`, `network local` for management. The existing `password` command resets the account to username **`C`**; read [source operation](SOURCE_OPERATION.md) before using it.

Python documents direct venv interpreter use without activation: https://docs.python.org/3.11/library/venv.html . Paths, pins and app arguments in this guide are defined by this repository. Verify the setup on the target Windows system and hardware.
