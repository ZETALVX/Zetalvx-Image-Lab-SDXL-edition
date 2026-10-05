# Testing the Source distribution

The repository includes read-only structure/syntax checks and unit/regression tests.

## Structure and syntax

```bash
python tools/check_source.py --javascript
```

This checks Python syntax, JSON parsing, JavaScript syntax (when Node.js is available) and the file manifest. It does not validate GPU inference.

## Source-boundary tests

```bash
python -B -m unittest tests.test_source_distribution -v
```

## Additional tests

Other modules under `tests/` cover application behavior. Some require optional dependencies, Windows, a browser, a configured runtime or model files. A skipped hardware/platform test is not equivalent to a pass.

For real acceptance testing, install the Source build on the target operating system and verify representative image, training, Identity and Vision workflows with the intended hardware and models.
