"""Real process-lifetime and private-artifact recovery regressions."""

import logging
import multiprocessing
import os
import signal
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def staging_diagnostics(monkeypatch):
    # Other migration fixtures disable pre-existing loggers in this interpreter.
    monkeypatch.setattr(
        logging.getLogger("snaketracker.infrastructure.backups.staging"), "disabled", False
    )


def _active_stage(root, channel):
    from snaketracker.infrastructure.backups.staging import VerificationStaging

    with VerificationStaging(Path(root)).database(b"private verification contents") as database:
        channel.send(str(database))
        channel.recv()


def test_private_verification_crash_is_cleaned_only_after_process_death_and_lease(tmp_path):
    from snaketracker.infrastructure.backups import staging

    manager = staging.VerificationStaging(tmp_path)
    unrelated = tmp_path / "legitimate-recovery-point"
    unrelated.write_bytes(b"preserve recovery")
    parent, child = multiprocessing.Pipe()
    process = multiprocessing.Process(target=_active_stage, args=(str(tmp_path), child))
    process.start()
    try:
        assert parent.poll(5)
        database = Path(parent.recv())
        assert manager.cleanup(lease_valid=lambda: True) == 0
        assert database.read_bytes() == b"private verification contents"
        os.kill(process.pid, signal.SIGKILL)
        process.join(5)
        assert process.exitcode == -signal.SIGKILL
        assert manager.cleanup(lease_valid=lambda: False) == 0
        assert database.exists()
        assert manager.cleanup(lease_valid=lambda: True) == 1
        assert not database.parent.exists()
        assert unrelated.read_bytes() == b"preserve recovery"
    finally:
        if process.is_alive():
            process.kill()
        process.join()
        parent.close()
        child.close()


def test_unrecognized_private_artifacts_are_retained_with_diagnostics(tmp_path, caplog):
    from snaketracker.infrastructure.backups import staging

    suspicious = tmp_path / ".snaketracker-backup-verify-unrecognized"
    suspicious.mkdir()
    target = tmp_path / "completed-database.sqlite3"
    target.write_bytes(b"preserve")
    (suspicious / "database.sqlite3").symlink_to(target)
    manager = staging.VerificationStaging(tmp_path)
    assert manager.cleanup(lease_valid=lambda: True) == 0
    assert target.read_bytes() == b"preserve"
    assert suspicious.exists()
    assert "unrecognized" in caplog.text


def test_verification_setup_enospc_removes_only_owned_staging(tmp_path, monkeypatch):
    import errno

    from snaketracker.infrastructure.backups import staging

    manager = staging.VerificationStaging(tmp_path)
    monkeypatch.setattr(
        os,
        "posix_fallocate",
        lambda *_: (_ for _ in ()).throw(OSError(errno.ENOSPC, "no verification space")),
    )
    with pytest.raises(OSError, match="no verification space"), manager.database(b"private"):
        pytest.fail("verification unexpectedly admitted")
    assert list(tmp_path.iterdir()) == []


def _abandoned(root):
    parent, child = multiprocessing.Pipe()
    process = multiprocessing.Process(target=_active_stage, args=(str(root), child))
    process.start()
    try:
        assert parent.poll(5)
        database = Path(parent.recv())
        process.kill()
        process.join(5)
        assert process.exitcode == -signal.SIGKILL
        return database
    finally:
        if process.is_alive():
            process.kill()
        process.join()
        parent.close()
        child.close()


def test_cleanup_resumes_after_guard_removal_without_deleting_other_recovery(tmp_path, monkeypatch):
    from snaketracker.infrastructure.backups.staging import VerificationStaging

    database = _abandoned(tmp_path)
    original = Path.unlink

    def interrupted(path, *args, **kwargs):
        if path.name.endswith(".json"):
            raise OSError("interrupted after guard removal")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", interrupted)
        assert VerificationStaging(tmp_path).cleanup(lease_valid=lambda: True) == 0
    assert not database.parent.exists()
    assert VerificationStaging(tmp_path).cleanup(lease_valid=lambda: True) == 1
    assert list(tmp_path.iterdir()) == []


