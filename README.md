# ScenarioPlay

Plays a human-written YAML scenario on a Linux machine: types every command character by
character into real terminals (tmux panes), presses Enter, waits for the result, and records
the whole screen to video with chapters, subtitles and a log.

- Specification: *Technical Specification: Scenario Typing Runner (ScenarioPlay)*
- Plan: [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md)
- Status: **phases 1–4** built:
  - **Local and VMware targets**, with X11, Wayland (wf-recorder) and host-side recording.
  - **The scenario language:** variables, conditions, loops, retries, try/catch,
    define/call, include, set/capture/assert/exec.
  - **Typing:** realistic typing with auto-typos; secrets and automatic answers.
  - **Consoles:** split, grid or tab layouts, `parallel`, remote consoles over ssh.
  - **Run modes:** `--step`, `--from`/`--to`, `--cast`, `--burn-subtitles`, `soak`.

  Open items are in [IMPLEMENTATION_PLAN.md](IMPLEMENTATION_PLAN.md) §6.7.
- Wiki: [docs/index.md](docs/index.md) (`mkdocs serve` to browse it)

## Install

On the Linux machine that runs the scenario:

```bash
sudo apt install tmux ffmpeg xterm        # xterm, or alacritty/kitty/gnome-terminal
pipx install .                            # or: pip install -e '.[dev]' in a venv
scenarioplay doctor
```

## Use

```bash
scenarioplay validate examples/nginx-install.yaml
scenarioplay run examples/nginx-install.yaml --dry-run
scenarioplay run examples/nginx-install.yaml --no-record   # rehearsal, window only
scenarioplay run examples/nginx-install.yaml               # records a take
scenarioplay schema > schema/scenarioplay.schema.json
```

Each take writes a folder under `takes/`: `video.mp4`, `chapters.txt`, `subtitles.srt`,
`take.log`, `report.json`, `transcript/<console>.txt`, `screenshots/`,
`scenario.resolved.yaml`.

Exit codes: 0 success, 1 validation error, 2 step failure, 3 environment error,
130 interrupted.

## A scenario

```yaml
version: 1
meta: { title: "Lab 3 - Nginx setup" }
defaults:
  typing: { profile: normal }
steps:
  - chapter: "Task 1: Install nginx"
  - run: "sudo apt install -y nginx"
    timeout: 600
  - run: "systemctl status nginx --no-pager"
    expect: "active \\(running\\)"
```

## Editor support

Point the VS Code YAML extension at the schema:

```json
"yaml.schemas": { "./schema/scenarioplay.schema.json": ["scenarios/**/*.yaml", "examples/*.yaml"] }
```

## Development

Tests need Linux with tmux and bash (WSL2 works):

```bash
pip install -e '.[dev]'
pytest                       # unit + integration (integration skips without tmux)
pytest -m "not integration"  # unit only
```
