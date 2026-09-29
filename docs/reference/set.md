# `set`

*Action.* Set or change a variable: `set: name` with `value:` (templates keep their type, so `value: "{{ packages }}"` stays a list).

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `set` (main) | text | required | Variable name. |
| `value` | anything | - | The value; a single {{ expr }} keeps its type (a list stays a list). |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
- set: site
  value: "{{ env_name }}.example.local"
```

```yaml
- set: packages
  value: "{{ base_packages }}"   # stays a list
```

## Common mistakes

- The value is a template; a bare `x == 1` is text, not an expression.
