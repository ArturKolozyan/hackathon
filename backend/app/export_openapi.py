import json
import os
from pathlib import Path


def output_path() -> Path:
    override = os.environ.get("OPENAPI_PATH")
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[2] / "openapi" / "openapi.json"


def canonical(schema: dict) -> str:
    return json.dumps(schema, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> None:
    from app.main import app

    path = output_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(canonical(app.openapi()), encoding="utf-8")
    print(path)


if __name__ == "__main__":
    main()
