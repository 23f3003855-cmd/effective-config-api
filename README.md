# Effective Config API

A FastAPI app for the TDS config-precedence task.

## Run locally

```bash
python -m pip install -r requirements.txt
uvicorn main:app --reload
```

Open `http://127.0.0.1:8000/effective-config`.

Try CLI/query overrides:

```text
http://127.0.0.1:8000/effective-config?set=port=9000&set=debug=true
```

## Deploy on Render

This repository includes `render.yaml` for a Render Blueprint. Push the project files to a GitHub repository and create a new Blueprint in Render from that repository. The blueprint will create a free web service with the required OS environment variables.

The `.env` file is intentionally parsed manually, so its values do not overwrite the OS-level layer before precedence is applied.
