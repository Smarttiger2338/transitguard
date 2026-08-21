# Contributing

Thank you for considering a contribution to TransitGuard.

## Development setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev,api]
pytest
```

## Before opening a pull request

Run:

```bash
ruff check .
pytest
```

## Project direction

TransitGuard should stay focused on transfer reliability. Full map rendering, fare calculation, and navigation UI features are out of scope unless they directly improve reliability evaluation.
