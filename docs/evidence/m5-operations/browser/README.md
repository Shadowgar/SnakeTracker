# M5 Browser Workflow Evidence

Result: **Pass**

Source revision: `e1a15025b4b5caa81391866d49c1b5a050f616be`
Browser: Playwright Chromium against an isolated fresh Docker database.
Reviewer: Codex final qualification; owner accepted August 11, 2026.

The original real-browser run completed first household setup, authentication, inventory creation,
stock receipt, animal creation, and authorized expense entry. The corrected reminder-UX run used a
fresh isolated Docker database, recorded an accepted feeding, configured a seven-day feeding
schedule from the animal profile, and verified the resulting upcoming agenda item. The normal
agenda exposed neither an Add Reminder action nor rule-disable administration. The browser console
reported zero errors and zero warnings. Both the animal schedule and agenda had a 390-pixel
document width at a 390 by 844 viewport, proving no horizontal overflow.

Retained screenshots:

- [Desktop home](desktop-home.png)
- [Desktop inventory](desktop-inventory.png)
- [Desktop expense validation](desktop-expenses.png)
- [Desktop expense detail](desktop-expense-detail.png)
- [Desktop animal care schedule](desktop-animal-care-schedule.png)
- [Desktop reminders](desktop-reminders.png)
- [Mobile animal care schedule](mobile-animal-care-schedule.png)
- [Mobile reminders](mobile-reminders.png)

`desktop-expenses.png` retains the required-field validation state that preceded successful entry;
it demonstrates browser-native form validation without a server mutation.

The automated browser regression is reproducible with:

```sh
uv run pytest -q tests/browser/test_operational_workflows.py
```

The isolated browser Compose project was removed after capture. The primary retained local stack
and its database were not altered by this workflow.
