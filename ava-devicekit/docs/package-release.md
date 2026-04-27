# Package Release

`pyproject.toml` defines the package metadata and the `ava-devicekit` CLI entry point.

Local package check:

```bash
cd ava-devicekit
python3 -m pip install -e .[dev]
ava-devicekit capabilities
ava-devicekit validate --config userland/runtime.example.json
```

Versioning should treat framework contracts as semver-sensitive:

| Change | Version Impact |
|---|---|
| Add provider/adapter implementation | Patch or minor |
| Add optional screen payload fields | Minor |
| Remove or rename schema fields | Major |
| Change firmware wire protocol | Major unless protected by compatibility shim |
