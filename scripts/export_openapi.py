"""Xuất đặc tả OpenAPI ra openapi.yaml (và openapi.json) để commit vào repo."""

from __future__ import annotations

import json
import pathlib
import sys

import yaml

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from app.main import create_app  # noqa: E402


def main() -> None:
    spec = create_app().openapi()
    root = pathlib.Path(__file__).resolve().parents[1]

    (root / "openapi.yaml").write_text(
        yaml.safe_dump(spec, sort_keys=False, allow_unicode=True), encoding="utf-8"
    )
    (root / "openapi.json").write_text(
        json.dumps(spec, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    paths = spec["paths"]
    ops = sum(
        1 for methods in paths.values() for m in methods if m in {"get", "post", "put", "delete"}
    )
    print(f"openapi.yaml / openapi.json: {len(paths)} paths, {ops} operations")


if __name__ == "__main__":
    main()
