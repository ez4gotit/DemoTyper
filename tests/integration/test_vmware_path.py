"""The vmware target end to end, without VMware: a stand-in `vmrun` and a real SSH server
(asyncssh, in this process) that runs commands on this machine. Everything after "the VM
is up" is the real code path: SSH transport, tmux over SSH, the guest-side recorder
plumbing, `vm: reboot` with console rebuild."""

from __future__ import annotations

import asyncio
import os
import shutil

import asyncssh
import pytest

from scenarioplay.engine.context import RunOptions
from scenarioplay.engine.take import run_take
from scenarioplay.exitcodes import ExitCode
from scenarioplay.loader import load_scenario
from scenarioplay.transport.ssh import SSHTransport

from .conftest import Result

pytestmark = pytest.mark.integration

FAKE_VMRUN = """#!/bin/bash
# Stand-in for vmrun: logs the call; the "guest" is this machine.
echo "$@" >> "{log}"
case "$3" in
  getGuestIPAddress) echo 127.0.0.1 ;;
  list) echo "Total running VMs: 1"; echo "$(cat {vmx_path_file})" ;;
  listSnapshots) echo "Total snapshots: 1"; echo clean ;;
esac
exit 0
"""


class _Server(asyncssh.SSHServer):
    def begin_auth(self, username: str) -> bool:
        return False  # test server: no authentication


async def _handle(process: asyncssh.SSHServerProcess) -> None:
    """Run the command locally, pumping stdin/stdout/stderr through the channel."""
    local = await asyncio.create_subprocess_shell(
        process.command, stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE)

    async def pump_in() -> None:
        try:
            while data := await process.stdin.read(65536):
                local.stdin.write(data)
                await local.stdin.drain()
        except (asyncssh.Error, ConnectionError, BrokenPipeError):
            pass
        finally:
            local.stdin.close()

    async def pump_out(source, sink) -> None:
        while data := await source.read(65536):
            sink.write(data)

    feeder = asyncio.create_task(pump_in())
    await asyncio.gather(pump_out(local.stdout, process.stdout),
                         pump_out(local.stderr, process.stderr))
    code = await local.wait()
    feeder.cancel()
    await asyncio.gather(feeder, return_exceptions=True)
    process.exit(code)


@pytest.fixture
async def ssh_server(tmp_path):
    key = asyncssh.generate_private_key("ssh-ed25519")
    server = await asyncssh.create_server(
        _Server, "127.0.0.1", 0, server_host_keys=[key], process_factory=_handle,
        sftp_factory=True, encoding=None)
    port = server.sockets[0].getsockname()[1]
    yield port
    server.close()
    await server.wait_closed()


@pytest.fixture
def fake_vmrun(tmp_path, monkeypatch):
    log = tmp_path / "vmrun.log"
    vmx = tmp_path / "lab.vmx"
    vmx.write_text('displayName = "Lab VM"\n')
    vmx_path_file = tmp_path / "vmx-path"
    vmx_path_file.write_text(str(vmx))
    script = tmp_path / "vmrun"
    script.write_text(FAKE_VMRUN.format(log=log, vmx_path_file=vmx_path_file))
    script.chmod(0o755)
    monkeypatch.setenv("SCENARIOPLAY_VMRUN", str(script))
    return vmx, log


async def test_ssh_transport_basics(ssh_server, tmp_path):
    t = SSHTransport("127.0.0.1", port=ssh_server, user=os.environ.get("USER", "u"),
                     known_hosts=None)
    await t.connect()
    try:
        res = await t.run(["sh", "-c", "echo out; echo err >&2; exit 3"], env={"X": "1"})
        assert (res.rc, res.out, res.err) == (3, "out\n", "err\n")
        path = str(tmp_path / "remote.txt")
        await t.write_file(path, "héllo\n")
        assert await t.read_file(path) == "héllo\n" and await t.exists(path)
        await t.fetch(path, str(tmp_path / "local.txt"))
        assert (tmp_path / "local.txt").read_text() == "héllo\n"
        proc = await t.start(["sh", "-c", "read line; echo got-$line"])
        await proc.write(b"ping\n")
        await proc.close_stdin()
        assert await proc.readline() == b"got-ping\n"
        assert await proc.wait() == 0
        assert t.expand_user("~/x") == os.path.expanduser("~/x")
    finally:
        await t.close()


def _display() -> str:
    return os.environ.get("DISPLAY") or ":0"


@pytest.mark.skipif(not os.path.exists(f"/tmp/.X11-unix/X{_display().lstrip(':')}"),
                    reason="needs an X server socket (the guest desktop check)")
async def test_vmware_take_over_ssh_with_reboot(ssh_server, fake_vmrun, tmp_path,
                                                write_scenario, monkeypatch):
    vmx, log = fake_vmrun
    monkeypatch.setenv("SP_GUEST_PASS", "g-pass-1")
    path = write_scenario(f"""
target:
  kind: vmware
  vmx: "{vmx}"
  snapshot: clean
  record: host
  boot_timeout: 60
  recorder: {{display: "{_display()}"}}
  ssh: {{host: auto, port: {ssh_server}, user: "{os.environ.get('USER', 'u')}",
         known_hosts: none}}
defaults:
  typing: {{profile: robot}}
  after_command_pause: 0
  answers:
    - when: 'Guest password: $'
      secret: SP_GUEST_PASS
steps:
  - run: "echo in-guest-$((6*7))"
    expect: '^in-guest-42$'
  - run: "read -r -s -p 'Guest password: ' pw; echo; echo len=${{#pw}}"
    expect: '^len=8$'
  - vm: reboot
  - run: "echo after-reboot"
  - exec: "echo out-of-view"
    capture: seen
  - assert: "seen == 'out-of-view'"
""")
    parsed, problems = load_scenario(path)
    assert parsed is not None, [p.format() for p in problems]
    out = tmp_path / "takes"
    code = await run_take(parsed, RunOptions(record=False, headless=True, out_dir=out,
                                             speed=4))
    r = Result(code, out)
    assert code == ExitCode.OK, r.log
    calls = log.read_text()
    assert "revertToSnapshot" in calls and "getGuestIPAddress" in calls
    assert "reset" in calls  # vm: reboot
    assert "in-guest-42" in r.transcript and "after-reboot" in r.transcript
    assert "consoles rebuilt: main" in r.log
    for f in r.dir.rglob("*"):
        if f.is_file():
            assert b"g-pass-1" not in f.read_bytes()
    assert shutil.which("tmux")
