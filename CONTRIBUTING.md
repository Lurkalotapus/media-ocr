# Contributing

## Scope

Keep the evidence, review, and final-note layers separate. Never make OCR output authoritative or delete raw OCR observations as part of presentation cleanup.

## Development

Use Python 3.14 and install the base dependencies:

```bash
python -m venv .venv
.venv/bin/python -m pip install -r docs/requirements.txt
```

Add a regression test before changing behavior, observe it fail, then implement the smallest fix. Run:

```bash
.venv/bin/python -m unittest discover -s skill/scripts -p 'test_*.py' -v
```

Do not add real private media, credentials, absolute user paths, generated OCR output, or downloaded model files to version control.
