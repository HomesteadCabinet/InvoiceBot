#!/usr/bin/env bash

# Pyenv-virtualenv configuration for Invoiceinator.
PYTHON_VERSION="3.12.9"
VENV_NAME="invoiceinator"
PYENV_ROOT="${PYENV_ROOT:-$HOME/.pyenv}"
VENV_PREFIX="$PYENV_ROOT/versions/$PYTHON_VERSION/envs/$VENV_NAME"
PYENV_BIN="$PYENV_ROOT/bin/pyenv"

show_usage() {
    echo "Usage: $1 [service_name]"
    echo "Available services:"
    echo "  django   - Run Django server on 0.0.0.0:9999"
    echo "  vue      - Run Vue frontend development server"
    echo "  static   - Collect Django static files"
    echo "  all      - Run both Django and Vue services"
    echo "  activate - Just activate the django virtual environment"
}

# Ensure pyenv is on PATH and pyenv-virtualenv is initialized in this shell.
bootstrap_pyenv() {
    if [ -x "$PYENV_BIN" ]; then
        case ":$PATH:" in
            *":$PYENV_ROOT/bin:"*) ;;
            *) export PATH="$PYENV_ROOT/bin:$PATH" ;;
        esac
    fi

    if ! command -v pyenv >/dev/null 2>&1; then
        echo "Error: pyenv not found. Expected at $PYENV_BIN" >&2
        return 1
    fi

    eval "$(pyenv init -)" >/dev/null 2>&1 || true
    eval "$(pyenv virtualenv-init -)" >/dev/null 2>&1 || true
    return 0
}

# Create the pyenv virtualenv if it doesn't exist yet.
ensure_venv() {
    bootstrap_pyenv || return 1

    if [ -d "$VENV_PREFIX" ]; then
        return 0
    fi

    if ! pyenv versions --bare | grep -qx "$PYTHON_VERSION"; then
        echo "Python $PYTHON_VERSION is not installed in pyenv."
        echo "Install it with: pyenv install $PYTHON_VERSION"
        return 1
    fi

    echo "Creating pyenv virtualenv '$VENV_NAME' from Python $PYTHON_VERSION..."
    pyenv virtualenv "$PYTHON_VERSION" "$VENV_NAME" || return 1
}

activate_venv() {
    ensure_venv || return 1

    if [ ! -f "$VENV_PREFIX/bin/activate" ]; then
        echo "Error: virtualenv activate script not found at $VENV_PREFIX/bin/activate" >&2
        return 1
    fi

    # shellcheck disable=SC1091
    . "$VENV_PREFIX/bin/activate"
    export PYENV_VERSION="$VENV_NAME"
    return 0
}

# Install/refresh requirements only when requirements.txt content changes.
install_requirements_if_needed() {
    local req_file="$1"
    [ -f "$req_file" ] || return 0

    local marker="$VENV_PREFIX/.requirements.sha256"
    local current_hash
    current_hash=$(sha256sum "$req_file" | awk '{print $1}')

    if [ -f "$marker" ] && [ "$(cat "$marker")" = "$current_hash" ]; then
        return 0
    fi

    echo "Installing Python dependencies from $req_file..."
    python -m pip install --upgrade pip >/dev/null
    pip install -r "$req_file" || return 1
    echo "$current_hash" > "$marker"
}

run_django() {
    echo "Starting Django server..."
    activate_venv || exit 1
    script_dir=$(dirname "$(realpath "$0")")
    install_requirements_if_needed "$script_dir/invoiceinator/requirements.txt" || exit 1
    cd "$script_dir/invoiceinator" || exit 1
    python manage.py runserver 0.0.0.0:9999
}

run_vue() {
    echo "Starting Vue development server..."
    script_dir=$(dirname "$(realpath "$0")")
    cd "$script_dir/invoice-frontend" || exit 1
    npm run dev
}

run_static() {
    echo "Collecting static files..."
    activate_venv || exit 1
    script_dir=$(dirname "$(realpath "$0")")
    install_requirements_if_needed "$script_dir/invoiceinator/requirements.txt" || exit 1
    cd "$script_dir/invoiceinator" || exit 1
    python manage.py collectstatic --noinput
}

if [ $# -eq 0 ]; then
    show_usage "$0"
    exit 1
fi

case "$1" in
    django)
        run_django
        ;;
    vue)
        run_vue
        ;;
    static)
        run_static
        ;;
    activate)
        echo "Activating Django virtual environment ($VENV_NAME)..."
        activate_venv || exit 1
        echo "Virtual environment activated. You can now run Django commands directly."

        current_shell=$(basename "$SHELL")
        case "$current_shell" in
            zsh)
                exec zsh
                ;;
            bash)
                exec bash
                ;;
            *)
                exec "$SHELL"
                ;;
        esac
        ;;
    all)
        script_dir=$(dirname "$(realpath "$0")")

        (
            activate_venv || exit 1
            install_requirements_if_needed "$script_dir/invoiceinator/requirements.txt" || exit 1
            cd "$script_dir/invoiceinator" || exit 1
            python manage.py runserver 0.0.0.0:9999
        ) &
        django_pid=$!

        (
            cd "$script_dir/invoice-frontend" || exit 1
            npm run dev
        ) &
        vue_pid=$!

        wait $django_pid
        wait $vue_pid
        ;;
    *)
        echo "Unknown service: $1"
        show_usage "$0"
        exit 1
        ;;
esac
