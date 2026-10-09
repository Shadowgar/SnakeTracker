#!/usr/bin/env python3
"""Validate ADR governance across committed, staged and local documentation."""

from __future__ import annotations

import hashlib
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

ROOT = Path(__file__).parents[2]
BASELINE_COMMIT = "bb3ab394a1487943424dad6d7544995c71156c98"
# Inherit the old gate's committed assertions, not a new owner acceptance.
# Never advance this checkpoint to HEAD: that would authorize unreviewed changes.
GOVERNANCE_CHECKPOINT = "1132dc8d0da42d1d4c13cee2052fb1b10575b82b"
PROTECTED_PREFIXES = (
    "docs/adr/",
    "docs/architecture/",
    "docs/quality/",
    "docs/requirements/",
    "docs/roadmap/",
    "docs/security/",
    "docs/ux/",
)
PROTECTED_FILES = {
    "docs/README.md",
    "docs/operations/backup-and-restoration.md",
    "docs/operations/care-guide-sources.md",
    "docs/operations/runtime-operations.md",
    "docs/operations/taxonomy-snapshot-refresh.md",
    "docs/plans/2026-10-01-extensible-animal-and-species-platform.md",
}
ADR_FILENAME = re.compile(r"([0-9]{4})-[a-z0-9]+(?:-[a-z0-9]+)*\.md")
INDEX_ENTRY = re.compile(r"\|\s*\[([0-9]{4})\]\(([^)]+)\)\s*\|")
APPROVED_FILE = re.compile(r"^- Approved file: `([^`]+)` SHA-256: `([0-9a-f]{64})`$", re.MULTILINE)


@dataclass(frozen=True)
class Decision:
    path: str
    number: str
    status: str
    text: str


def protected_architecture_changes(paths: set[str]) -> set[str]:
    return {
        path for path in paths if path in PROTECTED_FILES or path.startswith(PROTECTED_PREFIXES)
    }


def git(root: Path, *args: str, data: bytes | None = None) -> bytes:
    return subprocess.run(
        ["git", *args], cwd=root, input=data, capture_output=True, check=True
    ).stdout


def relevant(path: str) -> bool:
    return bool(protected_architecture_changes({path})) or (
        path.startswith("docs/evidence/") and path.endswith(".md")
    )


def blobs(root: Path, objects: dict[str, str]) -> dict[str, bytes]:
    paths = sorted(path for path in objects if relevant(path))
    if not paths:
        return {}
    raw = git(root, "cat-file", "--batch", data="".join(objects[p] + "\n" for p in paths).encode())
    result: dict[str, bytes] = {}
    offset = 0
    for path in paths:
        end = raw.index(b"\n", offset)
        _, kind, size = raw[offset:end].split()
        if kind != b"blob":
            raise ValueError(f"not a document blob: {path}")
        offset = end + 1
        length = int(size)
        result[path] = raw[offset : offset + length]
        offset += length + 1
    return result


def committed(root: Path, revision: str) -> dict[str, bytes]:
    objects: dict[str, str] = {}
    for entry in git(root, "ls-tree", "-rz", revision, "--", "docs").split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, _, oid = metadata.decode().split()
        path = name.decode()
        if relevant(path):
            if mode not in {"100644", "100755"}:
                raise ValueError(f"unsupported document mode: {path}")
            objects[path] = oid
    return blobs(root, objects)


def staged(root: Path) -> dict[str, bytes]:
    objects: dict[str, str] = {}
    for entry in git(root, "ls-files", "--stage", "-z", "--", "docs").split(b"\0"):
        if not entry:
            continue
        metadata, name = entry.split(b"\t", 1)
        mode, oid, stage = metadata.decode().split()
        path = name.decode()
        if relevant(path):
            if stage != "0" or mode not in {"100644", "100755"}:
                raise ValueError(f"unmerged or unsupported staged document: {path}")
            objects[path] = oid
    return blobs(root, objects)


def working(root: Path) -> dict[str, bytes]:
    paths = {
        name.decode()
        for name in git(root, "ls-files", "--cached", "--others", "-z", "--", "docs").split(b"\0")
        if name
    }
    result: dict[str, bytes] = {}
    for path in sorted(paths):
        if relevant(path):
            target = root / path
            if target.is_symlink():
                raise ValueError(f"symlink document: {path}")
            if target.is_file():
                result[path] = target.read_bytes()
    return result


def field(text: str, name: str) -> list[str]:
    return re.findall(rf"^(?:- )?{re.escape(name)}:\s*(.+)$", text, re.MULTILINE)


