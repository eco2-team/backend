#!/usr/bin/env bash
set -euo pipefail

python3 <<'PY'
import pathlib
import re
import sys

pattern = re.compile(r'"{{[^"]+}}"')
errors = []

for path in pathlib.Path(".").rglob("*.yaml"):
    if any(part.startswith(".git") or part == "worktrees" for part in path.parts):
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

python3 <<'PY'
import pathlib
import sys

# APIs + Workers ApplicationSets (each env can have multiple)
APPSETS = {
    "dev": [
        pathlib.Path("clusters/dev/apps/40-apis-appset.yaml"),
        pathlib.Path("clusters/dev/apps/41-workers-appset.yaml"),
    ],
    "prod": [
        pathlib.Path("clusters/prod/apps/60-apis-appset.yaml"),
        pathlib.Path("clusters/prod/apps/61-workers-appset.yaml"),
    ],
}

# 별도 Application으로 관리되는 서비스 (ApplicationSet 제외)
EXCLUDED_SERVICES = {
    "event-router",  # clusters/*/apps/43-event-router.yaml
    "sse-gateway",   # clusters/*/apps/42-sse-gateway.yaml
}

services = sorted(
    p.name
    for p in pathlib.Path("workloads/domains").iterdir()
    if p.is_dir() and p.name not in EXCLUDED_SERVICES
)

def parse_elements(path: pathlib.Path):
    names = []
    phases = {}
    inside = False
    current = None
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not inside:
            if stripped.startswith("elements:"):
                inside = True
            continue
        if stripped.startswith("template:"):
            break
        if stripped.startswith("- name:"):
            current = stripped.split(":", 1)[1].strip()
            names.append(current)
            continue
        if stripped.startswith("phase:") and current:
            phases[current] = stripped.split(":", 1)[1].strip().strip('"')
            continue
    return names, phases

errors = []
env_maps = {}

for env, paths in APPSETS.items():
    all_names = []
    all_phases = {}
    for path in paths:
        if not path.exists():
            # Workers appset is optional for backward compat
            if "workers" in str(path):
                continue
            errors.append(f"{env}: missing {path}")
            continue
        names, phases = parse_elements(path)
        all_names.extend(names)
        all_phases.update(phases)
    env_maps[env] = sorted(all_names)
    missing = sorted(set(services) - set(all_names))
    extra = sorted(set(all_names) - set(services))
    if missing:
        errors.append(f"{env}: services missing from ApplicationSet list → {', '.join(missing)}")
    if extra:
        errors.append(f"{env}: ApplicationSet lists unknown services → {', '.join(extra)}")
    orphan_phase = sorted(set(all_names) - set(all_phases))
    if orphan_phase:
        errors.append(f"{env}: services missing phase label → {', '.join(orphan_phase)}")

if len(env_maps) == len(APPSETS):
    if env_maps["dev"] != env_maps["prod"]:
        errors.append("dev/prod ApplicationSet service lists diverged")

if errors:
    print("❌ ApplicationSet service list validation failed:")
    for err in errors:
        print(f"- {err}")
    sys.exit(1)

print("✅ ApplicationSet service lists match workloads/domains/* directories.")
PY

python3 <<'PY'
import pathlib
import sys

errors = []
root = pathlib.Path("platform/helm")

for env in ("dev", "prod"):
    for patch in sorted(root.glob(f"*/{env}/patch-application.yaml")):
        content = patch.read_text().splitlines()
        project_value = None
        for line in content:
            stripped = line.strip()
            if stripped.startswith("project:"):
                project_value = stripped.split(":", 1)[1].strip().strip('"')
                break
        if project_value is None:
            errors.append(f"{patch}: missing spec.project")
            continue
        if project_value != env:
            errors.append(f"{patch}: spec.project='{project_value}' (expected '{env}')")

if errors:
    print("❌ Argo Application patches failed project validation:")
    for err in errors:
        print(f"- {err}")
    sys.exit(1)

print("✅ Argo Application patch files set spec.project per environment.")
PY
