# ScenarioPlay console rc file for zsh (see bash_rc.sh for what the hook does).
ZDOTDIR="$HOME"
if [[ -f "$HOME/.zshrc" ]]; then
    source "$HOME/.zshrc"
fi

HISTFILE=@@HISTFILE@@
unsetopt hist_ignore_space hist_ignore_dups hist_ignore_all_dups 2>/dev/null
@@ENV@@
typeset -g __sp_status=@@STATUS@@
typeset -gi __sp_seq=0
__sp_hook() {
    local __sp_ec=$?
    __sp_seq=$(( __sp_seq + 1 ))
    {
        print -r -- "$__sp_seq $__sp_ec"
        fc -ln -1 2>/dev/null
    } >| "$__sp_status"
    return $__sp_ec
}
typeset -ga precmd_functions
precmd_functions=(__sp_hook $precmd_functions)