def valid_date(value: str) -> bool:
    try:
        return date.fromisoformat(value).isoformat() == value
    except ValueError:
        return False


def catalog(documents: dict[str, bytes], failures: list[str]) -> dict[str, Decision]:
    decisions: dict[str, Decision] = {}
    for path, content in sorted(documents.items()):
        name = Path(path).name
        if Path(path).parent.as_posix() != "docs/adr":
            continue
        text = content.decode("utf-8")
        if not re.match(r"[0-9]", name) and not re.match(r"# ADR-", text):
            continue
        match = ADR_FILENAME.fullmatch(name)
        if match is None or int(match[1]) == 0:
            failures.append(f"invalid ADR filename: {path}")
            continue
        number = match[1]
        title = re.findall(r"^# ADR-([0-9]{4}): .+$", text, re.MULTILINE)
        if title != [number]:
            failures.append(f"ADR title ID differs from filename: {path}")
        if number in decisions:
            failures.append(f"duplicate ADR ID {number}: {path}")
        statuses = field(text, "Status")
        status = statuses[0].split(" for ")[0] if len(statuses) == 1 else ""
        if not (
            len(statuses) == 1
            and (
                statuses[0] in {"Accepted", "Superseded"}
                or re.fullmatch(r"Proposed(?: for .+)?", statuses[0])
            )
        ):
            failures.append(f"invalid ADR status: {path}")
        acceptance = field(text, "Acceptance date")
        if status == "Proposed" and acceptance:
            failures.append(f"Proposed ADR has an Acceptance date: {path}")
        elif status in {"Accepted", "Superseded"} and (
            len(acceptance) != 1 or not valid_date(acceptance[0])
        ):
            failures.append(f"invalid Acceptance date: {path}")
        decisions[number] = Decision(path, number, status, text)
    return decisions


def validate_index(documents: dict[str, bytes], decisions: dict[str, Decision]) -> list[str]:
    failures: list[str] = []
    text = documents.get("docs/adr/README.md", b"").decode("utf-8")
    seen: set[str] = set()
    for line in text.splitlines():
        if not re.match(r"\|\s*\[\d", line):
            continue
        match = INDEX_ENTRY.match(line)
        if match is None:
            failures.append("malformed ADR index entry")
            continue
        number, target = match.groups()
        if number in seen:
            failures.append(f"duplicate index entry: {number}")
        seen.add(number)
        decision = decisions.get(number)
        if decision is None:
            failures.append(f"index entry has missing ADR: {number}")
        elif target != Path(decision.path).name:
            failures.append(f"index filename/ID mismatch: {number}")
    failures.extend(f"ADR missing from ADR index: {n}" for n in sorted(decisions.keys() - seen))
    if "decision freeze is active" not in text:
        failures.append("ADR index does not record the active decision freeze")
    package = documents.get("docs/README.md", b"").decode("utf-8")
    if field(package, "Status") != ["Approved"] or "decision freeze" not in package.lower():
        failures.append("architecture index does not record approval and decision freeze")
    return failures


def approvals(documents: dict[str, bytes], decisions: dict[str, Decision]) -> dict[str, set[str]]:
    authorized: dict[str, set[str]] = {}
    for path, content in sorted(documents.items()):
        if not path.startswith("docs/evidence/") or not path.endswith(".md"):
            continue
        text = content.decode("utf-8")
        authority = field(text, "Authority")
        review = field(text, "Review status")
        dates = field(text, "Acceptance date")
        if not (
            len(authority) == 1
            and re.search(r"\bowner\b", authority[0], re.IGNORECASE)
            and len(review) == 1
            and re.fullmatch(r"Accepted(?: for .+)?", review[0])
            and len(dates) == 1
            and valid_date(dates[0])
        ):
            continue
        numbers = set(re.findall(r"\bADR-([0-9]{4})\b", " ".join(field(text, "Decision"))))
        numbers = {
            n
            for n in numbers
            if n in decisions and decisions[n].status in {"Accepted", "Superseded"}
        }
        for target, digest in APPROVED_FILE.findall(text):
            if target in documents and hashlib.sha256(documents[target]).hexdigest() == digest:
                authorized.setdefault(target, set()).update(numbers)
    return authorized


def index_narrative(content: bytes) -> list[str]:
    return [line for line in content.decode("utf-8").splitlines() if not INDEX_ENTRY.match(line)]


