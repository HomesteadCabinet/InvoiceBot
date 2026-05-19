# Invoiceinator

Invoiceinator is a full-stack invoice ingestion and review app. The backend is a Django API that parses invoice PDFs, syncs email/vendor data, and exposes admin/API endpoints. The frontend is a Quasar/Vite app for browsing and working with processed invoices.

## Project Layout

- `invoiceinator/`: Django backend, invoice parsers, tests, and API endpoints
- `invoice-frontend/`: Quasar frontend for the user interface
- `run.sh`: convenience script for local development and service startup

## Development Setup

This repository uses `pyenv` and `pyenv-virtualenv` for the Python backend environment.

### Prerequisites

- `pyenv`
- `pyenv-virtualenv`
- Python `3.12.9`
- Node.js and npm for the frontend

### Python Environment

From the repository root:

```bash
pyenv install 3.12.9
pyenv virtualenv 3.12.9 invoiceinator
pyenv local invoiceinator
```

The checked-in `.python-version` file is set to `invoiceinator`, so `pyenv` will automatically select that virtualenv when you enter the repo.

### Backend Dependencies

```bash
cd invoiceinator
pip install -r requirements.txt
```

### Run Locally

You can start the services individually or together:

```bash
./run.sh django   # Django API on 0.0.0.0:9999
./run.sh vue      # Quasar frontend dev server
./run.sh all      # Start both services
```

### Systemd User Services

The repository includes user-level systemd units under `systemd/user/` for running the Django and Vue debug servers.

Install them into your user session:

```bash
mkdir -p ~/.config/systemd/user
cp systemd/user/*.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now invoiceinator-django.service invoiceinator-vue.service
```

View logs with:

```bash
journalctl --user -u invoiceinator-django.service -f
journalctl --user -u invoiceinator-vue.service -f
```

### Notes

- The Django backend uses the `invoiceinator` virtualenv created by `pyenv-virtualenv`.
- If Python `3.12.9` is not installed yet, `run.sh` will prompt you to install it with `pyenv install 3.12.9`.
