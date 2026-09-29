# From PDF to scenario: a worked example

This page turns a two-page lab handout into a scenario, one decision at a time. The
handout is [examples/lab3/lab3.md](../examples/lab3/lab3.md) (the text of `lab3.pdf`),
and the finished scenario is [examples/lab3/lab3.yaml](../examples/lab3/lab3.yaml).

## 1. Read the PDF for structure

The handout has five numbered tasks, and every task becomes a `chapter`. The "Before you
start" and "Hand-in" parts are not tasks, so they don't appear in the video.

```yaml
steps:
  - chapter: "Task 1: Install nginx"
  - chapter: "Task 2: Start the service"
  - chapter: "Task 3: Publish your own page"
  - chapter: "Task 4: Check the configuration and the log"
  - chapter: "Task 5: Clean up"
```

Run `scenarioplay validate lab3.yaml` after every step on this page. Mistakes come with
line numbers.

## 2. Copy the commands in order

Each command in the PDF becomes a `run` step under its chapter. Copy the command text
exactly as printed:

```yaml
  - chapter: "Task 1: Install nginx"
  - run: "sudo apt-get update"
  - run: "sudo apt-get install -y nginx"
  - run: "nginx -v"
```

Quote every command with double quotes, and escape inner double quotes as `\"`. Commands
with single quotes, such as `echo '<h1>…</h1>'`, need nothing special inside double quotes.

## 3. Decide what each command waits for

Most commands end and give the prompt back, and `run` waits for that on its own. Look for
three exceptions:

- **Slow commands:** `apt-get update` and `install` can take minutes. Give them a
  `timeout`.
- **Commands whose result the PDF names:** "must print `active`", "must say *syntax is
  ok*", "note the status code (404)". Turn each into an `expect`, so the take fails loudly
  if the lab machine behaves differently:

  ```yaml
  - run: "systemctl is-active nginx"
    expect: '^active$'
  - run: "sudo nginx -t"
    expect: "syntax is ok"
  ```

- **Commands that must succeed:** add `check_exit: true` where a failure would make the
  rest of the video meaningless (the install, the service start).

## 4. Passwords

The lab uses `sudo`, so add an answer rule and give the password when running:

```yaml
defaults:
  answers:
    - when: '\[sudo\] password for'
      secret: SUDO_PASS
```

## 5. Make it repeatable

A take must start from the same state every time. `setup` runs before recording, so use it
to undo what the lab does (and `sudo -k` so the password prompt appears in the video):

```yaml
setup:
  - run: "sudo systemctl stop nginx 2>/dev/null; sudo apt-get purge -y -qq nginx nginx-common >/dev/null 2>&1; sudo -k"
    timeout: 300
```

On a VMware guest, `target.snapshot` does this better: every take starts from the snapshot.

## 6. Variables for what changes

The page heading contains the student's name. Make it a variable, so another take can
change it without editing the steps:

```yaml
vars:
  heading: "Lab 3 by student"
steps:
  - run: "echo '<h1>{{ heading }}</h1>' | sudo tee /var/www/html/index.html"
  - run: "curl -s http://localhost"
    expect: "{{ heading }}"
```

```bash
scenarioplay run lab3.yaml --var heading="Lab 3 by Anna"
```

## 7. Pacing for viewers

- `defaults.after_command_pause: 1.2` leaves every output on screen a moment.
- A `pause: 2` after the hand-in command gives time to read the log lines.
- `screenshot: task4-hand-in.png` saves what students must hand in.
- `label: hand-in` lets you rehearse from there: `--from hand-in`.

## 8. Rehearse, then record

```bash
scenarioplay validate examples/lab3/lab3.yaml
scenarioplay run examples/lab3/lab3.yaml --dry-run
SUDO_PASS='…' scenarioplay run examples/lab3/lab3.yaml --no-record --speed 3
SUDO_PASS='…' scenarioplay run examples/lab3/lab3.yaml
```

If a rehearsal fails, the take folder's `take.log` names the step and line, what was
expected, and the last 50 lines of output. `--from "Task 3: Publish your own page"` reruns
only the part being fixed.
