# Locked toolchain evidence

- Source revision: `da061911a7956892adbf8b5a1414e7407ce05b2a`
- Execution time: 2026-08-04T10:10Z
- Host: x86_64 WSL2 development environment
- Python: 3.13.14
- uv: 0.12.1
- Reviewer: Pending owner review

The raw output in [toolchain-bootstrap.log](toolchain-bootstrap.log) was produced by:

```sh
./scripts/development/bootstrap.sh
```

The script validates the exact uv version, installs the `.python-version` interpreter if needed,
and runs `uv sync --frozen`. This run found the interpreter installed and all 67 locked packages
already synchronized.
