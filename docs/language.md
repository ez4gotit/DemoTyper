# Variables, conditions and blocks (phase 2)

This page adds to the [quick start](quickstart.md). The full wiki, with one page per
action and a cookbook, is phase 4.

## Variables

```yaml
vars:
  site: example.local
  packages: [nginx, curl]
steps:
  - run: "sudo apt install -y {{ packages | join(' ') }}"
  - run: "curl -sI http://{{ site }}"
```

Where values come from, lowest priority first:

1. `vars` in the scenario file
2. `--var name=value` on the command line (repeatable). The value is read as YAML, so
   `--var replicas=3` is a number and `--var debug=true` is a boolean.
3. `--vars file.yaml`
4. Values set while the take runs, by `set` or `capture`

`{{ ... }}` works in any text: commands, captions, chapter titles, `expect` patterns and
file paths. Text that is exactly one `{{ expr }}` keeps its type, so
`for_each: "{{ packages }}"` gets a list. Inside other text, `true`/`false` print as words,
null prints as nothing, and a list prints space-separated.

Built-in values:

| Name | Value |
| --- | --- |
| `env.NAME` | Environment variable of the runner |
| `secret.NAME` | A secret (see [passwords](quickstart.md#passwords-sudo-and-others)). Allowed in `exec`, `set`, `assert`, conditions. Refused in typed text, captions, chapters and logs. |
| `take.id`, `take.started_at`, `take.dir` | This take |
| `last.exit_code` | Exit code of the last `run` (needs a bash/zsh console) or `exec` |
| `last.output` | Output of the last `run` (up to its prompt) or `exec` |
| `last.matched` | The `as` name of the `any` branch that matched |
| `loop.index`, `loop.index0`, `loop.first`, `loop.last`, `loop.length`, `loop.item` | Inside loops (`index` starts at 1) |
| `error.message`, `error.step`, `error.line` | Inside `catch` |

Filters: `join(sep)`, `upper`, `lower`, `trim`, `default(value)`, `length`, `int`, `string`.

`validate` warns about variables that are neither declared in `vars` nor set anywhere.
Run it with the same `--var`/`--vars` as the take, and those warnings become errors, as
they are in `run`.

## Conditions

`when`, `if`, `while`, `until` and `assert` take either of two forms.

- **An expression**, as a plain string without `{{ }}`: `mode == 'prod' and replicas > 1`.
  Operators: `== != < <= > >=`, `and or not`, `in`, `not in`, `matches` (regex search),
  parentheses. Values captured from the screen are text: compare them as numbers with
  `count | int > 2`.
- **A screen or system condition**, in the same form as `wait_for`, checked once right
  now: `{regex: "HTTP/1.1 200"}`, `{exec: "systemctl is-active nginx"}`,
  `{file: /etc/nginx/nginx.conf}`, `{port: 80}`, `{any: [...]}`. `idle` needs time, so it
  only works in `wait_for`.

## Wait conditions

| Condition | Holds when |
| --- | --- |
| `prompt: true` | The shell prompt is back |
| `text: "…"` / `regex: "…"` | It appears in the output since the last input |
| `gone: "…"` | It is no longer in that output (a progress bar finished) |
| `idle: 3` | The screen has not changed for 3 s |
| `exec: "cmd"` | The command succeeds, run out of view |
| `file: path` | The file exists |
| `port: 80` or `port: "host:5432"` | The TCP port accepts connections |
| `any: [ … ]` / `all: [ … ]` | One or all of the listed conditions hold. Each may give `as` and `console`. |

Options: `timeout`, `interval`, `scope: screen`, and `on_timeout`. `on_timeout` takes
`fail` (the default), `continue`, `retry` (wait once more) or a list of steps to run.

## Blocks

The keyword takes the block's main value, and the other fields sit beside it.

```yaml
- if: "env_name == 'prod'"
  then: [ ... ]
  elif:
    - if: "env_name == 'staging'"
      then: [ ... ]
  else: [ ... ]

- run: "sudo ufw allow 80"
  when: "enable_firewall"            # makes one step conditional

- for_each: "{{ packages }}"         # or a literal list
  as: pkg                            # default: item
  steps:
    - run: "apt-cache policy {{ pkg }}"

- repeat: 3
  steps: [ ... ]

- while: "count | int < 5"           # checked before each pass
  max_iterations: 10                 # required
  delay: 1
  steps: [ ... ]

- until: { regex: "HTTP/1.1 200" }   # checked after each pass: steps run at least once
  max_iterations: 10
  delay: 3
  on_exhausted: fail                 # or continue
  steps:
    - run: "curl -sI http://localhost"

- retry: 3                           # attempts in total
  delay: 5
  steps: [ ... ]

- try: [ ... ]
  catch:
    - log: "failed at {{ error.step }}: {{ error.message }}"
  finally: [ ... ]

- define: create_user
  params: [name]
  steps:
    - run: "sudo useradd -m {{ name }}"
- call: create_user
  with: { name: alice }

- break: true                        # continue: true; both usually with `when`
  when: "loop.index > 3"
- stop: success                      # or failure; `finally` still runs
  message: "nothing more to show"
- include: common/login.yaml         # that file's steps, spliced in here
```

## Data actions

```yaml
- set: greeting
  value: "hello {{ user }}"
- run: "nginx -v 2>&1"
  capture: { name: version, regex: 'nginx/(\S+)' }   # or capture: name (whole output)
- capture: free_mb                   # from the output since the last input
  regex: 'Mem:\s+\d+\s+\d+\s+(\d+)'
  from: output                       # output | screen | last_output
- assert: "version matches '^1\\.'"
  message: "nginx 1.x is installed"
- exec: "systemctl is-active nginx"  # out of view; sets last.exit_code and last.output
  capture: state
```

## When a step fails

Any step can say what should happen when it fails, with `on_fail`:

```yaml
on_fail: continue                   # note it and carry on
on_fail: { retry: 3, delay: 2 }     # run the step again
on_fail:                            # run recovery steps instead of failing
  - run: "sudo systemctl restart nginx"
```

`defaults.on_fail` sets the policy for every step. On a block, `on_fail` also covers
failures of the steps inside it.
