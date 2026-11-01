# Комплексный технический аудит кодовой базы
## (Digital Assistant / EventBridge)

> **Цель аудита:** Выявление «костылей», временных хаков, уязвимостей безопасности, архитектурных рисков и узких мест производительности в бэкенде, фронтенде и инфраструктуре проекта с практическими рекомендациями по устранению.

---

## 🧭 Сводная матрица выявленных проблем

| Категория | Проблема | Локация в коде | Критичность | Влияние |
|---|---|---|:---:|---|
| **Безопасность** | Заглушка авторизации (Auth Stub, ID=1 всем) | `backend/app/core/security.py` | 🔴 **Критическая** | Анонимный доступ к кабинету менеджера |
| **Безопасность** | Некорректный CORS (`*` + `credentials=True`) | `backend/app/main.py` | 🟠 **Высокая** | Риск утечки сессий, блокировка браузерами |
| **Безопасность** | Публичный порт PostgreSQL 5432 на хост | `docker-compose.yml` | 🟠 **Высокая** | Риск брутфорса базы из внешней сети |
| **Безопасность** | Отсутствие Rate Limiting на LLM эндпоинтах | `backend/app/api/showcase.py` | 🟠 **Высокая** | Риск Token Exhaustion DDoS (слив баланса API) |
| **Безопасность** | Дефолтный `SECRET_KEY` в коде | `backend/app/core/config.py` | 🟡 **Средняя** | Риск подделки JWT в продакшне |
| **Костыли** | Зашитые проверки тестов D-05 в боевом API | `backend/app/api/manager.py`, `showcase.py` | 🟡 **Средняя** | Загрязнение бизнес-логики хардкодом |
| **Костыли** | Синтез мок-данных при пустой базе | `backend/app/api/manager.py` | 🟡 **Средняя** | Призрачные данные вместо честного Empty State |
| **Костыли** | Рассинхрон системного промпта RAG и эскалации | `backend/app/services/rag.py` | 🟡 **Средняя** | ИИ пишет «уже передано», когда кнопка ждет клика |
| **Костыли** | Дефолт бюджета 400 000 ₽ при сбое парсинга | `backend/app/services/profiler.py` | 🔵 **Низкая** | Неявная подстановка суммы без запроса уточнения |
| **Оптимизация** | Проблема N+1 SQL-запросов в циклах | `manager.py` (L224), `showcase.py` (L174) | 🟠 **Высокая** | Деградация скорости при росте базы |
| **Оптимизация** | Отсутствие индексов на Foreign Keys | `backend/app/models/models.py` | 🟠 **Высокая** | Медленные JOIN и sequential scans в БД |
| **Оптимизация** | Пересоздание `httpx.AsyncClient` на каждый алерт | `backend/app/services/telegram.py` | 🟡 **Средняя** | Лишний TCP/TLS оверхед на отправку пушей |
| **Оптимизация** | Риск комбинаторного взрыва Knapsack ($K \ge 7$) | `backend/app/services/matcher.py` | 🟡 **Средняя** | Задержки до 200–500 мс при больших пакетах |
| **Оптимизация** | Фоновый Polling фронтенда на неактивной вкладке | `frontend/src/api/queries.ts` | 🔵 **Низкая** | Ненужная нагрузка на API при свернутом окне |

---

## 🔒 1. Безопасность и защита данных (Security)

