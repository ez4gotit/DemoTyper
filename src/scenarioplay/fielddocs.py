"""Descriptions of options shared by many steps and conditions. Used by the reference pages
and the JSON Schema (editor tooltips) when a field has no description of its own."""

FIELD_DOCS: dict[str, str] = {
    # common step options
    "console": "Run in this console instead of the current one.",
    "timeout": "Seconds to wait before failing (default: defaults.timeout).",
    "on_fail": "What to do when the step fails: fail, continue, {retry: N, delay: S}, or a "
               "list of recovery steps.",
    "when": "Run the step only if this expression or condition holds.",
    "label": "A name for --from/--to and the log.",
    # input steps
    "wait_for": "After the input, wait for this condition instead of the default.",
    "expect": "Same as wait_for; a plain string is a regex.",
    "typing": "Typing speed and realism for this step (see defaults.typing).",
    "typos": "off turns auto-typos off for this step (on cannot force them where they are "
             "switched off).",
    "check_exit": "Fail the step when the command exits with a non-zero code.",
    "enter": "Press Enter after typing.",
    "repeat": "Press the key this many times.",
    "hidden": "Wait until the terminal hides input (a password prompt) before typing.",
    # conditions
    "interval": "Seconds between checks (default 0.2).",
    "scope": "since_last_input (default): only output after the last input; screen: the "
             "whole visible screen.",
    "on_timeout": "fail (default), continue, retry (wait once more), or a list of steps to run.",
    "as": "Name stored in last.matched when this branch of `any` matches.",
    # blocks
    "steps": "The steps to run.",
    "then": "Steps to run when the condition holds.",
    "else": "Steps to run when no condition holds.",
    "elif": "More branches: a list of {if, then}.",
    "max_iterations": "Upper limit of passes, so a take can never hang (required).",
    "delay": "Seconds to wait between passes.",
    "on_exhausted": "fail (default) or continue when the limit is reached.",
    "params": "Parameter names; `call` gives each a value with `with`.",
    "with": "Values for the block's parameters.",
    "catch": "Steps to run when a step in `try` fails; {{ error.message }} and "
             "{{ error.step }} are set.",
    "finally": "Steps that always run afterwards.",
    "wait": "all: end when every branch is done; any: end when the first is done and stop "
            "the others.",
    "message": "Text for the log and the report.",
    "name": "A name (snapshot name for `vm`).",
    "duration": "Seconds the subtitle stays on screen.",
    "level": "Log level.",
    "zoom": "true: the pane fills the screen; false: back to the layout.",
    "caption": "Subtitle text.",
    "regex": "Regular expression; the first group (or the whole match) is kept.",
    "group": "Which regex group to keep (number or name).",
    "lines": "Keep only the last N lines.",
    "from": "output (since the last input), screen, or last_output (of the last run).",
    "value": "The value; a single {{ expr }} keeps its type (a list stays a list).",
    "cwd": "Directory to run in.",
    "enter_newlines": "Press Enter for each newline in the text.",
}
