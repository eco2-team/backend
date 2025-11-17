#!/usr/bin/env bash
set -euo pipefail

python3 <<'PY'
import pathlib
import re
import sys

pattern = re.compile(r'"{{[^"]+}}"')
errors = []

for path in pathlib.Path(".").rglob("*.yaml"):
    if any(part.startswith(".git") for part in path.parts):
        continue
    try:
        data = path.read_text()
    except UnicodeDecodeError:
        continue
    if "kind: ApplicationSet" not in data:
        continue
    for match in pattern.finditer(data):
        line = data.count("\n", 0, match.start()) + 1
        snippet = match.group(0)
        errors.append((path.as_posix(), line, snippet))

if errors:
    print("❌ Found literal quotes around templating tokens in ApplicationSet definitions:")
    for path, line, snippet in errors:
        print(f"- {path}:{line} → {snippet}")
    sys.exit(1)

print("✅ ApplicationSet templates: no literal quotes detected.")
PY

