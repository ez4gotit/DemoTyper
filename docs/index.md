# ScenarioPlay

ScenarioPlay plays a YAML scenario on a Linux machine, locally or in a VMware guest. It
types every command character by character into real terminals, waits for each result,
and records the screen. The output is a video with chapters, subtitles, a log, a report
and transcripts.

The wiki is written for scenario authors; you don't need the source code.

1. [Quick start](quickstart.md): from a lab task to a finished video.
2. [File structure](file-structure.md): every top-level key.
3. [Reference](reference/index.md): every action and control block, with options,
   defaults, examples and common mistakes.
4. [Choosing a wait](waiting.md): `prompt`, `text`, `regex`, `idle`, `exec`, and the
   prompt regex for common shells.
5. [Cookbook](cookbook.md): sudo, `[Y/n]`, nano and vim, long installs, services, `tail -f`,
   SSH, multi-console demos.
6. [From PDF to scenario](from-pdf.md): a worked example.
7. [Troubleshooting](troubleshooting.md).
8. [Cheat sheet](cheatsheet.md): all the syntax on one page.

More: [variables, conditions, blocks and consoles](language.md), [typing and
typos](typing.md), [setting up the guest and the VMware host](setup.md).

Examples in `examples/`:

- **One console:** `hello-shell.yaml`, `nginx-install.yaml`, `lab3/lab3.yaml`.
- **Several consoles:** `multi-console.yaml`.
- **Loops and conditions:** `loops-and-conditions.yaml`.
- **VMware with snapshot reset:** `vmware-lab.yaml`.
