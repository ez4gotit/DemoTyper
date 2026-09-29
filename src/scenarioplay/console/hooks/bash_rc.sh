# ScenarioPlay console rc file. Generated for one take; deleted when the take ends.
# It loads the user's normal ~/.bashrc, then adds a hidden hook that runs before every
# prompt and writes "<seq> <exit code>" plus the last command line to a status file.
# Nothing here is ever typed on screen.

if [ -f "$HOME/.bashrc" ]; then
    . "$HOME/.bashrc"
fi

# Keep the take out of the user's real history, and record every command.
HISTFILE=@@HISTFILE@@
HISTCONTROL=
HISTIGNORE=
@@ENV@@
__sp_status=@@STATUS@@
__sp_seq=0
__sp_hook() {
    local __sp_ec=$?
    __sp_seq=$((__sp_seq + 1))
    {
        printf '%s %s\n' "$__sp_seq" "$__sp_ec"
        HISTTIMEFORMAT= builtin fc -ln -1 2>/dev/null
    } >| "$__sp_status"
    return $__sp_ec
}
if [[ "$(declare -p PROMPT_COMMAND 2>/dev/null)" == "declare -a"* ]]; then
    PROMPT_COMMAND=(__sp_hook "${PROMPT_COMMAND[@]}")
else
    PROMPT_COMMAND="__sp_hook${PROMPT_COMMAND:+;$PROMPT_COMMAND}"
fi
