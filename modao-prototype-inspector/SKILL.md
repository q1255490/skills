---
name: modao-prototype-inspector
description: Inspect a Modao prototype from a single share link, launch or reuse debug Chrome automatically, scan the page tree, and capture overview, detail, and interaction evidence with a structured session manifest.
---

# Modao Prototype Inspector

Use this skill when the user wants Codex to inspect a Modao prototype directly from a share link.

## Input Contract

- Required: one Modao URL
- Optional natural-language constraints:
  - focus on a specific surface such as `运营端` or `移动端`
  - focus on a specific flow such as `预约订座`
  - disable automatic page switching

## Workflow

1. Reuse `http://127.0.0.1:9222` if a debug Chrome session already exists.
2. Otherwise launch Google Chrome Stable on macOS with a persistent profile at `~/.codex/modao-browser-profile`.
3. Open the provided Modao link in Chrome.
4. Wait for Modao to load the page tree.
5. If the page is blocked by login or permission walls, save a blocking screenshot and stop.
6. Read the full page tree from the left panel DOM.
7. Traverse page nodes in tree order.
8. For each page node, capture:
   - `overview.png`
   - `detail.png`
9. For each page-tree transition, capture:
   - `before.png`
   - `after.png`
   - `compare.png`
10. Write `session.json` and `summary.md`.

## Evidence Rules

- `overview` and `detail` must be derived from the same state.
- `interaction` is only for page-tree transitions.
- Never mix `运营端` and `移动端` screens in the same evidence group.
- Use `tree_path` as the node identity, not the page title alone.

## Blocking Rules

- If the skill detects a login wall, do not continue scanning.
- Keep the Chrome window open so the user can complete login manually.
- On the next run, reuse the same persistent profile.

## References

- Workflow details: `references/workflow.md`
- Evidence model and identity fields: `references/evidence-model.md`

## Scripts

- `scripts/scan_session.py`
- `scripts/chrome_runtime.py`
- `scripts/modao_adapter.py`
- `scripts/capture_engine.py`

