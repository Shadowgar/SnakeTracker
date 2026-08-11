# M5 Authorization Evidence

Result: **Pass**

Source revision: `f976b4622a0f72bd165c906cdc8ab5d72a399cc6`  
Reviewer: Codex local qualification; owner acceptance pending.

Every keeper route rechecks current household membership and capability. Inventory and reminder
operations remain household-scoped; financial records require Owner or Administrator capability;
operational job views do not disclose another household's data. Mutations require CSRF and
expected-version/idempotency inputs. Browser tests cover unauthenticated redirects, CSRF rejection,
stale-role denial, invalid identifiers, and cross-household isolation.

Reproduce:

```sh
uv run pytest -q tests/integration/test_inventory.py tests/integration/test_expenses.py \
  tests/integration/test_reminders.py tests/browser/test_operational_workflows.py
```
