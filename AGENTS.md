# Repository Guidelines

## Project Structure & Module Organization
- `main.py` — legacy CLI scanner for 2m band.
- `scanner_frontend.py` — Flask API + background scanner loop.
- `web/` — static frontend (index.html UI).
- `simulate_scanner.py` — simulated activity generator.
- `test_*.py` — pytest-based tests (API, loop, hardware checks).
- `bookmarks.csv`, `sdr_scan_*.csv` — runtime outputs; do not edit.
- `sdrscan/` — local virtualenv; do not modify in PRs.

## Build, Test, and Development Commands
- Install deps: `python3 -m pip install -U pip && python3 -m pip install flask pytest numpy`
- Run UI: `python3 scanner_frontend.py` (serves on `http://localhost:5000`).
- Run simulator: `python3 simulate_scanner.py`.
- Run legacy scanner: `python3 main.py`.
- Tests: `pytest -q` (API/unit tests pass without RTL-SDR; hardware tests may require rtl_* tools).

## Coding Style & Naming Conventions
- Python 3.10+, 4-space indentation, UTF-8.
- Use snake_case for functions/vars, PascalCase for classes, UPPER_CASE for constants.
- Keep functions small and focused; add type hints where clear value.
- Prefer standard library and minimal dependencies.
- Don’t commit generated CSV/audio or edit `sdrscan/` contents.

## Testing Guidelines
- Use pytest; name files `test_*.py` and tests `test_*`.
- For API: use Flask `app.test_client()`; keep sleeps short; avoid flakes.
- Prefer simulation for unit tests; hardware/RTL flows should be optional and fast-failing.
- Ensure `pytest -q` passes before opening a PR.

## Commit & Pull Request Guidelines
- Small, focused commits. Suggested prefixes: `feat:`, `fix:`, `test:`, `docs:`, `refactor:`.
- PRs should include: summary of changes, why, test results, and screenshots/GIFs for UI changes.
- Update docs (`todo.md`, this file) when workflows or endpoints change.

## Security & Configuration Tips
- Default port: 5000. `bookmarks.csv` writes in repo root; ensure writable.
- Don’t expose the Flask dev server publicly; use a reverse proxy if needed.
- On Raspberry Pi, prefer a systemd unit for auto-start and watchdog behavior.

## Agent Notes
- Keep patches minimal and surgical; avoid renames unless necessary.
- Do not modify the `sdrscan/` virtualenv.
- Run tests locally and avoid introducing long-running or flaky tests.
