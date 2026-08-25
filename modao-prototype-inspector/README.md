# modao-prototype-inspector

中文：给 Codex 一个墨刀分享链接，这个 skill 会自动复用或启动带调试端口的 Chrome，打开原型，扫描左侧页面树，并输出结构化视觉证据。  
English: Give Codex a Modao share link. This skill launches or reuses a debug-enabled Chrome session, opens the prototype, scans the left page tree, and captures structured visual evidence.

## 功能 / What It Does

中文：

- 接收一个墨刀链接作为输入
- 优先复用 `127.0.0.1:9222` 的 Chrome debug 会话
- 若没有可用会话，则自动启动 macOS 上的 Google Chrome Stable
- 扫描墨刀左侧页面树
- 为每个页面输出 `overview` 和 `detail`
- 为页面树切换输出 `interaction`
- 生成 `session.json` 和 `summary.md`

English:

- Accepts a single Modao URL
- Reuses `127.0.0.1:9222` if Chrome is already running in debug mode
- Otherwise launches Google Chrome Stable on macOS with a persistent profile
- Scans page nodes from the Modao left panel
- Captures `overview`, `detail`, and page-tree `interaction` evidence
- Writes `session.json` and `summary.md`

## 当前范围 / Current Scope

中文：

- 平台：macOS
- 浏览器：Google Chrome Stable
- 输入：一个墨刀链接
- 导航范围：仅页面树点击
- 输出：图片证据和会话清单

这一版不会自动点击画布热区，也不会尝试还原完整画布内用户流程。

English:

- Platform: macOS
- Browser: Google Chrome Stable
- Input: one Modao link
- Navigation: page-tree clicks only
- Output: images plus a session manifest

This v1 does not attempt to click canvas hotspots or infer full in-canvas user journeys.

## 依赖 / Dependencies

中文：

- Python 3.11+
- 已安装 Google Chrome Stable，默认路径为 `/Applications/Google Chrome.app`
- Python 包：
  - `requests`
  - `websocket-client`
  - `Pillow`

English:

- Python 3.11+
- Google Chrome Stable installed at `/Applications/Google Chrome.app`
- Python packages:
  - `requests`
  - `websocket-client`
  - `Pillow`

安装依赖 / Install dependencies:

```bash
python3 -m pip install requests websocket-client Pillow
```

## 使用方式 / Usage

中文：直接执行扫描脚本。

English: Run the scanner directly.

```bash
python3 scripts/scan_session.py "https://modao.cc/proto/your-share-link"
```

输出目录 / Artifacts are written under:

```text
deliverables/modao/<timestamp>-<prototype_slug>/
```

典型输出结构 / Typical output structure:

```text
deliverables/modao/<session>/
├── session.json
├── summary.md
├── screens/
└── interactions/
```

## 私有链接与登录 / Private Links And Login

中文：

- 如果链接需要登录，脚本会打开或复用一个持久 profile 的 Chrome
- 第一次运行可能会停在 `login_required` 阻塞截图
- 你在那个 Chrome 窗口里完成墨刀登录后，再次执行脚本即可

English:

- If the link requires login, the scanner opens or reuses Chrome with a persistent profile at `~/.codex/modao-browser-profile`
- The first run may stop with a `login_required` blocking screenshot
- After you complete login in that Chrome window, rerun the command

## 文件结构 / Skill Files

- [SKILL.md](./SKILL.md)
- [workflow.md](./references/workflow.md)
- [evidence-model.md](./references/evidence-model.md)
