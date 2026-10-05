"""Shared read-only activity inventory for update, restart and uninstall (0.1.0.42)."""
import contextlib, json, sqlite3
from pathlib import Path
BUSY = {'running','queued','cancelling','preparing','loading_model','downloading','validating','verifying','installing'}

def busy_jobs(home):
    home = Path(home)
    """Read-only check. Fail closed on corrupt known state rather than kill a job."""
    result = []
    db = home/'shared/data/sdxl_studio.sqlite3'
    if db.is_file():
        with contextlib.closing(sqlite3.connect(db.resolve().as_uri()+'?mode=ro', uri=True, timeout=3)) as con:
            tables = {r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table'")}
            if 'jobs' in tables:
                result.extend('image:'+str(row[0]) for row in con.execute(
                    "SELECT id FROM jobs WHERE status IN ('running','queued','cancelling')"))
    for pattern in ('shared/training/jobs/*/progress.json', 'shared/identity/jobs/*/progress.json',
                    'jobs/vision-actions/*.json', 'shared/downloads/model-hub/*.json',
                    'shared/config/instantid_code_install.json', 'shared/vision/link-imports/*.json',
                    'shared/config/sdxl_base_install.json'):
        for path in home.glob(pattern):
            d = json.loads(path.read_text(encoding='utf-8'))
            if not isinstance(d,dict):raise ValueError('Invalid job state: '+str(path.relative_to(home)))
            if d.get('status') in BUSY: result.append(str(path.relative_to(home)))
    return result

