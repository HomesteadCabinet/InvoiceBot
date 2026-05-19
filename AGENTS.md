# Repository Guidelines

## Project Structure & Module Organization

- `invoiceinator/` contains the Django backend, invoice parsers, API views, migrations, and backend tests.
- `invoiceinator/test/` holds parser fixtures and the standalone parser harness used to validate PDF extraction.
- `invoice-frontend/` contains the Quasar/Vite frontend.
- `systemd/user/` contains user-level service units for local debug runs.
- `run.sh` is the main convenience script for starting backend, frontend, or both.

## Build, Test, and Development Commands

- `pyenv install 3.12.9 && pyenv virtualenv 3.12.9 invoiceinator && pyenv local invoiceinator` sets up the backend Python environment.
- `cd invoiceinator && pip install -r requirements.txt` installs Django and parser dependencies.
- `./run.sh django` starts the Django debug server on `0.0.0.0:9999`.
- `./run.sh vue` starts the Quasar dev server.
- `./run.sh all` runs both services together.
- `cd invoice-frontend && npm run lint` checks the frontend.
- `cd invoice-frontend && npm run build` creates a production frontend build.
- `cd invoiceinator && python test/test_parsers.py` runs the PDF parser regression harness.

## Coding Style & Naming Conventions

- Use 4-space indentation for Python and follow standard Django conventions.
- Prefer `snake_case` for Python functions, variables, and parser helpers.
- Keep parser entrypoints named `parse_<vendor>_invoice`; the test harness discovers those names.
- For Vue/JS, follow the existing ESLint rules in `invoice-frontend/eslint.config.js`.
- Keep changes small and local to the relevant backend or frontend module.

## Testing Guidelines

- Add backend tests under `invoiceinator/invoices/tests.py` or extend the parser harness in `invoiceinator/test/test_parsers.py`.
- Name parser fixtures descriptively, e.g. `vendor_name.pdf` or `vendor_variant.pdf`.
- When changing parsing logic, run the parser harness against the affected PDFs and note any failures.

## Commit & Pull Request Guidelines

- Commit history in this repo is short and direct, often using date-stamped summaries such as `4-9-25 New Parsers`.
- Keep commits focused on one change set and use a clear subject line.
- PRs should include a short description, commands run, and screenshots for frontend changes when relevant.
- Call out any fixture PDFs, parser rules, or service files changed.

## Security & Configuration Tips

- Do not commit secrets, OAuth tokens, or Gmail/Sheets credentials.
- Local user services assume the repo lives at `~/Dev/Invoiceinator`; adjust paths if your checkout differs.
