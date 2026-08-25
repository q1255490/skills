# Evidence Model

Each captured page is identified by a stable `tree_path`, not by a title alone.

## Node Fields

- `surface`
  - `运营端`
  - `移动端`
  - `游客版`
  - `商家版`
  - `unknown`
- `tree_path`
  - full nested path from the Modao left tree
- `screen_name`
  - last segment of the path
- `state`
  - `default`
  - `modal`
  - `success`
  - `failure`
- `zoom_percent`
  - visible Modao zoom value such as `61%` or `100%`
- `artifacts`
  - `overview`
  - `detail`

## Edge Fields

- `from`
- `to`
- `artifacts`
  - `before`
  - `after`
  - `compare`

## Rules

- `overview` and `detail` must come from the same state.
- `interaction` is only a transition artifact.
- Do not mix different surfaces in one evidence group.
- `success` and `failure` are inferred from the screen name first.
- `modal` is inferred from names containing `提示`, `确认`, `弹窗`, `弹层`, or `弹框`.