def test_fifo_replacement_is_rejected_without_blocking_cleanup(tmp_path, caplog):
    from snaketracker.infrastructure.backups.staging import VerificationStaging

    database = _abandoned(tmp_path)
    database.unlink()
    os.mkfifo(database, 0o600)
    assert VerificationStaging(tmp_path).cleanup(lease_valid=lambda: True) == 0
    assert database.exists()
    assert "unrecognized" in caplog.text


def test_retained_entries_do_not_starve_a_later_owned_orphan(tmp_path):
    from snaketracker.infrastructure.backups.staging import VerificationStaging

    for index in range(40):
        (tmp_path / f".snaketracker-backup-verify-unrecognized-{index}").mkdir()
    database = _abandoned(tmp_path)
    manager = VerificationStaging(tmp_path)
    removed = sum(manager.cleanup(lease_valid=lambda: True) for _ in range(4))
    assert removed == 1
    assert not database.parent.exists()
    assert all(
        (tmp_path / f".snaketracker-backup-verify-unrecognized-{index}").is_dir()
        for index in range(40)
    )


def test_database_replaced_during_lease_renewal_is_preserved(tmp_path, caplog):
    from snaketracker.infrastructure.backups.staging import VerificationStaging

    database = _abandoned(tmp_path)
    calls = 0

    def renew():
        nonlocal calls
        calls += 1
        if calls == 2:
            replacement = database.with_name("replacement")
            replacement.write_bytes(b"unrelated recovery data")
            replacement.chmod(0o600)
            replacement.replace(database)
        return True

    assert VerificationStaging(tmp_path).cleanup(lease_valid=renew) == 0
    assert database.read_bytes() == b"unrelated recovery data"
    assert "changed during lease renewal" in caplog.text


def test_cleanup_requires_lease_to_remain_valid_at_deletion(tmp_path):
    from snaketracker.infrastructure.backups.staging import VerificationStaging

    database = _abandoned(tmp_path)
    calls = 0

    def renew():
        nonlocal calls
        calls += 1
        return calls == 1

    assert VerificationStaging(tmp_path).cleanup(lease_valid=renew) == 0
    assert database.read_bytes() == b"private verification contents"
    assert VerificationStaging(tmp_path).cleanup(lease_valid=lambda: True) == 1


def test_orphan_cleanup_allocates_no_new_metadata_under_enospc(tmp_path, monkeypatch):
    import errno

    from snaketracker.infrastructure.backups.staging import VerificationStaging

    database = _abandoned(tmp_path)
    original = os.open

    def no_creation(path, flags, *args, **kwargs):
        if flags & os.O_CREAT:
            raise OSError(errno.ENOSPC, "no metadata space")
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", no_creation)
    assert VerificationStaging(tmp_path).cleanup(lease_valid=lambda: True) == 1
    assert not database.exists()
    assert list(tmp_path.iterdir()) == []


def test_interrupted_normal_teardown_remains_registered_and_recoverable(tmp_path, monkeypatch):
    from snaketracker.infrastructure.backups.staging import VerificationStaging

    original = Path.unlink

    def interrupt(path, *args, **kwargs):
        if path.name.endswith(".json"):
            raise OSError("simulated teardown interruption")
        return original(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "unlink", interrupt)
        with (
            pytest.raises(OSError, match="teardown interruption"),
            VerificationStaging(tmp_path).database(b"private") as database,
        ):
            assert database.read_bytes() == b"private"
    assert len(list(tmp_path.glob(".verification-owner-*.json"))) == 1
    assert VerificationStaging(tmp_path).cleanup(lease_valid=lambda: True) == 1
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("identity", ["guard", "directory", "database"])
def test_receipt_identity_mismatch_cannot_delete_plaintext(tmp_path, identity, caplog):
    import json

    from snaketracker.infrastructure.backups.staging import VerificationStaging

    database = _abandoned(tmp_path)
    marker = next(tmp_path.glob(".verification-owner-*.json"))
    receipt = json.loads(marker.read_text())
    receipt[identity][1] += 1
    marker.write_text(json.dumps(receipt))
    assert VerificationStaging(tmp_path).cleanup(lease_valid=lambda: True) == 0
    assert database.read_bytes() == b"private verification contents"
    assert "identity" in caplog.text


