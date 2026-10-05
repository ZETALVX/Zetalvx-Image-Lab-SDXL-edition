# Contributing

Contributions, bug reports and technical feedback are welcome.

## Before submitting changes

- Keep changes focused and explain the affected behavior.
- Use the isolated Source data home; do not test against a packaged installation home.
- Do not commit model weights, datasets, generated user media, credentials, tokens, certificates, runtime environments or local logs.
- Do not weaken security checks, version checks or dependency safety gates just to make a test pass.
- Preserve third-party license and attribution requirements.

## Testing

Run the source structure checks:

```bash
python tools/check_source.py --javascript
python -B -m unittest tests.test_source_distribution -v
```

Additional workflow-specific tests can be run from `tests/` as needed. GPU/model tests require the corresponding local runtime and model files.

## Bug reports

Include, where relevant:

- operating system;
- Python version;
- GPU and driver information;
- affected workflow;
- exact error;
- reproducible steps;
- a sanitized log excerpt.

Never include passwords, API keys, access tokens, cookies, private keys or private model credentials.

See LICENSE, NOTICE and THIRD_PARTY_NOTICES.md for licensing information.
