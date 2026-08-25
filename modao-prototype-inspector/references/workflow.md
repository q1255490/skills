# Workflow

## Entry

The user provides a single Modao URL.

## Runtime

1. Attempt to connect to Chrome remote debugging at `127.0.0.1:9222`.
2. If unavailable, launch Google Chrome Stable with:
   - remote debugging enabled
   - persistent profile at `~/.codex/modao-browser-profile`
3. Reuse an existing Modao tab if it already matches the target URL.
4. Otherwise create a new Chrome target for the URL.

## Modao readiness

The scanner waits for:

- `.rn-content-body`
- a tree root `ul` under the left panel

If those selectors never appear and the page looks like a login wall, the run stops and records a blocking screenshot.

## Tree traversal

The scanner reads the left page tree from the DOM instead of guessing via screenshots.

- `folder` nodes only contribute to ancestry
- `page` nodes become scan targets
- `tree_path` is built from nested page and folder labels

Traversal order is DOM order.

## Capture rules

For each page node:

- capture `overview.png`
- derive `detail.png` from the same screenshot using the largest visible canvas rect

For each page-to-page transition:

- copy the previous page `overview` as `before.png`
- copy the current page `overview` as `after.png`
- generate `compare.png`

## Output

Each session writes:

- `session.json`
- `summary.md`
- `screens/*`
- `interactions/*`

