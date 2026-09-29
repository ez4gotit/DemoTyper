# Typing

Every character is sent separately with a human-like rhythm. Nothing is pasted.

```yaml
defaults:
  typing:
    profile: normal            # novice | normal | expert | robot
    speed: 0.7                 # overall pace multiplier (>1 faster, <1 slower); 0.7 default
    cps: 9                     # mean characters per second
    jitter: 0.35               # random spread of the delays
    word_pause: [0.05, 0.5]    # extra, varied pause after a space
    punctuation_pause: [0.1, 0.4]
    shifted_slowdown: 1.4      # Shift characters are slower
    think_before: [0.3, 1.2]   # pause before starting a command
    think_long_threshold: 40   # longer commands get a longer pause
    burst: { chance: 0.15, speedup: 1.8, length: [3, 8] }
    reword: { chance: 0.05, hesitation: [0.3, 0.7], min_length: 3 }  # backspace a word, retype
    layout: us                 # us | de | ru | path to a layout file
    typos:
      enabled: true
      rate: 0.03               # chance of a typo per character
      kinds: { neighbour: 0.6, transposition: 0.15, doubled: 0.1, missed: 0.1, case: 0.05 }
      notice_after: [0, 3]     # characters typed before noticing
      hesitation: [0.2, 0.6]   # pause before backspacing
      backspace_cps: 18
      max_per_line: 2
      min_length: 6            # no typos in shorter commands
      protect: []              # characters never mistyped
      seed: null               # a number makes typos the same in every take
```

Settings layer in this order: `defaults.typing`, then the console's `typing`, then the
step's `typing`. At each level a `profile` applies first and that level's own settings
second. From the command line, `--speed 2` halves every delay and pause, `--typos 0.05`
sets the rate, and `--no-typos` turns typos off.

**Overall pace (`speed`).** `speed` is a single multiplier on the whole typing pace: `1.0`
is the raw profile pace, `0.7` (the **default**) is 30 % slower, `2.0` is twice as fast. It
is separate from the CLI `--speed` (they multiply), so you can slow the *scenario's* typing
without changing how the operator scales a run. The `robot` profile pins `speed` to `1.0`
so it stays an exact, deterministic pace.

**Pauses between words.** The pause after each space is a random value in the `word_pause`
range, and the first keystroke of a new word also gets extra timing spread — so the rhythm
clearly varies from word to word, the way a person's does.

**Rewording.** With `reword`, the typist occasionally (5 % of words by default) finishes a
word, pauses, **backspaces the whole word and types it again** — as if second‑guessing it.
Like typos, this only happens where backspacing is safe (a shell command line that is
verified before Enter); it never runs inside a full‑screen program or a `secret`.

| Profile | Speed | Typos |
| --- | --- | --- |
| `novice` | 4 cps, long pauses | 6 %, noticed late |
| `normal` | 9 cps | 3 % |
| `expert` | 16 cps, bursts | 1 %, noticed at once |
| `robot` | 25 cps, no variation | none |

## Typos

A typo looks like a person's: a key next to the intended one (`ngnix`), two keys swapped,
a key pressed twice or missed, or Shift held wrong (`Nginx`). The typist keeps going for a
few characters, pauses as if noticing, backspaces quickly and retypes. The take log lists
every typo with its position, kind, and intended and typed text.

Typos are only made where they can be checked:

- on a shell command line, where the prompt regex matched just before typing;
- in a step that presses Enter, because the line is read back and compared before Enter;
- never in full-screen programs (vim, nano, less), in answers to questions, or in secrets.

Before every Enter the runner reads the command line back from the screen. If it differs
from the intended text for any reason, it fixes the line, and if that fails the step fails
without pressing Enter. After each command, the hidden shell hook reports the command
that actually ran. A mismatch appears in `report.json` under `executed_mismatches`, which
must always be empty.

## Layouts

Neighbour typos follow the keyboard layout: `us` (QWERTY), `de` (QWERTZ) and `ru`
(ЙЦУКЕН). Shift characters mistype to Shift neighbours: `!` next to `@`. Characters that
aren't on the layout (Latin text on `ru`) get the other kinds of typo only. A custom
layout is a YAML file:

```yaml
name: my-layout
rows:  ["`1234567890-=", "qwertyuiop[]\\", "asdfghjkl;'", "zxcvbnm,./"]
shift: ["~!@#$%^&*()_+", "QWERTYUIOP{}|", "ASDFGHJKL:\"", "ZXCVBNM<>?"]
offsets: [0, 0.5, 0.75, 1.25]   # how far each row is shifted, in key widths
```
