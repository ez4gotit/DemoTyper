# Choosing a wait

The runner never guesses how long a command takes. Every step that starts something
waits for an explicit condition, with a timeout.

| Situation | Use |
| --- | --- |
| A command that ends and gives the prompt back | nothing extra: `run` waits for the prompt |
| A question in the middle (`[Y/n]`, `Continue?`) | `expect: '\[Y/n\]'`, then `type: y` with `enter: true` |
| A known line of output (`Serving HTTP`, `active (running)`) | `wait_for: { text: "…" }` |
| Output that varies (`HTTP/1.1 200` or `301`) | `wait_for: { regex: "…" }` |
| A progress bar or spinner that must finish | `wait_for: { gone: "%" }` |
| A program with no prompt and no clear line (`tail -f`, `top`) | `wait_for: { idle: 2 }` |
| Something not on screen: a service, a file, a port | `wait_for: { exec: "systemctl is-active x" }`, `{ file: … }`, `{ port: 80 }` |
| One of several outcomes | `wait_for: { any: [ … ] }` then `if: "last.matched == '…'"` |
| A password prompt | an [answer rule](quickstart.md#passwords-sudo-and-others), not a wait |

`text`, `regex` and `gone` look only at output since the last input, so the typed command
never matches. Add `scope: screen` to look at the whole visible screen.

Only use `pause` to give viewers time to read, never to wait for a command.

## The prompt regex

`run` knows a command has finished when:

1. the hidden shell hook reports that the shell printed a new prompt (bash and zsh
   consoles on the target machine), and
2. the last non-empty line on screen matches the prompt regex.

On consoles on another machine (`host:`) and in `sh` consoles there's no hook, so only the
regex counts.

The default `[$#%>] ?$` matches prompts ending in `$`, `#`, `%` or `>`. Set
`defaults.prompt`, or `prompt` on a console, for anything else:

| Shell and prompt | Regex |
| --- | --- |
| bash default: `user@host:~$ ` | `\$ $` or the default |
| root: `root@host:~# ` | `# $` or the default |
| zsh default: `host% ` | `% $` or the default |
| oh-my-zsh robbyrussell: `➜  dir git:(main) ✗ ` | `➜ .*$` |
| starship / powerline, ending in `❯` | `❯ ?$` |
| fish: `user@host ~> ` | `> $` or the default |
| a two-line prompt whose second line is `$ ` | `^\$ $` |

When the take starts, the runner waits for the first prompt. If the regex doesn't match,
the take stops right away (exit code 3) and prints the prompt line it saw, so the fix is
quick.

## Timeouts

A wait takes the first of: `timeout` on the condition, `timeout` on the step, then
`defaults.timeout` (60 s). Long installs need a bigger one on that step:

```yaml
- run: "sudo apt-get install -y texlive-full"
  timeout: 1800
```

`on_timeout` on a condition can `continue`, `retry` (wait once more), or run steps.
