import os
from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

BASE_DIR = Path(__file__).resolve().parent

DEFAULTS: dict[str, Any] = {
    "port": 8000,
    "workers": 1,
    "debug": False,
    "log_level": "info",
    "api_key": "default-secret-000",
}

app = FastAPI(title="Effective Config API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "OPTIONS"],
    allow_headers=["*"],
)


def normalize_key(raw_key: str) -> str:
    key = raw_key.strip()
    upper_key = key.upper()
    if upper_key == "NUM_WORKERS":
        return "workers"
    if upper_key.startswith("APP_"):
        return upper_key[4:].lower()
    return key.lower()


def parse_scalar(value: Any) -> Any:
    # YAML layer may already have integers and booleans; env/query values are strings.
    return value


def read_dotenv(path: Path) -> dict[str, str]:
    """Read .env without putting its values into os.environ (keeps layer order clear)."""
    result: dict[str, str] = {}
    if not path.exists():
        return result
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        result[key.strip()] = value
    return result


def apply_mapping(target: dict[str, Any], layer: dict[str, Any], *, only_app_prefix: bool = False) -> None:
    for raw_key, raw_value in layer.items():
        key_text = str(raw_key).strip()
        if only_app_prefix and not key_text.upper().startswith("APP_") and key_text.upper() != "NUM_WORKERS":
            continue
        key = normalize_key(key_text)
        target[key] = parse_scalar(raw_value)


def coerce_value(key: str, value: Any) -> Any:
    text = str(value).strip()
    if key in {"port", "workers"}:
        try:
            return int(text)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=f"'{key}' must be an integer") from exc
    if key == "debug":
        return text.lower() in {"true", "1", "yes", "on"}
    return text


def build_effective_config(request: Request) -> dict[str, Any]:
    config = DEFAULTS.copy()

    # Layer 2: environment-specific YAML, defaults to development.
    environment_name = os.environ.get("ENVIRONMENT", "development")
    yaml_path = BASE_DIR / f"config.{environment_name}.yaml"
    if yaml_path.exists():
        try:
            yaml_data = yaml.safe_load(yaml_path.read_text(encoding="utf-8")) or {}
        except yaml.YAMLError as exc:
            raise HTTPException(status_code=500, detail="Invalid YAML config file") from exc
        if isinstance(yaml_data, dict):
            apply_mapping(config, yaml_data)

    # Layer 3: .env file. NUM_WORKERS is a supported alias for workers.
    apply_mapping(config, read_dotenv(BASE_DIR / ".env"), only_app_prefix=True)

    # Layer 4: actual OS environment variables with APP_ prefix.
    os_layer = {key: value for key, value in os.environ.items() if key.upper().startswith("APP_")}
    apply_mapping(config, os_layer, only_app_prefix=True)

    # Layer 5: each set=key=value query parameter overrides all configuration layers.
    for item in request.query_params.getlist("set"):
        if "=" not in item:
            raise HTTPException(status_code=400, detail="Each set parameter must use key=value")
        raw_key, raw_value = item.split("=", 1)
        key = normalize_key(raw_key)
        config[key] = coerce_value(key, raw_value)

    # Ensure all values have the required output types, even for YAML and env layers.
    for key in ("port", "workers", "debug", "log_level", "api_key"):
        if key in config:
            config[key] = coerce_value(key, config[key])

    # Do not expose the secret, even if it was overridden by the caller.
    config["api_key"] = "****"
    return config


@app.get("/")
def root() -> dict[str, str]:
    return {"message": "Effective Config API is running", "endpoint": "/effective-config"}


@app.get("/effective-config")
def effective_config(request: Request) -> dict[str, Any]:
    return build_effective_config(request)
