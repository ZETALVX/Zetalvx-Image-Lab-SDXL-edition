# Operating the source checkout

## Entry point and isolation

Use the app venv prepared in the OS guide and `source.py`, always from the repository root. `source.py home` prints the data directory without creating it. Its default is the packaged product's base name plus **`-Source`**, outside the checkout. A deliberately chosen `SDXL_STUDIO_HOME` is respected only when it is not the standard packaged home, a recognized installed home, the checkout, an ancestor or a child of the checkout.

Keep the same absolute data path between sessions. Do not move created venvs to a new directory; recreate them there instead. Keep another Zetalvx Image Lab instance stopped while using the default ports 8298–8301. Model files may be linked from elsewhere; that does not give multiple workers coordinated use of all external applications' GPU memory.

## Commands

`source.py init` initializes configuration/account setup and creates or reuses the existing self-signed certificate. `start --local` starts the normal browser workflow. `start --no-browser` is suitable for a CLI host. `network lan` / `network local` save the access mode for the next start; stop first when changing access mode. `status` and `doctor` display source paths and component information.

`stop` uses the existing owned-process lifecycle logic, not a global kill of every `python.exe`. GUI stop/restart uses the source-path adapter. Stop after completing or cancelling active work.

`setup-code` creates/rotates the temporary **first-account** code while initial setup is incomplete. Once an account exists, it is not a password-reset mechanism. The existing `password` command resets credentials to username **`C`**, requests a new password interactively and revokes sessions; use it deliberately from the host rather than expecting it to preserve another username.

## Logs

Logs remain under `<source-home>/shared/logs`, including `launcher.log`, `web-worker.log`, `image-worker.log`, `training-worker.log` and `identity-worker.log`. GUI lifecycle messages go to `app-control.log`. No disappearance of a browser page is proof that removal succeeded. Application logs may include user data; redact before posting an issue. Never publish `secrets`, worker keys, auth files, cookies, certificates' private keys or resolved private environment inventories.

## Manual source update

Finish/cancel work and run `source.py stop` from the old checkout. Confirm stopped status. Retain a backup of user data that matters. Download a new source checkout or update the repository deliberately; review the updated documentation and any required dependency changes. Keep the same **source** data home, not the packaged installation home. Re-run dependency preparation only when required; do not overwrite existing venvs with a packaged installer. Start the new checkout with `source.py`.

A `git` checkout change does not roll back data/schema changes or model files. No automatic rollback guarantee is made for source updates.

## Manual source removal

Stop this source instance and confirm no owned service remains. Close terminals whose current directory is the directory to be removed. Remove the checkout manually when no longer needed. Remove the separate source data home only after deciding whether to keep its models, datasets, images, projects, settings and account. Linked external model directories are separate data and should not be recursively removed as part of this process.

The source entry point installs no app registry item, global PATH command or desktop launcher. This is deliberately different from the two packaged installers, whose uninstall workflows remain separate and unchanged.
