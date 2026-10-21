import json
import sys
from pathlib import Path

# Обеспечиваем корректный импорт app.* при прямом запуске скрипта
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.main import app


def export_openapi():
    """
    Экспортирует схему OpenAPI в формате JSON (UTF-8, indent=2).
    Сохраняет файл в корневую директорию проекта и в папку backend/.
    """
    openapi_schema = app.openapi()

    backend_dir = Path(__file__).resolve().parent.parent
    root_dir = backend_dir.parent

    backend_target = backend_dir / "openapi.json"
    root_target = root_dir / "openapi.json"

    json_content = json.dumps(openapi_schema, ensure_ascii=False, indent=2)

    with open(backend_target, "w", encoding="utf-8") as f:
        f.write(json_content)

    with open(root_target, "w", encoding="utf-8") as f:
        f.write(json_content)

    routes_count = len(openapi_schema.get("paths", {}))
    schemas_count = len(openapi_schema.get("components", {}).get("schemas", {}))

    print(f"[OK] Контракт OpenAPI успешно выгружен:")
    print(f"  - Маршрутов (paths): {routes_count}")
    print(f"  - Схем данных (schemas): {schemas_count}")
    print(f"  - Файлы сохранены в:")
    print(f"      1. {backend_target}")
    print(f"      2. {root_target}")


if __name__ == "__main__":
    export_openapi()