@pytest.mark.parametrize(
    "defect",
    [
        "guard-permissions",
        "guard-hardlink",
        "oversized-receipt",
        "purpose",
        "token",
        "directory-name",
        "extra-entry",
        "missing-guard",
        "tail-oversized",
        "tail-purpose",
    ],
)
def test_untrusted_artifact_metadata_cannot_authorize_plaintext_cleanup(tmp_path, defect, caplog):
    import json

    from snaketracker.infrastructure.backups.staging import VerificationStaging

    database = _abandoned(tmp_path)
    marker = next(tmp_path.glob(".verification-owner-*.json"))
    guard = marker.with_suffix(".lock")
    receipt = json.loads(marker.read_text())
    if defect == "guard-permissions":
        guard.chmod(0o644)
    elif defect == "guard-hardlink":
        os.link(guard, tmp_path / "unrelated-guard-alias")
    elif defect in {"oversized-receipt", "tail-oversized"}:
        marker.write_bytes(b"x" * 4097)
    elif defect in {"purpose", "tail-purpose"}:
        receipt["purpose"] = "unrelated-recovery-point"
        marker.write_text(json.dumps(receipt))
    elif defect == "token":
        receipt["token"] = "another-generation"
        marker.write_text(json.dumps(receipt))
    elif defect == "directory-name":
        receipt["directory_name"] = "../legitimate-recovery"
        marker.write_text(json.dumps(receipt))
    elif defect == "extra-entry":
        (database.parent / "legitimate-recovery-point").write_bytes(b"preserve")
    if defect == "missing-guard" or defect.startswith("tail-"):
        guard.unlink()
    assert VerificationStaging(tmp_path).cleanup(lease_valid=lambda: True) == 0
    assert database.read_bytes() == b"private verification contents"
    assert marker.exists()
    assert "Retained unrecognized" in caplog.text


def test_interrupted_database_removal_resumes_without_plaintext(tmp_path):
    from snaketracker.infrastructure.backups.staging import VerificationStaging

    database = _abandoned(tmp_path)
    database.unlink()
    assert VerificationStaging(tmp_path).cleanup(lease_valid=lambda: True) == 1
    assert not database.parent.exists()
    assert list(tmp_path.iterdir()) == []


@pytest.mark.parametrize("guard_present", [True, False])
def test_cleanup_tail_retains_receipt_when_lease_is_lost(tmp_path, guard_present):
    from snaketracker.infrastructure.backups.staging import VerificationStaging

    database = _abandoned(tmp_path)
    marker = next(tmp_path.glob(".verification-owner-*.json"))
    database.unlink()
    database.parent.rmdir()
    if not guard_present:
        marker.with_suffix(".lock").unlink()
    renewals = iter([True, False])
    assert VerificationStaging(tmp_path).cleanup(lease_valid=lambda: next(renewals)) == 0
    assert marker.exists()
    assert VerificationStaging(tmp_path).cleanup(lease_valid=lambda: True) == 1


def test_unsafe_root_and_unregistered_ownership_files_are_preserved(tmp_path, caplog):
    from snaketracker.infrastructure.backups.staging import VerificationStaging

    metadata = tmp_path / ".verification-owner-unregistered.lock"
    metadata.write_bytes(b"operator must inspect")
    tmp_path.chmod(0o777)
    with pytest.raises(ValueError, match="staging root"):
        VerificationStaging(tmp_path).cleanup(lease_valid=lambda: True)
    tmp_path.chmod(0o700)
    assert VerificationStaging(tmp_path).cleanup(lease_valid=lambda: True) == 0
    assert metadata.read_bytes() == b"operator must inspect"
    assert "operator inspection required" in caplog.text