def index_maintenance(current: bytes, baseline: bytes, previous: dict[str, Decision]) -> bool:
    if index_narrative(current) != index_narrative(baseline):
        return False
    rows = []
    for content in (current, baseline):
        rows.append(
            {
                match[1]: line
                for line in content.decode("utf-8").splitlines()
                if (match := INDEX_ENTRY.match(line))
            }
        )
    return all(
        rows[0].get(number) == rows[1].get(number)
        for number, decision in previous.items()
        if decision.status in {"Accepted", "Superseded"}
    )


def validate_snapshot(documents: dict[str, bytes], baseline: dict[str, bytes]) -> list[str]:
    failures: list[str] = []
    decisions = catalog(documents, failures)
    failures.extend(validate_index(documents, decisions))
    previous = catalog(baseline, [])
    authorized = approvals(documents, decisions)
    for number, decision in decisions.items():
        old = previous.get(number)
        if (
            old is not None
            and old.status in {"Accepted", "Superseded"}
            and decision.status == "Proposed"
        ):
            failures.append(f"accepted decision cannot return to Proposed: {decision.path}")
        protected = decision.status in {"Accepted", "Superseded"} or (
            old is not None and old.status in {"Accepted", "Superseded"}
        )
        if (
            protected
            and documents[decision.path] != baseline.get(decision.path)
            and number not in authorized.get(decision.path, set())
        ):
            failures.append(f"ADR needs content-bound owner approval evidence: {decision.path}")
        if decision.status == "Superseded":
            successor = field(decision.text, "Superseded by")
            replacement = (
                decisions.get(successor[0].removeprefix("ADR-")) if len(successor) == 1 else None
            )
            if (
                replacement is None
                or replacement.status != "Accepted"
                or replacement.number == number
            ):
                failures.append(f"Superseded ADR needs an Accepted successor: {decision.path}")
    for old in previous.values():
        if old.status in {"Accepted", "Superseded"} and old.path not in documents:
            failures.append(f"protected accepted ADR deleted: {old.path}; retain it as Superseded")
    adr_paths = {d.path for d in decisions.values()} | {d.path for d in previous.values()}
    for path in sorted(protected_architecture_changes(set(documents) | set(baseline)) - adr_paths):
        if path.startswith("docs/adr/") and Path(path).name != "README.md":
            continue  # Unrelated notes are not architecture decisions.
        if documents.get(path) == baseline.get(path):
            continue
        # Membership-only index maintenance is checked structurally, not an architecture amendment.
        if path == "docs/adr/README.md" and index_maintenance(
            documents.get(path, b""), baseline.get(path, b""), previous
        ):
            continue
        if not authorized.get(path):
            failures.append(
                f"frozen architecture needs content-bound owner approval evidence: {path}"
            )
    return failures


def validate_repository(root: Path, checkpoint: str = GOVERNANCE_CHECKPOINT) -> list[str]:
    try:
        git(root, "merge-base", "--is-ancestor", checkpoint, "HEAD")
        baseline = committed(root, checkpoint)
        baseline_failures: list[str] = []
        baseline_decisions = catalog(baseline, baseline_failures)
        baseline_failures.extend(validate_index(baseline, baseline_decisions))
        if baseline_failures:
            return ["invalid governance checkpoint: " + "; ".join(baseline_failures)]
        views = {
            "HEAD": committed(root, "HEAD"),
            "index": staged(root),
            "working tree": working(root),
        }
        return [
            f"{label}: {failure}"
            for label, documents in views.items()
            for failure in validate_snapshot(documents, baseline)
        ]
    except (subprocess.CalledProcessError, OSError, UnicodeError, ValueError) as error:
        return [f"could not inspect governance checkpoint/repository safely: {error}"]


def main() -> int:
    failures = validate_repository(ROOT)
    try:
        git(ROOT, "merge-base", "--is-ancestor", BASELINE_COMMIT, GOVERNANCE_CHECKPOINT)
    except subprocess.CalledProcessError:
        failures.append(
            "original architecture baseline is not an ancestor of the governance checkpoint"
        )
    if failures:
        print("architecture freeze failures:\n" + "\n".join(failures), file=sys.stderr)
        return 1
    decisions = catalog(working(ROOT), [])
    counts = {
        status: sum(d.status == status for d in decisions.values())
        for status in ("Accepted", "Proposed", "Superseded")
    }
    print(
        "architecture freeze passed: "
        + ", ".join(f"{count} {status.lower()} ADRs" for status, count in counts.items())
        + "; HEAD, index and working tree validated"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