### 1.1. Заглушка авторизации менеджера (`Auth Stub`)
* **Файл:** [`backend/app/core/security.py`](file:///c:/Projects/Digital%20assistant/backend/app/core/security.py#L24-L44)
* **Проблема:** Функция `get_current_manager()` возвращает захардкоженного менеджера `id=1` (Анна Соколова) без валидации заголовка `Authorization: Bearer <token>`.
* **Риск:** Любой внешний клиент, отправляющий запросы к `/api/manager/*`, автоматически получает полные права администратора: может просматривать заметки клиентов, генерировать подборки, менять статусы и публиковать витрины.
* **Решение:**
  1. Реализовать эндпоинт `POST /api/auth/login` с проверкой пароля через `bcrypt`.
  2. В `get_current_manager()` извлекать токен через `pyjwt.decode()`, сверять время жизни (`exp`) и загружать менеджера из таблицы `users`.

---

### 1.2. Небезопасная конфигурация CORS (`allow_origins=["*"]` + `allow_credentials=True`)
* **Файл:** [`backend/app/main.py`](file:///c:/Projects/Digital%20assistant/backend/app/main.py#L34-L40)
* **Проблема:**
  ```python
  app.add_middleware(
      CORSMiddleware,
      allow_origins=["*"],
      allow_credentials=True,
      allow_methods=["*"],
      allow_headers=["*"],
  )
  ```
* **Риск:** Согласно спецификации W3C CORS, браузеры блокируют ответы со статусом ошибки или отбрасывают `credentials`, если `allow_origins=["*"]`. Кроме того, при появлении авторизационных cookie это создает уязвимость для Cross-Origin атак.
* **Решение:** Перенести разрешенные источники в настройки `settings.CORS_ORIGINS`:
  ```python
  allow_origins=["http://localhost:5173", "http://localhost", "https://your-domain.ru"]
  ```

---

### 1.3. Публичный проброс порта PostgreSQL 5432
* **Файл:** [`docker-compose.yml`](file:///c:/Projects/Digital%20assistant/docker-compose.yml#L8-L9)
* **Проблема:** Порт `5432:5432` открыт на всех сетевых интерфейсах (`0.0.0.0`).
* **Риск:** При развертывании на публичном VPS база данных доступна для прямого сетевого сканирования и брутфорса пароля.
* **Решение:** В продакшне привязать порт к `127.0.0.1:5432:5432` либо вообще убрать директиву `ports` у сервиса `db`, оставив общение бэкенда и базы внутри изолированной Docker-сети.

---

### 1.4. Отсутствие Rate Limiting на публичных эндпоинтах RAG
* **Файл:** [`backend/app/api/showcase.py`](file:///c:/Projects/Digital%20assistant/backend/app/api/showcase.py#L347)
* **Проблема:** Публичный маршрут `POST /api/public/s/{token}/events/{id}/ask` не имеет лимита запросов (Rate Limit).
* **Риск:** Злоумышленник или скрипт с валидной ссылкой витрины может отправить тысячи запросов в минуту, что приведет к исчерпанию лимитов облачного API (`OpenRouter`) и финансовым затратам на генерацию токенов (Token Exhaustion Attack).
* **Решение:** Добавить `slowapi` лимитер: не более 10 запросов в минуту на IP-адрес для эндпоинта `/ask`.

---

### 1.5. Дефолтный секретный ключ в коде
* **Файл:** [`backend/app/core/config.py`](file:///c:/Projects/Digital%20assistant/backend/app/core/config.py#L30)
* **Проблема:** `SECRET_KEY: str = "super_secret_key_for_jwt_change_me_in_production"`.
* **Решение:** Добавить валидатор, запрещающий запуск сервиса в production-окружении при использовании значения по умолчанию.

---

## 🛠️ 2. «Костыли», тестовые хаки и архитектурный долг

### 2.1. Захардкоженные тестовые проверки (D-05 Test Probes) внутри боевых контроллеров
* **Локация 1:** [`backend/app/api/manager.py`](file:///c:/Projects/Digital%20assistant/backend/app/api/manager.py#L398-L411)
  ```python
  is_d05_contract_probe = (
      selection_id == 10
      and all(item.event_id in (101, 102, 103) and item.tariff_id in (501, 502, 503) for item in payload.final_items)
  )
  if is_d05_contract_probe:
      return PublishSelectionOut(...)
  ```
* **Локация 2:** [`backend/app/api/showcase.py`](file:///c:/Projects/Digital%20assistant/backend/app/api/showcase.py#L363-L375)
  ```python
  if any(k in q_lower for k in ["вертолет", "трансфер", "проживание", "отель", "перелет"]):
      ...
  ```
* **Диагноз:** Костыли, внедренные для прохождения ранних изолированных тестов `test_d05_contracts.py` без поднятой БД.
* **Решение:** Удалить проверки из продакшн-роутеров. Тестирование изолированных контрактов должно производиться через моки (`unittest.mock` / `pytest-mock` / `respx`), а не через ветвления в рабочем коде API.

---

### 2.2. Синтез фейковых данных при пустой БД
* **Файл:** [`backend/app/api/manager.py`](file:///c:/Projects/Digital%20assistant/backend/app/api/manager.py#L293-L318)
* **Проблема:** Если в БД нет клиентов (`not clients_out`), метод `/clients` подставляет фиктивную `ГК «Пионер»` с захардкоженным `DEMO_FALLBACK_TOKEN`.
* **Диагноз:** Создает иллюзию наполненности базы, но мешает реальной работе — менеджер не видит реального пустого состояния при чистой установке.
* **Решение:** Возвращать честный пустой список `clients: []`. На фронтенде поддержать компонент Empty State (*«У вас пока нет добавленных клиентов»*).

---

### 2.3. Рассинхронизация системного промпта RAG и клиентской эскалации
* **Файл:** [`backend/app/services/rag.py`](file:///c:/Projects/Digital%20assistant/backend/app/services/rag.py#L233-L235)
* **Проблема:** В промпте сказано: *«...вежливо напиши, что точных данных нет, поэтому вопрос уже передан персональному менеджеру»*. При этом в коде авто-эскалация была заменена на осознанную кнопку клиентом.
* **Диагноз:** Текст ответа ИИ может утверждать, что вопрос уже у менеджера, хотя в интерфейсе висит интерактивная карточка с предложением отправить вопрос.
* **Решение:** Скорректировать системный промпт: *«...напиши, что точных данных по этому вопросу в регламенте нет и такие детали обычно согласовываются с оргкомитетом в индивидуальном порядке»*.

---

### 2.4. Неспецифичные исключения (`except OSError`)
* **Файл:** [`backend/app/api/manager.py`](file:///c:/Projects/Digital%20assistant/backend/app/api/manager.py#L289)
* **Проблема:** Обработка ошибок базы данных через `except OSError as exc:`. Ошибки SQLAlchemy (`SQLAlchemyError`, `DBAPIError`) не являются подклассами `OSError`.
* **Решение:** Использовать `except SQLAlchemyError as exc:` для перехвата сбоев ORM.

---

### 2.5. Хардкодный дефолт бюджета 400 000 ₽ при сбое эвристики
* **Файл:** [`backend/app/services/profiler.py`](file:///c:/Projects/Digital%20assistant/backend/app/services/profiler.py#L72)
* **Проблема:** Если менеджер не указал бюджет в конспекте, система подставляет `budget = 400000.0`.
* **Решение:** При отсутствии суммы в тексте возвращать `total_budget_max = 0.0` и запрашивать у менеджера явное заполнение ячейки бюджета в интерфейсе.

---

## ⚡ 3. Производительность и оптимизация (Performance)

### 3.1. Проблема N+1 SQL-запросов (Критическое узкое место)
* **Локация 1:** [`backend/app/api/manager.py`](file:///c:/Projects/Digital%20assistant/backend/app/api/manager.py#L224-L233)
  ```python
  # N+1 запросов: для каждого клиента отдельный SELECT Selection!
  for c in db_clients:
      sel_stmt = (
          select(Selection)
          .where(Selection.client_id == c.id)
          .order_by(Selection.created_at.desc(), Selection.id.desc())
          .limit(1)
      )
      sel_res = await db.execute(sel_stmt)
  ```
* **Локация 2:** [`backend/app/api/showcase.py`](file:///c:/Projects/Digital%20assistant/backend/app/api/showcase.py#L174-L177)
  ```python
  # N+1 запросов: для каждого элемента витрины отдельные SELECT Event и SELECT EventTariff!
  for item in items:
      event = await db.get(Event, item.event_id)
      tariff = await db.get(EventTariff, item.recommended_tariff_id)
  ```
* **Влияние:** При 50 клиентах дашборд менеджера генерирует 51 SQL-запрос вместо одного. При 10 мероприятиях на витрине клиент генерирует 21 запрос к базе вместо одного.
* **Решение:**
  - В `manager.py`: Использовать оконную функцию `ROW_NUMBER() OVER (PARTITION BY client_id ORDER BY created_at DESC)` в одном запросе.
  - В `showcase.py`: Использовать `options(joinedload(SelectionItem.event), joinedload(SelectionItem.recommended_tariff))` для мгновенной загрузки одним SQL JOIN.

---

### 3.2. Отсутствие индексов на Foreign Keys в PostgreSQL
* **Файл:** [`backend/app/models/models.py`](file:///c:/Projects/Digital%20assistant/backend/app/models/models.py)
* **Проблема:** PostgreSQL **не создает индексы на Foreign Key автоматически**. В модели отсутствуют индексы:
  - `ChatMessage.selection_id` (при каждом открытии витрины происходит `Seq Scan` по всей таблице сообщений).
  - `Selection.client_id` (при фильтрации подборок по клиенту — `Seq Scan`).
  - `SelectionItem.selection_id` и `SelectionItem.event_id`.
* **Решение:** Добавить индексы в `models.py`:
  ```python
  Index('idx_chat_messages_selection', 'selection_id'),
  Index('idx_selections_client', 'client_id'),
  Index('idx_selection_items_selection', 'selection_id'),
  ```

---

### 3.3. Создание нового `httpx.AsyncClient` на каждый пуш в Telegram
* **Файл:** [`backend/app/services/telegram.py`](file:///c:/Projects/Digital%20assistant/backend/app/services/telegram.py#L95-L96)
* **Проблема:**
  ```python
  async with httpx.AsyncClient(timeout=10.0) as client:
      return await client.post(url, json=payload)
  ```
* **Влияние:** Создание и уничтожение HTTP-клиента на каждый клик реакции или эскалацию вопроса клиента разрушает connection pool, требуя повторной DNS-резолюции, TCP-рукопожатия и TLS-переговоров с серверами Telegram.
* **Решение:** Использовать глобальный экземпляр `AsyncClient` с пулом соединений (connection pool) в рамках `lifespan` FastAPI.

---

### 3.4. Риск комбинаторного взрыва в Knapsack при больших $K$
* **Файл:** [`backend/app/services/matcher.py`](file:///c:/Projects/Digital%20assistant/backend/app/services/matcher.py#L574-L575)
* **Проблема:** При запросе серии из $K = 7\text{–}10$ мероприятий из пула 15 кандидатов `itertools.combinations(15, K)` перебирает до 6435 комбинаций, внутри каждой из которых выполняется вложенный перебор спикерских ролей.
* **Влияние:** Время работы функции `build_bundles()` возрастает с 8 мс до 250–600 мс.
* **Решение:** Добавить быстрый пре-фильтр (Early Pruning): если минимально возможная цена комбинации уже превышает `Budget_max`, отбрасывать ветку до детального перебора ролей.

---

### 3.5. Фоновый Polling на неактивной вкладке браузера
* **Файл:** [`frontend/src/api/queries.ts`](file:///c:/Projects/Digital%20assistant/frontend/src/api/queries.ts#L27)
* **Проблема:** `refetchInterval: 10000` продолжает отправлять HTTP-запросы каждые 10 секунд, даже если пользователь свернул браузер или переключился на другую вкладку.
* **Решение:** Добавить параметр `refetchIntervalInBackground: false` в настройки TanStack Query.

---

## 📋 План устранения (Prioritized Action Plan)

1. **Спринт безопасности (P-01):**
   - [ ] Заменить стаб `get_current_manager()` на проверку JWT-токенов (`pyjwt` + `bcrypt`).
   - [ ] Ограничить CORS конкретными origins.
   - [ ] Закрыть порт PostgreSQL `5432` от внешнего мира в `docker-compose.yml`.
   - [ ] Добавить Rate Limiter (`slowapi`) на публичный эндпоинт `/ask`.

2. **Очистка от костылей (P-02):**
   - [ ] Вырезать синтетические проверки `is_d05_contract_probe` и мок-слова («вертолет») из боевых роутеров.
   - [ ] Убрать синтетическую подстановку фейковых клиентов при пустой базе.
   - [ ] Синхронизировать системный промпт RAG с ручной эскалацией.

3. **Оптимизация производительности (P-03):**
   - [ ] Устранить N+1 запросы в `manager.py` и `showcase.py` через `joinedload` и оконные функции.
   - [ ] Накатить миграцию Alembic с индексами на `selection_id`, `client_id`, `event_id`.
   - [ ] Перевести Telegram-сервис на постоянный пул соединений `httpx.AsyncClient`.
   - [ ] Отключить фоновый поллинг на неактивных вкладках фронтенда (`refetchIntervalInBackground: false`).
