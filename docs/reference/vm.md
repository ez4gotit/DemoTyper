# `vm`

*Action.* VMware control mid-take (spec 4.4): `vm: snapshot`, `vm: revert` or `vm: reboot`. `snapshot` takes a snapshot named `name`; `revert` goes back to `name` (default: target.snapshot). After a revert or reboot the runner waits for the guest and rebuilds the consoles. In `steps`, revert and reboot need host-side recording (`target.record: host`), because they would kill a recorder inside the guest.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `vm` (main) | `snapshot` / `revert` / `reboot` | required | snapshot, revert or reboot. |
| `name` | text | - | A name (snapshot name for `vm`). |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
setup:
  - vm: revert
    name: clean
```

```yaml
# target.record: host
- vm: reboot
- run: "uptime"
```

```yaml
- vm: snapshot
  name: after-install
```

## Common mistakes

- With `target.record: guest`, `vm` steps are only allowed in `setup`, because they would kill the recorder inside the guest (spec 4.4).
