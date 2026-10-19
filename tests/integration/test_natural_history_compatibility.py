from __future__ import annotations

import os
import sqlite3
import subprocess
from pathlib import Path

import pytest
from alembic import command

from snaketracker.infrastructure.database.engine import create_sqlite_engine
from snaketracker.infrastructure.taxonomy.catalog import LocalTaxonomyCatalog
from snaketracker.infrastructure.taxonomy.natural_history import NaturalHistoryRepository
from tests.integration.test_boa_care_guide import _table_hashes
from tests.integration.test_local_taxonomy import taxon
from tests.integration.test_natural_history import NOW, boa, version
from tests.integration.test_taxonomy_compatibility import config_for

ROOT = Path(__file__).parents[2]


def test_isolated_backup_upgrade_retains_all_tables_and_blocks_destructive_downgrade(tmp_path):
    # Populated real commands, inventory FIFO, guide bundle, events and projections.
    from snaketracker.infrastructure.taxonomy.care_guides import SQLAlchemyCareGuideRepository
    from tests.integration.test_care_guides import _bundle
    from tests.integration.test_structured_inventory_feeding import _setup

    engine, _bootstrap, _store, _inventory, _animals, _animal = _setup(tmp_path)
    path = tmp_path / "structured-inventory.sqlite3"
    engine.dispose()
    # _setup uses current head. Empty additive X3 can safely downgrade for the old-source fixture.
    command.downgrade(config_for(path), "0024_local_taxonomy")
    engine = create_sqlite_engine(path, require_local_storage=False)
    catalog = LocalTaxonomyCatalog(engine)
    catalog.publish(taxon("python", "Python regius", "snake"), retrieved_at=NOW)
    # Retain historical immutable guide versions by importing one fixture guide.
    bundle = _bundle().model_copy(update={"guides": (_bundle().guides[0],)})
    SQLAlchemyCareGuideRepository(engine).import_bundle(bundle)
    identifier = boa(catalog)
    engine.dispose()
    restored = tmp_path / "restored.sqlite3"
    with sqlite3.connect(path) as original, sqlite3.connect(restored) as target:
        original.backup(target)
    before = _table_hashes(restored)
    with sqlite3.connect(restored) as c:
        guides = c.execute("SELECT * FROM care_guide_versions").fetchall()
    command.upgrade(config_for(restored), "head")
    after = _table_hashes(restored)
    assert all(
        after[name] == digest for name, digest in before.items() if name != "alembic_version"
    )
    with sqlite3.connect(restored) as c:
        assert c.execute("SELECT * FROM care_guide_versions").fetchall() == guides
        assert c.execute("PRAGMA foreign_key_check").fetchall() == []
    engine = create_sqlite_engine(restored, require_local_storage=False)
    item = version(identifier)
    repo = NaturalHistoryRepository(engine)
    repo.retain(item)
    with pytest.raises(RuntimeError, match="downgrade blocked"):
        command.downgrade(config_for(restored), "0024_local_taxonomy")
    assert repo.versions(identifier) == (item,)
    engine.dispose()


def test_actual_previous_compatibility_reader_rejects_new_schema(tmp_path):
    # Execute the actual merged-main compatibility module, not an imitation version check.
    path = tmp_path / "x3.sqlite3"
    command.upgrade(config_for(path), "head")
    previous = subprocess.check_output(
        ["git", "show", "94ea887:src/snaketracker/bootstrap/compatibility.py"], cwd=ROOT, text=True
    )
    module = tmp_path / "previous_compatibility.py"
    module.write_text(previous)
    result = subprocess.run(
        [
            str(ROOT / ".venv/bin/python"),
            "-c",
            "import importlib.util,sys; "
            "from snaketracker.infrastructure.database.engine import create_sqlite_engine; "
            "spec=importlib.util.spec_from_file_location('previous',sys.argv[1]); "
            "m=importlib.util.module_from_spec(spec);sys.modules['previous']=m; "
            "spec.loader.exec_module(m); "
            "p=__import__('pathlib').Path(sys.argv[2]); "
            "e=create_sqlite_engine(p,require_local_storage=False); "
            "r=m.inspect_database_compatibility(e);print(r.mode.value); "
            "assert not r.normal_readiness;e.dispose()",
            str(module),
            str(path),
        ],
        capture_output=True,
        text=True,
        env=os.environ.copy(),
    )
    assert result.returncode == 0, result.stderr
    assert "recovery_required" in result.stdout
