# Package Release

`pyproject.toml` defines the package metadata and the `ava-devicekit` CLI entry point.

Local package check:

```bash
cd ava-devicekit
python3 -m pip install -e .[dev]
ava-devicekit capabilities
ava-devicekit validate --config userland/runtime.example.json
python3 -m pytest -q tests tests/conformance
python3 -m build
```

Versioning should treat framework contracts as semver-sensitive:

| Change | Version Impact |
|---|---|
| Add provider/adapter implementation | Patch or minor |
| Add optional screen payload fields | Minor |
| Remove or rename schema fields | Major |
| Change firmware wire protocol | Major unless protected by compatibility shim |

## Release Checklist

| Step | Command / Check |
|---|---|
| Run Python tests | `python3 -m pytest -q tests tests/conformance` |
| Validate runtime example | `ava-devicekit validate --config userland/runtime.example.json` |
| Check generators | `ava-devicekit init-app /tmp/dk-app --type payment --force`; `ava-devicekit init-board /tmp/dk-board --force` |
| Build package | `python3 -m build` |
| Smoke CLI | `ava-devicekit capabilities`; `ava-devicekit firmware list --config userland/runtime.example.json` |
| Tag | Use semver; bump major for incompatible schema/protocol changes |
