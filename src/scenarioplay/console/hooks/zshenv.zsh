# ScenarioPlay: zsh reads this because ZDOTDIR points here. Load the user's own file.
if [[ -f "$HOME/.zshenv" ]]; then
    source "$HOME/.zshenv"
fi
