#!/usr/bin/env sh

# Function to display usage information
show_usage() {
    echo "Usage: $1 [service_name]"
    echo "Available services:"
    echo "  django   - Run Django server on 0.0.0.0:8888"
    echo "  vue      - Run Vue frontend development server"
    echo "  static   - Collect Django static files"
    echo "  all      - Run both Django and Vue services"
    echo "  activate - Just activate the django virtual environment"
}

# Function to activate the virtual environment
activate_venv() {
    # echo "DEBUG: Attempting to activate virtual environment..."
    local venv_path="invoiceinator/.venv/bin/activate"
    # echo "DEBUG: First trying path: $venv_path"
    if [ -f "$venv_path" ]; then
        # echo "DEBUG: Found venv at parent directory"
        . "$venv_path"
    else
        # echo "DEBUG: Not found in parent directory"
        venv_path="$(pwd)/.venv/bin/activate"
        # echo "DEBUG: Now trying path: $venv_path"
        if [ -f "$venv_path" ]; then
            # echo "DEBUG: Found venv in current directory"
            . "$venv_path"
        else
            # echo "DEBUG: Virtual environment not found in either location"
            echo "Warning: Virtual environment not found at $venv_path"
            return 1
        fi
    fi
    # echo "DEBUG: Virtual environment activated successfully"
    return 0
}

# Function to run Django service
run_django() {
    echo "Starting Django server..."
    activate_venv
    cd invoiceinator
    python manage.py runserver
}

# Function to run Vue service
run_vue() {
    echo "Starting Vue development server..."
    cd invoice-frontend
    npm run dev
}

# Function to collect static files
run_static() {
    echo "Collecting static files..."
    cd invoiceinator
    activate_venv
    python manage.py collectstatic --noinput
}

# Check if a service name was provided
if [ $# -eq 0 ]; then
    show_usage "$0"
    exit 1
fi

# Run the requested service
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
        echo "Activating Django virtual environment..."
        # Detect the current shell
        current_shell=$(basename "$SHELL")

        # Source the virtual environment
        activate_venv

        echo "Virtual environment activated. You can now run Django commands directly."
        # Start an interactive shell based on the user's default shell
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
        # Run both services in background processes
        # For Django
        script_dir=$(dirname "$(realpath "$0")")

        (
            cd "$script_dir/invoiceinator"
            if [ -f "$script_dir/.venv/bin/activate" ]; then
                . "$script_dir/.venv/bin/activate"
            else
                echo "Warning: Virtual environment not found at $script_dir/.venv"
            fi
            python manage.py runserver 0.0.0.0:8888
        ) &
        django_pid=$!

        # For Vue
        (
            cd "$script_dir/invoice-frontend"
            npm run dev
        ) &
        vue_pid=$!

        # Wait for both processes
        wait $django_pid
        wait $vue_pid
        ;;
    *)
        echo "Unknown service: $1"
        show_usage "$0"
        exit 1
        ;;
esac
