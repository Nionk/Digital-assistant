# Руководство по запуску проекта (Startup Guide)

## Требования к окружению
- **Docker** 24+ и **Docker Compose** v2
- **Python** 3.12+ (для локальной разработки без Docker)
- **Node.js** 20+ (для локальной разработки фронтенда без Docker)

---

## 1. Первоначальная настройка

1. Клонируйте репозиторий и перейдите в корень проекта:
   ```bash
   git clone https://github.com/Nionk/Digital-assistant.git
   cd Digital-assistant
   ```

2. Скопируйте шаблон переменных окружения:
   ```bash
   # Windows PowerShell:
   Copy-Item .env.example .env
   # Linux / macOS:
   cp .env.example .env
   ```

3. Задайте секреты в `.env`:
   - Сгенерируйте надёжный `SECRET_KEY` (например: `openssl rand -hex 32`).
   - Укажите ключи к ИИ: `LLM_API_KEY` (OpenRouter / DeepSeek) и `EMBEDDING_API_KEY` (Jina AI).
   - При необходимости укажите `TELEGRAM_BOT_TOKEN` и `TELEGRAM_MANAGER_CHAT_ID`.

---

## 2. Запуск в Production-режиме (по умолчанию)

В прод-режиме:
- Порт бэкенда (`8000`) закрыт наружу и доступен только через Nginx.
- Обход авторизации строго запрещён (`ALLOW_DEMO_AUTH_BYPASS=false`, иначе приложение не запустится).
- Все API-запросы проходят через Nginx на порту `80`.

```bash
# 1. Запуск всех 3 сервисов (db, backend, frontend/nginx) в фоне:
docker compose up -d --build

# 2. Применение миграций PostgreSQL + pgvector:
docker compose exec backend alembic upgrade head

# 3. Наполнение базы начальными данными (каталог мероприятий и пользователи):
docker compose exec backend python scripts/seed_db.py

# 4. Проверка состояния:
docker compose ps
```
Сервис доступен по адресу: **http://localhost** (или IP/домен вашего сервера).

---

## 3. Запуск в Development-режиме (локальная разработка)

Для локальной разработки предусмотрен compose-оверлей `docker-compose.dev.yml`:
- Пробрасывает код `./backend` как том (горячая перезагрузка uvicorn `--reload`).
- Открывает порт бэкенда на `127.0.0.1:8000` для прямого тестирования и Swagger UI (`/docs`).
- Разрешает `ENVIRONMENT=dev` и при необходимости `ALLOW_DEMO_AUTH_BYPASS=true` для отладки без ввода JWT.

### Вариант А: Все сервисы в Docker
```bash
# Запуск с оверлеем разработки:
docker compose -f docker-compose.yml -f docker-compose.dev.yml up -d --build

# Миграции и сиды:
docker compose exec backend alembic upgrade head
docker compose exec backend python scripts/seed_db.py
```
- Swagger UI бэкенда: **http://localhost:8000/docs**
- Фронтенд (Nginx): **http://localhost**

### Вариант Б: База данных в Docker, сервисы локально
```bash
# 1. Запуск только PostgreSQL 16 + pgvector:
docker compose up -d db

# 2. Бэкенд локально:
cd backend
python -m venv .venv
# Активация: .venv\Scripts\activate (Windows) или source .venv/bin/activate (Linux/Mac)
pip install -r requirements.txt
alembic upgrade head
python scripts/seed_db.py
uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload

# 3. Фронтенд локально (в отдельном терминале):
cd frontend
npm install
npm run dev
# Открыть: http://localhost:5173
```

---

## 4. Фоновый мониторинг площадок (Cron / APScheduler)

Фоновый мониторинг 9 площадок с отправкой утренней сводки в Telegram управляется переменной окружения:
```env
ENABLE_SCHEDULER=true
APP_TIMEZONE=Europe/Moscow
```
При `ENABLE_SCHEDULER=true` сервис запускает планировщик внутри lifespan FastAPI и ежедневно в 03:00 МСК производит мониторинг обновлений.

---

## 5. Полезные команды

```bash
# Проверка здоровья сервиса:
curl http://localhost/health
# или напрямую (в dev-режиме):
curl http://127.0.0.1:8000/health

# Просмотр логов:
docker compose logs -f backend
docker compose logs -f frontend

# Остановка контейнеров:
docker compose down
```
