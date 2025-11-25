#!/usr/bin/env python3
"""Update the image tag inside a Kustomize kustomization.yaml file.

The script looks for the `images` entry whose `name` matches the provided
image name and updates its `newTag` value. If the entry does not exist,
it is appended. The script preserves key order for readability.
"""

from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

import yaml


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Update Kustomize image tag")
    parser.add_argument("--file", required=True, help="Path to kustomization.yaml")
    parser.add_argument("--image", required=True, help="Image name to update")
    parser.add_argument("--tag", required=True, help="New tag value")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    path = Path(args.file)
    if not path.exists():
        raise SystemExit(f"File not found: {path}")

    with path.open("r", encoding="utf-8") as fp:
        data: dict[str, Any] = yaml.safe_load(fp) or {}

    images: list[dict[str, Any]] = data.setdefault("images", [])

    # Look for existing entry
    target = None
    for item in images:
        if item.get("name") == args.image:
            target = item
            break

    if target is None:
        target = {"name": args.image}
        images.append(target)

    target["newTag"] = args.tag

    with path.open("w", encoding="utf-8") as fp:
        yaml.safe_dump(data, fp, sort_keys=False)


if __name__ == "__main__":
    main()
