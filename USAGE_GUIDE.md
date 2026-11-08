# Руководство по архитектуре и работе с приложением (Usage Guide)

## 1. Архитектурные принципы и изменения

В рамках оптимизации кодовой базы были полностью устранены скрытые тестовые костыли и уязвимости:
1. **Устранение IDOR (Insecure Direct Object Reference):**
   - В роутах кабинета менеджера (`/api/manager/clients`, `/api/manager/clients/{id}/match`, `/api/manager/selections/{id}/publish`, `/api/manager/selections/{id}/activity`, `/api/manager/selections/{id}/reply`) внедрена строгая изоляция по `current_manager.id`.
   - Менеджер видит и имеет доступ исключительно к своим закрепленным клиентам и подборкам.
2. **Ликвидация «Test-Infected» продакшн-кода:**
   - Из контроллеров API (`manager.py`, `showcase.py`, `security.py`, `auth.py`) удалены все фиктивные моки (`DEMO_FALLBACK_TOKEN`, подборка №10, ответ про вертолеты, захардкоженный клиент «ГК Пионер» и «Анна Соколова»).
   - При недоступности БД API честно отдает HTTP `503 Service Unavailable`, а при отсутствии сущности — `404 Not Found`.
3. **Обобщенные алгоритмы вместо точечных исключений:**
   - Алгоритм подбора пакетов в `matcher.py` переведен на декартово произведение не-спикерских ролей (`itertools.product`), что позволяет автоматически рассчитывать любое сочетание спонсорских, делегатских и спикерских слотов.
   - Парсер топонимов в `profiler.py` классифицирует аббревиатуры (без гласных), омонимы (требующие контекстного предлога) и склоняемые города системно.

---

## 2. Модель аутентификации и безопасность

### Контуры доступа
- **Публичный контур:**
  - `POST /api/auth/login` — получение JWT-токена доступа.
  - `GET /health` — проверка процесса (Liveness).
  - `GET /ready` — проверка связи с PostgreSQL (Readiness).
  - `GET /api/public/s/{magic_token}` и вложенные эндпоинты — доступ к клиентской витрине по защищенному криптографическому UUIDv4 ссылке.
- **Закрытый контур менеджера (`/api/manager/*`):**
  - Требует заголовок `Authorization: Bearer <JWT-токен>`.

### Переходный флаг `ALLOW_DEMO_AUTH_BYPASS`
- **В Production (`docker-compose.yml`):**
  `ALLOW_DEMO_AUTH_BYPASS: "false"` — любой неавторизованный запрос к кабинету менеджера блокируется со статусом `401 Unauthorized`.
- **В Development (`ENVIRONMENT=dev`):**
  Пока фронтенд не имеет готового экрана входа, бэкенд разрешает локальные запросы без токена, автоматически загружая первого активного менеджера из базы данных (`select(User).order_by(User.id.asc()).limit(1)`).

---

## 3. Быстрый запуск и сценарии работы

### Сценарий 1. Запуск в Docker Compose (Production)
```bash
# 1. Запуск всех сервисов в фоне
docker compose up -d --build

# 2. Проверка статуса контейнеров и readiness-пробы
docker compose ps
curl http://localhost:8000/ready
```
* Фронтенд и Nginx: `http://localhost:80`
* Документация OpenAPI: `http://localhost:8000/docs`

### Сценарий 2. Авторизация и работа с API
1. **Вход менеджера в систему:**
   ```bash
   curl -X POST http://localhost:8000/api/auth/login \
     -H "Content-Type: application/json" \
     -d '{"email": "manager@skart.ru", "password": "password"}'
   ```
2. **Получение дашборда закрепленных клиентов:**
   ```bash
   curl http://localhost:8000/api/manager/clients \
     -H "Authorization: Bearer <ACCESS_TOKEN>"
   ```
3. **Ручной импорт PDF-брошюры или текста мероприятия:**
   ```bash
   curl -X POST http://localhost:8000/api/manager/events/upload-pdf \
     -H "Authorization: Bearer <ACCESS_TOKEN>" \
     -F "file=@brochure.pdf"
   ```
4. **Запуск фонового парсинга площадки:**
   ```bash
   curl -X POST http://localhost:8000/api/manager/scraper/run \
     -H "Authorization: Bearer <ACCESS_TOKEN>" \
     -H "Content-Type: application/json" \
     -d '{"source_key": "vedomosti"}'
   ```
5. **Мониторинг реакций и вопросов клиентов (Polling):**
   ```bash
   curl http://localhost:8000/api/manager/selections/1/activity \
     -H "Authorization: Bearer <ACCESS_TOKEN>"
   ```
6. **Ответ менеджера в чат витрины:**
   ```bash
   curl -X POST http://localhost:8000/api/manager/selections/1/reply \
     -H "Authorization: Bearer <ACCESS_TOKEN>" \
     -H "Content-Type: application/json" \
     -d '{"message_id": 42, "reply_text": "Да, для вашей делегации забронированы VIP-места в 1 ряду."}'
   ```

### Сценарий 3. Локальная разработка (Dev)
```bash
# 1. Запуск базы данных
docker compose up db -d

# 2. Применение миграций и запуск бэкенда
alembic upgrade head
uvicorn app.main:app --reload --port 8000
```
