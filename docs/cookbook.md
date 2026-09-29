# Cookbook

## sudo passwords

```yaml
defaults:
  answers:
    - when: '\[sudo\] password for'
      secret: SUDO_PASS
setup:
  - run: "sudo -k"      # forget cached credentials, so the prompt shows in the video
steps:
  - run: "sudo apt-get update"
```

```bash
SUDO_PASS='…' scenarioplay run lab.yaml
```

The password is typed only into the hidden prompt. If sudo asks again (a wrong password),
the step fails straight away. On lab VMs where the prompt doesn't need to be seen,
`NOPASSWD` in the snapshot's sudoers is simpler still.

## `[Y/n]` and other questions

Answer every time the question appears:

```yaml
defaults:
  answers:
    - when: 'Do you want to continue\? \[Y/n\]'
      text: "y"
```

Or explicitly, where it matters for the viewer:

```yaml
- run: "sudo apt install nginx"
  expect: '\[Y/n\]'
- pause: 1
- type: "y"
  enter: true
  wait_for: { prompt: true, timeout: 600 }
```

## Editing a file in nano

```yaml
- type: "nano /etc/hosts"
  enter: true
  wait_for: { text: "GNU nano", scope: screen }
- key: M-/                    # go to the end
- type: "10.0.0.5  lab.local"
- key: C-o                    # save
- key: Enter
- key: C-x                    # exit
  wait_for: { prompt: true }
```

Typos are switched off automatically inside nano.

## Editing a file in vim

```yaml
- type: "vim app.conf"
  enter: true
  wait_for: { idle: 1 }
- type: "Go"                  # new line at the end, insert mode
- type: "port = 8080"
- key: Escape
- type: ":wq"
- key: Enter
  wait_for: { prompt: true }
```

## Long installs

```yaml
- run: "sudo apt-get install -y build-essential"
  timeout: 1800
```

To keep the video short:

```yaml
- record: pause
- run: "sudo apt-get dist-upgrade -y"
  timeout: 3600
- record: resume              # adds a "(14 min 03 s skipped)" subtitle
```

## Several videos from one take

`record: stop` ends the current video file and `record: start` begins a new one. With
`autostart: false`, recording begins only at the first `record: start`:

```yaml
target:
  recorder: { autostart: false }
steps:
  - run: "git clone https://example.com/lab.git && cd lab"   # preparation, not recorded
  - record: start
    clip: build
  - chapter: "Build"
  - run: "make"
  - record: stop
  - run: "make test > /dev/null"                               # not recorded
  - record: start
    clip: results
  - chapter: "Results"
  - run: "cat results.txt"
```

The take folder then has `clips/01-build.mp4` and `clips/02-results.mp4`, each with its
own `.chapters.txt` and `.srt`. `report.json` lists the clips, and each step has a `clip`
number. A take with a single clip still writes `video.mp4`, as usual.

## Screenshots for a handout

```yaml
defaults:
  screenshots:
    chapters: end        # a PNG at the end of every chapter: 01-<chapter>-end.png, ...
    text: true           # plus the console text, as .html (with colours) and .txt
steps:
  - chapter: "Task 4: The access log"
  - run: "sudo tail -n 5 /var/log/nginx/access.log"
    console: logs
  - screenshot:          # just that console, cropped to its pane
      file: task4-log.png
      console: logs
```

Screenshots also work while recording is stopped, and with `--no-record`. A headless take
has no screen, so it saves the text only.

## A service that must be ready

```yaml
- run: "sudo systemctl start app"
- wait_for: { exec: "systemctl is-active app", timeout: 60 }
- wait_for: { port: 8080, timeout: 60 }
- until: { regex: "HTTP/1.1 200" }
  max_iterations: 10
  delay: 3
  steps:
    - run: "curl -sI http://localhost:8080"
```

## `tail -f` and other commands that never return

```yaml
- type: "tail -f /var/log/nginx/access.log"
  enter: true
  console: logs
  wait_for: { idle: 1 }
- run: "curl -s localhost > /dev/null"
  console: client
- wait_for: { text: "GET / HTTP", console: logs }
- key: C-c
  console: logs
  wait_for: { prompt: true }
```

## SSH to a second machine

Visibly, as part of the lesson:

```yaml
- type: "ssh student@10.0.0.20"
  enter: true
  expect: 'student@lab2'      # the remote prompt
```

Or as a console that is already on that machine:

```yaml
consoles:
  - { name: main }
  - { name: lab2, host: 10.0.0.20, ssh: { user: student, key: ~/.ssh/lab } }
```

## Multi-console demos

```yaml
layout: grid
consoles:
  - { name: server, title: "Server" }
  - { name: client, title: "Client" }
  - { name: logs, title: "Access log" }
steps:
  - parallel:
      - console: server
        steps:
          - type: "python3 -u -m http.server 8080 2>&1 | tee access.log"
            enter: true
            wait_for: { text: "Serving HTTP" }
      - console: logs
        steps:
          - type: "tail -f access.log"
            enter: true
            wait_for: { idle: 1 }
  - run: "curl -s localhost:8080 > /dev/null"
    console: client
  - focus: logs
    zoom: true
  - pause: 2
  - focus: logs
    zoom: false
```

See `examples/multi-console.yaml` for the full demo.

## Repeating a step for a list

```yaml
vars:
  users: [alice, bob, carol]
steps:
  - for_each: "{{ users }}"
    as: u
    steps:
      - run: "sudo useradd -m {{ u }}"
```

## Different takes from one scenario

```yaml
- if: "env_name == 'prod'"
  then: [ ... ]
  else: [ ... ]
```

```bash
scenarioplay run lab.yaml --var env_name=prod
scenarioplay run lab.yaml --vars prod.yaml
```
