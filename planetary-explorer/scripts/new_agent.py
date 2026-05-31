"""Scaffold a new MAF agent from the simple_qa template.

Usage:
    python scripts/new_agent.py NAME [--template simple_qa]

Copies ``container-app/agents/_templates/<template>/`` to
``container-app/agents/<name>/`` and rewrites class names + imports so
the new agent is importable and runnable out of the box.

Idempotency: refuses to overwrite an existing ``container-app/agents/<name>/``
directory.
"""
from __future__ import annotations

import argparse
import re
import shutil
import sys
from pathlib import Path


def to_camel(snake: str) -> str:
    return "".join(p.capitalize() for p in snake.split("_"))


def rewrite_text(text: str, src_name: str, dst_name: str) -> str:
    src_camel = to_camel(src_name)
    dst_camel = to_camel(dst_name)
    text = text.replace(src_camel + "Agent", dst_camel + "Agent")
    text = text.replace(src_camel, dst_camel)
    text = re.sub(rf"\b{re.escape(src_name)}\b", dst_name, text)
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("name", help="snake_case name of the new agent")
    parser.add_argument(
        "--template",
        default="simple_qa",
        help="template directory under container-app/agents/_templates/",
    )
    args = parser.parse_args()

    name: str = args.name
    if not re.fullmatch(r"[a-z][a-z0-9_]*", name):
        print(f"agent name must be snake_case (got {name!r})", file=sys.stderr)
        return 2

    repo_root = Path(__file__).resolve().parents[1]
    src = repo_root / "container-app" / "agents" / "_templates" / args.template
    dst = repo_root / "container-app" / "agents" / name
    if not src.exists():
        print(f"template not found: {src}", file=sys.stderr)
        return 2
    if dst.exists():
        print(f"refusing to overwrite existing {dst}", file=sys.stderr)
        return 2

    shutil.copytree(src, dst)
    for path in dst.rglob("*"):
        if path.is_file() and path.suffix in {".py", ".md"}:
            text = path.read_text(encoding="utf-8")
            new_text = rewrite_text(text, args.template, name)
            if new_text != text:
                path.write_text(new_text, encoding="utf-8")

    print(f"created {dst.relative_to(repo_root)}")
    print(f"  class: {to_camel(name)}Agent")
    print(f"  import: from agents.{name} import {to_camel(name)}Agent")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
