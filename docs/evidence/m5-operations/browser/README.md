# M5 Browser Workflow Evidence

Result: **Pass**

Source revision: `f976b4622a0f72bd165c906cdc8ab5d72a399cc6`  
Browser: Playwright Chromium against an isolated fresh Docker database.  
Reviewer: Codex local qualification; owner acceptance pending.

The real-browser run completed first household setup, authentication, inventory creation, stock
receipt, animal creation, authorized expense entry, and a fixed-schedule reminder. The reminder
rendered as due with a human-readable explanation. The browser console reported zero errors and
zero warnings. A 390 by 844 viewport had a 390-pixel document width, proving no horizontal
overflow on the reminder workflow.

Retained screenshots:

- [Desktop home](desktop-home.png)
- [Desktop inventory](desktop-inventory.png)
- [Desktop expense detail](desktop-expense-detail.png)
- [Desktop reminders](desktop-reminders.png)
- [Mobile reminders](mobile-reminders.png)

`desktop-expenses.png` retains the required-field validation state that preceded successful entry;
it demonstrates browser-native form validation without a server mutation.

The automated browser regression is reproducible with:

```sh
uv run pytest -q tests/browser/test_operational_workflows.py
```

The isolated browser Compose project was removed after capture. The primary retained local stack
and its database were not altered by this workflow.
