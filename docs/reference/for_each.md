# `for_each`

*Control block.* Repeat the steps for each item of a list (`for_each: [a, b]` or `"{{ var }}"`).

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `for_each` (main) | list of anything or text | required | A list, or "{{ variable }}" holding one. |
| `as` | text | `item` | Name stored in last.matched when this branch of `any` matches. |
| `steps` | list of anything | required | The steps to run. |

Every step also takes the [common options](index.md#common-options). `when` is not allowed on blocks other than `break`, `continue` and `stop`.

## Examples

```yaml
- for_each: "{{ packages }}"
  as: pkg
  steps:
    - run: "apt-cache policy {{ pkg }}"
```

```yaml
- for_each: [web, api]
  steps:
    - run: "systemctl status {{ item }} --no-pager"
```

## Common mistakes

- `for_each: "{{ packages }}"` must be exactly one `{{ }}` so it stays a list.
