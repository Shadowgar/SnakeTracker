from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolated_application_composition(request, monkeypatch):
    """Existing in-process composition tests are not privileged launcher tests.

    Keep their route, scanner, worker-duty and storage-profile assertions intact.
    The explicit direct-admission tests and mandatory Linux/WAL qualification do
    not receive this fixture. Runtime source has no environment/test-mode bypass.
    """
    modules = {
        "test_species_directory_workflow.py",
        "test_operational_workflows.py",
        "test_multispecies_workflow.py",
        "test_password_recovery.py",
        "test_product_experience.py",
        "test_animal_care_workflow.py",
        "test_identity_flow.py",
        "test_x1_preflight.py",
        "test_application_startup.py",
        "test_care_guides.py",
        "test_production_operator_qualification.py",
        "test_demo_household_isolation.py",
        "test_m6_owner_review_demo.py",
        "test_admin_console.py",
    }
    if request.path.parent.name != "browser" and request.path.name not in modules:
        return
    from snaketracker.bootstrap import startup
    from snaketracker.infrastructure.database.engine import create_readonly_sqlite_engine

    root = request.getfixturevalue("tmp_path").resolve()

    class CompositionAdmission:
        def inspection_engine(self, source, role):
            assert source.resolve().is_relative_to(root), "Composition fixture escaped owned data"
            return create_readonly_sqlite_engine(source)

        def admit_mutable(self, source, role):
            assert source.resolve().is_relative_to(root), "Composition fixture escaped owned data"

        def started(self):
            pass

    monkeypatch.setattr(startup, "_admission", CompositionAdmission())


@pytest.fixture
def anyio_backend() -> str:
    return "asyncio"
