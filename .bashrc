# Auto-activate Python virtual environment when in this project directory
if [ -f "${PWD}/.venv/Scripts/activate" ]; then
    source "${PWD}/.venv/Scripts/activate"
fi

# Add .venv/Scripts to PATH if venv exists
if [ -d "${PWD}/.venv/Scripts" ]; then
    export PATH="${PWD}/.venv/Scripts:$PATH"
    export VIRTUAL_ENV="${PWD}/.venv"
fi