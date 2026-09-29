# `paste`

*Action.* Instantly insert a substring at the cursor (a pseudo-paste) instead of typing it character by character - handy for long, boring tokens (a base64 blob, a long path). `paste: "text"` inserts literal text (templates allowed); `paste: {buffer: name}` inserts a named buffer from `defaults.buffers`. It is character-safe and does not use the OS clipboard or bracketed paste - the characters are just sent in one burst.

## Options

| Option | Type | Default | Description |
| --- | --- | --- | --- |
| `wait_for` | mapping or text | - | After the input, wait for this condition instead of the default. |
| `expect` | mapping or text | - | Same as wait_for; a plain string is a regex. |
| `paste` (main) | text or mapping | required | Text to insert instantly, or {buffer: name}. |
| `enter` | true/false | `false` | Press Enter after typing. |

Every step also takes the [common options](index.md#common-options).

## Examples

```yaml
# a long token typed instantly instead of character by character
- type: "echo "
- paste: "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"
  enter: true
```

```yaml
# pubkey is defined once under defaults.buffers
- type: "echo '"
- paste: { buffer: pubkey }
- type: "' >> ~/.ssh/authorized_keys"
  enter: true
```

## Common mistakes

- `paste` inserts the characters in one burst (a pseudo-paste); it is not the OS clipboard or bracketed paste, and does not bypass the shell.
- A buffer must be defined under `defaults.buffers`; `paste: {buffer: name}` fails validation otherwise.
- To paste a captured value, use a template: `paste: "{{ my_capture }}"`.
