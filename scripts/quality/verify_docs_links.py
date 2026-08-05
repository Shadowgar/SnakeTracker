#!/usr/bin/env python3
"""Check that Markdown links to repository-local targets resolve."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).parents[2]
MARKDOWN_LINK = re.compile(r"!?(?:\[[^\]]*\])\(([^)]+)\)")


def local_target(raw_target: str) -> str | None:
    target = raw_target.strip()
    if target.startswith("<") and ">" in target:
        target = target[1 : target.index(">")]
    else:
        target = target.split(maxsplit=1)[0]
    parsed = urlsplit(target)
    if parsed.scheme or parsed.netloc or not parsed.path:
        return None
    return unquote(parsed.path)


def main() -> int:
    failures: list[str] = []
    markdown_files = sorted(ROOT.glob("*.md")) + sorted((ROOT / "docs").rglob("*.md"))
    for source in markdown_files:
        content = source.read_text(encoding="utf-8")
        for match in MARKDOWN_LINK.finditer(content):
            target = local_target(match.group(1))
            if target is None:
                continue
            candidate = (
                ROOT / target.lstrip("/") if target.startswith("/") else source.parent / target
            )
            if not candidate.resolve(strict=False).exists():
                failures.append(f"{source.relative_to(ROOT)} -> {match.group(1)}")
    if failures:
        print("broken local documentation links:\n" + "\n".join(failures), file=sys.stderr)
        return 1
    print(f"documentation links passed: {len(markdown_files)} files checked")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
