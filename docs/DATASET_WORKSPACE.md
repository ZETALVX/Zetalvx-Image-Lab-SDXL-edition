# Dataset Studio inside the SDXL Training host

This release keeps the public standalone Dataset Studio 0.1.2 unchanged. It does not
mount an iframe, use its HTTP server or read its credentials. Existing Creator Vision
profiles remain in the same store, implemented by the unchanged `vision` package.

## Shared code, not a second dataset database

`core/dataset_exchange.py` is byte-identical to standalone `datasets.py`. Both schema,
ZIP interoperability, image constraints and manual trigger operations are reused.
`vision/batch.py`, registry, engines, profile UI and caption merge rules remain unchanged.

The host adapter `core/dataset_workspace.py` exposes validated operations on the
existing `shared/training/datasets` directory. `core/dataset_workspace_api.py` attaches
this adapter to the authenticated Creator. Creation, manual edits, import/export,
image upload, deletion and caption completion all share the caption engine's RLock.
Each JSON write is atomic. Training submission holds that lock through preflight and
job registration; changes are blocked while a dataset has an active training job.

## Request and editing contracts

- Mutations under `/api/training/datasets` use the existing Vision CSRF scope. GETs
  continue to require the Creator login. Multipart requests preserve their content type.
- PUT accepts `expected` metadata and `expected_captions` for optimistic concurrency.
  A 409 `dataset_conflict` preserves the client draft and supplies the current record.
- Image batches validate names, exact UTF-8 caption pairs, limits and safe images before
  publishing. File staging is cleaned on failure. Identical image bytes are skipped.
- `/use` runs preflight and returns the current manifest/report. It neither submits a
  GPU job nor copies the dataset. `/api/training/jobs` uses its existing `dataset_id`.
- Captioning preserves manually edited text and dataset options changed during inference.
  Structural changes are blocked while captioning that dataset. API/native training
  handoff waits for pending captioning. Existing native GPU lock is retained.

## UI contract

Training is separated into Dataset / Train SDXL / Results. One selected image/caption
editor, twelve thumbnails per page and per-dataset Vision selection replace the old
all-caption-input list. The active dataset, image and training section are retained
in the browser session. Background updates skip focused or dirty fields, and rendered
thumbnails change only when their state does. Existing custom training parameters are
not reset on each visit.

Image-source originals, captions, model names, paths and trigger strings are never
translated by interface language changes. Display dimensions are contain-only.
Model installation/configuration remains in Models → Vision/Caption (Transformers,
GGUF or API). No new model loader or diffusion backend was introduced by this change.

## Limitations

No cross-app account synchronization or shared GPU scheduler with the standalone.
No promise of exact training resumption after editing an old completed dataset. Review
and retain a copy of your dataset for reproducibility. Thumbnail routes require the
app login; large datasets remain paginated in the UI but the JSON report is full-size.
No automatic continuation of an interrupted caption request after server restart.
