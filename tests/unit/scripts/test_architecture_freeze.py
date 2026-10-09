from __future__ import annotations

import hashlib
import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).parents[3]
MODULE_PATH = ROOT / "scripts/quality/verify_architecture_freeze.py"
SPEC = importlib.util.spec_from_file_location("verify_architecture_freeze", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
freeze = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = freeze
SPEC.loader.exec_module(freeze)


def git(root: Path, *args: str) -> str:
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def write(root: Path, path: str, text: str) -> None:
    target = root / path
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(text, encoding="utf-8")


def adr(number: str, status: str = "Proposed", decision: str = "Use exact contracts.") -> str:
    acceptance = "Acceptance date: 2026-08-04\n" if status != "Proposed" else ""
    return f"# ADR-{number}: Test decision\n\nStatus: {status}\n{acceptance}\n{decision}\n"


def index(root: Path, *numbers: str) -> None:
    write(
        root,
        "docs/adr/README.md",
        "# ADR index\n\nThe decision freeze is active.\n\n| ADR | Decision |\n|---|---|\n"
        + "".join(f"| [{n}]({n}-test.md) | Test decision |\n" for n in numbers),
    )


@pytest.fixture
def repository(tmp_path: Path) -> tuple[Path, str]:
    git(tmp_path, "init", "--quiet")
    git(tmp_path, "config", "user.name", "Governance fixture")
    git(tmp_path, "config", "user.email", "fixture@example.invalid")
    write(
        tmp_path, "docs/README.md", "# Architecture\n\nStatus: Approved\nDecision freeze active.\n"
    )
    write(tmp_path, "docs/adr/0001-test.md", adr("0001", "Accepted"))
    write(tmp_path, "docs/architecture/model.md", "# Frozen model\n\nUse typed contracts.\n")
    index(tmp_path, "0001")
    git(tmp_path, "add", "docs")
    git(tmp_path, "commit", "--quiet", "-m", "Inherited accepted checkpoint")
    return tmp_path, git(tmp_path, "rev-parse", "HEAD")


def add_proposed(root: Path, number: str = "0002") -> None:
    write(root, f"docs/adr/{number}-test.md", adr(number))
    index(root, "0001", number)


def approval(root: Path, target: str, number: str) -> None:
    digest = hashlib.sha256((root / target).read_bytes()).hexdigest()
    write(
        root,
        "docs/evidence/m0-architecture/approval.md",
        "# Architecture amendment evidence\n\n"
        f"- Decision: ADR-{number}\n"
        "- Acceptance date: 2026-08-04\n"
        "- Authority: owner instruction recorded in review\n"
        "- Review status: Accepted\n"
        f"- Approved file: `{target}` SHA-256: `{digest}`\n",
    )


def failures(repository: tuple[Path, str]) -> list[str]:
    root, baseline = repository
    return freeze.validate_repository(root, baseline)


def test_existing_accepted_catalog_is_preserved(repository: tuple[Path, str]) -> None:
    assert failures(repository) == []


@pytest.mark.parametrize("state", ["untracked", "staged", "committed"])
def test_indexed_proposed_decision_needs_no_acceptance(
    repository: tuple[Path, str], state: str
) -> None:
    root, _ = repository
    add_proposed(root)
    if state != "untracked":
        git(root, "add", "docs")
    if state == "committed":
        git(root, "commit", "--quiet", "-m", "Proposed decision")
    assert failures(repository) == []


def test_multiple_proposals_and_existing_status_qualifier(repository: tuple[Path, str]) -> None:
    root, _ = repository
    add_proposed(root)
    write(
        root, "docs/adr/0003-test.md", adr("0003").replace("Proposed", "Proposed for owner review")
    )
    index(root, "0001", "0002", "0003")
    write(root, "docs/adr/notes.md", "# Unrelated notes\n")
    assert failures(repository) == []


@pytest.mark.parametrize(
    ("path", "text", "message"),
    [
        ("docs/adr/0002-other.md", adr("0002"), "duplicate ADR ID"),
        ("docs/adr/002-test.md", adr("0002"), "invalid ADR filename"),
        ("docs/adr/0002-test.md", adr("0003"), "title ID"),
        ("docs/adr/0002-test.md", adr("0002", "Maybe"), "status"),
        ("docs/adr/0002-test.md", adr("0002") + "Status: Accepted\n", "status"),
        ("docs/adr/0002-test.md", adr("0002") + "Acceptance date: 2026-08-04\n", "Proposed"),
    ],
)
def test_invalid_catalog_is_rejected(
    repository: tuple[Path, str], path: str, text: str, message: str
) -> None:
    root, _ = repository
    add_proposed(root)
    write(root, path, text)
    assert any(message in error for error in failures(repository))


def test_missing_index_membership_is_rejected(repository: tuple[Path, str]) -> None:
    root, _ = repository
    write(root, "docs/adr/0002-test.md", adr("0002"))
    assert any("missing from ADR index" in error for error in failures(repository))


def test_index_without_document_is_rejected(repository: tuple[Path, str]) -> None:
    root, _ = repository
    index(root, "0001", "0002")
    assert any("missing ADR" in error for error in failures(repository))


def test_duplicate_index_membership_is_rejected(repository: tuple[Path, str]) -> None:
    root, _ = repository
    index(root, "0001", "0001")
    assert any("duplicate index" in error for error in failures(repository))


@pytest.mark.parametrize("state", ["working", "staged", "committed"])
def test_unapproved_accepted_change_is_rejected(repository: tuple[Path, str], state: str) -> None:
    root, _ = repository
    write(root, "docs/adr/0001-test.md", adr("0001", "Accepted", "Use arbitrary JSON."))
    if state != "working":
        git(root, "add", "docs")
    if state == "committed":
        git(root, "commit", "--quiet", "-m", "Unauthorized architecture change")
    assert any("approval evidence" in error for error in failures(repository))


def test_worktree_repair_cannot_hide_invalid_staged_content(repository: tuple[Path, str]) -> None:
    root, _ = repository
    write(root, "docs/adr/0001-test.md", adr("0001", "Accepted", "Use arbitrary JSON."))
    git(root, "add", "docs/adr/0001-test.md")
    write(root, "docs/adr/0001-test.md", adr("0001", "Accepted"))
    assert any("index:" in error and "approval evidence" in error for error in failures(repository))


def test_accepted_promotion_needs_content_bound_owner_evidence(
    repository: tuple[Path, str],
) -> None:
    root, _ = repository
    write(root, "docs/adr/0002-test.md", adr("0002", "Accepted"))
    index(root, "0001", "0002")
    assert any("approval evidence" in error for error in failures(repository))
    approval(root, "docs/adr/0002-test.md", "0002")
    assert failures(repository) == []
    write(root, "docs/adr/0002-test.md", adr("0002", "Accepted", "Unreviewed extra behavior."))
    assert any("approval evidence" in error for error in failures(repository))


def test_proposed_to_accepted_transition_requires_evidence(repository: tuple[Path, str]) -> None:
    root, baseline = repository
    add_proposed(root)
    git(root, "add", "docs")
    git(root, "commit", "--quiet", "-m", "Proposed decision")
    write(root, "docs/adr/0002-test.md", adr("0002", "Accepted"))
    assert freeze.validate_repository(root, baseline)


@pytest.mark.parametrize("defect", ["no owner", "no acceptance", "wrong decision", "bad date"])
def test_incomplete_approval_does_not_authorize_acceptance(
    repository: tuple[Path, str], defect: str
) -> None:
    root, _ = repository
    write(root, "docs/adr/0002-test.md", adr("0002", "Accepted"))
    index(root, "0001", "0002")
    approval(root, "docs/adr/0002-test.md", "0002")
    evidence = root / "docs/evidence/m0-architecture/approval.md"
    replacements = {
        "no owner": ("owner instruction", "automation instruction"),
        "no acceptance": ("Review status: Accepted", "Review status: Pending"),
        "wrong decision": ("ADR-0002", "ADR-0001"),
        "bad date": ("2026-08-04", "2026-99-99"),
    }
    before, after = replacements[defect]
    evidence.write_text(evidence.read_text().replace(before, after))
    assert any("approval evidence" in error for error in failures(repository))


def test_accepted_amendment_with_scoped_evidence_passes(repository: tuple[Path, str]) -> None:
    root, _ = repository
    write(root, "docs/adr/0001-test.md", adr("0001", "Accepted", "Approved updated contract."))
    approval(root, "docs/adr/0001-test.md", "0001")
    assert failures(repository) == []


def test_other_frozen_documents_remain_protected(repository: tuple[Path, str]) -> None:
    root, _ = repository
    write(root, "docs/architecture/model.md", "# Model\n\nUse arbitrary JSON.\n")
    assert any("approval evidence" in error for error in failures(repository))
    approval(root, "docs/architecture/model.md", "0001")
    assert failures(repository) == []


def test_accepted_document_cannot_be_deleted(repository: tuple[Path, str]) -> None:
    root, _ = repository
    (root / "docs/adr/0001-test.md").unlink()
    index(root)
    assert any("deleted" in error for error in failures(repository))


def test_missing_checkpoint_fails_closed(repository: tuple[Path, str]) -> None:
    root, _ = repository
    assert any("checkpoint" in error for error in freeze.validate_repository(root, "missing"))


@pytest.mark.parametrize("state", ["staged", "committed"])
def test_recorded_acceptance_passes_in_git_views(repository: tuple[Path, str], state: str) -> None:
    root, _ = repository
    write(root, "docs/adr/0002-test.md", adr("0002", "Accepted"))
    index(root, "0001", "0002")
    approval(root, "docs/adr/0002-test.md", "0002")
    git(root, "add", "docs")
    if state == "committed":
        git(root, "commit", "--quiet", "-m", "Recorded architecture acceptance")
    assert failures(repository) == []


def test_supersession_needs_an_accepted_successor(repository: tuple[Path, str]) -> None:
    root, _ = repository
    write(root, "docs/adr/0001-test.md", adr("0001", "Superseded"))
    approval(root, "docs/adr/0001-test.md", "0001")
    assert any("Accepted successor" in error for error in failures(repository))
    write(root, "docs/adr/0002-test.md", adr("0002", "Accepted"))
    write(root, "docs/adr/0001-test.md", adr("0001", "Superseded") + "Superseded by: ADR-0002\n")
    index(root, "0001", "0002")
    approval(root, "docs/adr/0001-test.md", "0001")
    evidence = root / "docs/evidence/m0-architecture/approval.md"
    old_approval = evidence.read_text()
    approval(root, "docs/adr/0002-test.md", "0002")
    write(root, "docs/evidence/m0-architecture/supersession.md", old_approval)
    assert failures(repository) == []


def test_accepted_decision_cannot_be_downgraded_to_proposed(repository: tuple[Path, str]) -> None:
    root, _ = repository
    write(root, "docs/adr/0001-test.md", adr("0001"))
    approval(root, "docs/adr/0001-test.md", "0001")
    assert any("cannot return to Proposed" in error for error in failures(repository))


def test_title_cannot_hide_an_adr_in_an_unrelated_filename(repository: tuple[Path, str]) -> None:
    root, _ = repository
    write(root, "docs/adr/notes.md", adr("0002"))
    assert any("invalid ADR filename" in error for error in failures(repository))


def test_index_link_must_match_the_discovered_filename(repository: tuple[Path, str]) -> None:
    root, _ = repository
    add_proposed(root)
    target = root / "docs/adr/README.md"
    target.write_text(target.read_text().replace("(0002-test.md)", "(0001-test.md)"))
    assert any("index filename/ID mismatch" in error for error in failures(repository))


def test_accepted_index_description_is_still_frozen(repository: tuple[Path, str]) -> None:
    root, _ = repository
    target = root / "docs/adr/README.md"
    target.write_text(target.read_text().replace("| Test decision |", "| Use arbitrary JSON |"))
    assert any("approval evidence" in error for error in failures(repository))


def test_protected_architecture_changes_exclude_unrelated_plans_runbooks_and_evidence() -> None:
    assert freeze.protected_architecture_changes(
        {
            "docs/architecture/model.md",
            "docs/plans/phase1.md",
            "docs/operations/unrelated.md",
            "docs/evidence/m1/README.md",
        }
    ) == {"docs/architecture/model.md"}


@pytest.mark.parametrize(
    "path",
    [
        "docs/README.md",
        "docs/operations/backup-and-restoration.md",
        "docs/operations/runtime-operations.md",
        "docs/plans/2026-10-01-extensible-animal-and-species-platform.md",
        "docs/operations/care-guide-sources.md",
        "docs/operations/taxonomy-snapshot-refresh.md",
    ],
)
def test_controlling_documents_are_protected(path: str) -> None:
    assert freeze.protected_architecture_changes({path}) == {path}
    assert freeze.relevant(path)


@pytest.mark.parametrize("view", ["HEAD", "index", "working tree"])
def test_existing_twelve_content_bound_approvals_are_loaded_and_validated(view: str) -> None:
    documents = {
        "HEAD": lambda: freeze.committed(ROOT, "HEAD"),
        "index": lambda: freeze.staged(ROOT),
        "working tree": lambda: freeze.working(ROOT),
    }[view]()
    evidence = documents["docs/evidence/m6.6-species-aware-husbandry/README.md"].decode()
    entries = freeze.APPROVED_FILE.findall(evidence)
    assert len(entries) == len(dict(entries)) == 12
    decisions = freeze.catalog(documents, [])
    authorized = freeze.approvals(documents, decisions)
    for path, digest in entries:
        assert path in freeze.protected_architecture_changes({path})
        assert path in documents
        assert hashlib.sha256(documents[path]).hexdigest() == digest
        assert "0028" in authorized.get(path, set())
    baseline = freeze.committed(ROOT, freeze.GOVERNANCE_CHECKPOINT)
    assert freeze.validate_snapshot(documents, baseline) == []


@pytest.mark.parametrize(
    "path",
    [
        "docs/plans/2026-10-01-extensible-animal-and-species-platform.md",
        "docs/operations/care-guide-sources.md",
        "docs/operations/taxonomy-snapshot-refresh.md",
    ],
)
@pytest.mark.parametrize(
    ("state", "label"), [("working", "working tree"), ("staged", "index"), ("committed", "HEAD")]
)
def test_controlling_document_edits_require_exact_content_approval_in_each_git_view(
    repository: tuple[Path, str], path: str, state: str, label: str
) -> None:
    root, _ = repository
    approved = "# Owner-reviewed controlling contract\n\nUse the reviewed policy.\n"
    edited = "# Changed controlling contract\n\nUse an unreviewed policy.\n"
    write(root, path, approved)
    approval(root, path, "0001")
    git(root, "add", "docs")
    git(root, "commit", "--quiet", "-m", "Exact-content owner approval")
    assert failures(repository) == []

    write(root, path, edited)
    if state != "working":
        git(root, "add", path)
        if state == "committed":
            git(root, "commit", "--quiet", "-m", "Unapproved controlling-document edit")
        # Repair later views so only the intended HEAD or index snapshot is invalid.
        write(root, path, approved)
        if state == "committed":
            git(root, "add", path)
    errors = failures(repository)
    assert len(errors) == 1
    assert errors[0].startswith(f"{label}:")
    assert "content-bound owner approval evidence" in errors[0] and path in errors[0]

    write(root, path, edited)
    approval(root, path, "0001")
    if state != "working":
        git(root, "add", "docs")
    if state == "committed":
        git(root, "commit", "--quiet", "-m", "Owner-approved future exact content")
    assert failures(repository) == []

    write(root, path, edited + "\nAnother unreviewed change.\n")
    assert any(
        error.startswith("working tree:") and "approval evidence" in error and path in error
        for error in failures(repository)
    )
