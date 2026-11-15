import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app


def export_openapi():
    """
    Экспортирует схему OpenAPI в формате JSON (UTF-8, indent=2).
    Сохраняет файл в единый источник правды: backend/openapi.json.
    """
    openapi_schema = app.openapi()

    backend_dir = Path(__file__).resolve().parent.parent
    backend_target = backend_dir / "openapi.json"

    json_content = json.dumps(openapi_schema, ensure_ascii=False, indent=2)

    with open(backend_target, "w", encoding="utf-8") as f:
        f.write(json_content)

    routes_count = len(openapi_schema.get("paths", {}))
    schemas_count = len(openapi_schema.get("components", {}).get("schemas", {}))

    print("[OK] Контракт OpenAPI успешно выгружен:")
    print(f"  - Маршрутов (paths): {routes_count}")
    print(f"  - Схем данных (schemas): {schemas_count}")
    print(f"  - Файл сохранен в: {backend_target}")


if __name__ == "__main__":
    export_openapi()
