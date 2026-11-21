# Backend API — техническая документация

> Документ составлен по фактическому исходному коду каталога `backend/` (12 модулей `app/`, ~2500 строк), проверен по реализации, а не только по README.
> Всё, что не удалось достоверно установить по коду, помечено явно. Актуальные ограничения и особенности вынесены в раздел [14](#14-расхождения-с-readme-и-ограничения-проверено-по-коду).

---

## 1. Краткое описание

`backend/` — это небольшой HTTP API-слой (BFF/адаптер) между браузерным интерфейсом и **Keitaro Admin API** (`https://admin-api.docs.keitaro.io`, базовый путь `/admin_api/v1`).

Назначение:

1. Скрыть API-ключ Keitaro от браузера: все обращения к трекеру выполняет сервер.
2. Предоставить фронтенду упрощённый контракт: поиск активных офферов в Keitaro, создание кампании вместе с двумя потоками (streams) одним запросом, просмотр истории операций.
3. Выполнить «доменную» валидацию и подстановку сущностей Keitaro по именам (домен, группа кампаний), а также проверку ключа действия потока.
4. Зафиксировать результат операции в локальной БД (журнал `campaign_creation_logs`) со статусами `started` / `success` / `partial` / `failed`.
5. Кэшировать созданные сущности в локальной БД (`campaigns` → `streams` → `offers`) и отдавать чтение из неё.

Ключевая бизнес-операция — `POST /api/campaigns/create`: создаёт кампанию и два потока:

- **GEO - Google** — регулярный поток (`type=regular`) с Country-фильтром, который принимает заданные ISO-коды и редиректит на `https://www.google.com/`;
- **Default - Offer** — дефолтный поток (`type=default`), отдающий 100% трафика на выбранный активный оффер.

Если создание потоков падает, кампания и уже созданные потоки **намеренно не удаляются** в Keitaro — операция помечается как `partial`. Кампания при этом уже сохранена локально, потоки/офферы сохраняются только фактически созданные.

---

## 2. Технологический стек

| Компонент | Версия / факт | Назначение |
|---|---|---|
| Python | 3.13.7 (в `backend/.venv`) | Среда исполнения. В `requirements.txt` версия Python не зафиксирована |
| FastAPI | 0.115.12 | HTTP-фреймворк, маршрутизация, DI, OpenAPI |
| Uvicorn `[standard]` | 0.34.0 | ASGI-сервер |
| Pydantic | 2.10.6 | Валидация/сериализация схем запросов |
| pydantic-settings | 2.7.1 | Загрузка конфигурации из `.env` |
| SQLAlchemy[asyncio] | 2.0.38 | Async ORM (2.0-style `Mapped`/`mapped_column`) |
| aiosqlite | 0.21.0 | Async-драйвер SQLite |
| asyncpg | 0.30.0 | Async-драйвер PostgreSQL |
| httpx | 0.28.1 | Асинхронный HTTP-клиент к Keitaro |
| pycountry | 24.6.1 | Справочник ISO-3166 для проверки GEO-кодов |
| python-slugify | 8.0.4 | Генерация alias кампании из названия |

Файл зависимостей: `backend/requirements.txt`. Dev-зависимостей (pytest, ruff, mypy и т.п.) в нём нет.

Хранилище по умолчанию — SQLite (`backend/campaign_creator.db`), PostgreSQL подразумевается опционально через `DATABASE_URL`. Async-драйверы (`aiosqlite`, `asyncpg`) включены в `requirements.txt`.

---

## 3. Структура Backend

```
backend/
├── .env                 # фактическая конфигурация (содержит секреты; в поставку не входит)
├── .env.example         # шаблон конфигурации
├── requirements.txt     # пины зависимостей
├── requirements-dev.txt # pytest / pytest-asyncio / respx
├── pytest.ini           # конфигурация тестов
├── campaign_creator.db  # SQLite-база по умолчанию (runtime, в git не отслеживается)
├── .venv/               # локальное виртуальное окружение
├── scripts/
│   ├── init_db.py                  # разовая инициализация/миграция схемы
│   ├── backfill_campaigns.py       # опциональный идемпотентный бэкфилл из Keitaro
│   └── dev/
│       └── probe_keitaro_streams.py # read-only проверка формы /streams (этап 0)
├── tests/               # pytest: создание, чтение, репозиторий, веса, синхронизация
└── app/
    ├── __init__.py
    ├── main.py          # create_app: lifespan, middleware, include_router
    ├── config.py        # Settings (pydantic-settings) + синглтон settings
    ├── database.py      # async engine, async_sessionmaker, Base, PRAGMA, get_db
    ├── deps.py          # DbSession, KeitaroClientDep
    ├── errors.py        # EditorError, LocalPersistenceError, RevisionConflictError
    ├── api_errors.py    # доменные исключения -> HTTP response
    ├── models.py        # ORM-модели CampaignCreationLog, Campaign, Stream, Offer
    ├── migrations.py    # async ensure_schema + бэкфилл baseline
    ├── schemas.py       # Pydantic-схемы запроса и ответов
    ├── keitaro.py       # KeitaroClient — HTTP-адаптер Keitaro Admin API
    ├── changes.py       # чистые правила «есть локальные изменения»
    ├── utils.py         # coercion helpers (as_int/as_str/json_safe/...)
    ├── weights.py       # чистое распределение весов офферов
    ├── routers/
    │   ├── health.py    # /api/health, /api/admin/stream-actions
    │   ├── campaigns.py # list/detail/history/create
    │   ├── offers.py    # /api/offers-remote, /api/offers
    │   └── editor.py    # sync/load, push, discard, stream offers, patch offer
    ├── services/
    │   ├── creation.py  # создание кампании/потоков + commit-границы + журнал
    │   └── editor.py    # use-case редактора
    └── repositories/
        ├── campaigns.py # upsert и чтение кампаний/потоков/офферов
        ├── editor.py    # baseline, soft delete, revision CAS
        └── mapping.py   # единый маппинг snapshot-полей
```

Слои разделены: `routers` отвечают только за HTTP, `services` — за сценарии и транзакции, `repositories` — только за SQLAlchemy. Межслойные зависимости направлены сверху вниз; `keitaro.py`, `models.py`, `schemas.py` не зависят от routers/services.

### Назначение модулей

- **`app/main.py`** — `create_app()`: FastAPI, CORS, middleware опциональной аутентификации, `lifespan` с async `create_all`/`ensure_schema`, регистрация exception handlers и routers. `app` остаётся модульной точкой входа для uvicorn.
- **`app/config.py`** — `Settings(BaseSettings)`: типизированное чтение `.env`, синглтон `settings`, `cors_origin_list`. Значения читаются один раз при импорте.
- **`app/database.py`** — `create_async_engine`, `async_sessionmaker` (`expire_on_commit=False`), декларативная база `Base`, `PRAGMA foreign_keys=ON` и `busy_timeout` для SQLite, async-зависимость `get_db()` с rollback и закрытием сессии.
- **`app/deps.py`** — `DbSession` и `KeitaroClientDep`: единый способ получить сессию/клиент Keitaro в роутерах.
- **`app/errors.py`** — доменные исключения: `EditorError`, `LocalPersistenceError`, `RevisionConflictError`, `RemoteChanged`.
- **`app/api_errors.py`** — exception handlers, сохраняющие контракт `{"detail": {"code", "message", ...}}`.
- **`app/models.py`** — `CampaignCreationLog` и три кэширующие сущности: `Campaign`, `Stream`, `Offer` со связями и уникальными ограничениями.
- **`app/routers/`** — HTTP-слой: health/system, campaigns, offers, editor. Бизнес-логики и SQL в роутерах нет.
- **`app/services/creation.py`** — прикладная логика создания: разрешение домена/группы/источника, проверка оффера и action key, генерация имени/alias, `PartialCreationError` и оркестрация трёх commit-границ с журналом.
- **`app/services/editor.py`** — use-case редактора: `add_offer`, `patch_offer`, `discard`, `load_campaign_streams`, `push_campaign_changes`; возвращает Pydantic-контракты, но не знает про HTTP.
- **`app/repositories/campaigns.py`** — upsert кампаний/потоков/офферов, чтение списков/деталей, журнал операций.
- **`app/repositories/editor.py`** — baseline, soft delete, `apply_remote_snapshot`, `reset_to_baseline`, `commit_stream_baseline` и compare-and-swap для `revision`.
- **`app/repositories/mapping.py`** — единый маппинг полей Stream/Offer (устраняет расхождение между созданием и загрузкой).
- **`app/changes.py`** — чистые правила, определяющие локальные изменения; используется и repository, и editor-service.
- **`app/keitaro.py`** — `KeitaroClient`: `httpx.AsyncClient`, `KeitaroError`, пагинация, кэш каталога офферов и обёртки над эндпоинтами трекера.
- **`app/weights.py`** — чистая функция `distribute_shares(offers)`: закреплённые веса неизменны, остаток 100% делится между активными незакреплёнными, остаток отдаётся последним по `Offer.id`; ошибки — `WeightError` с кодом.


---

## 4. Архитектура и взаимодействие компонентов

### 4.1 Общая схема

```
Браузер (React/MUI)
      │  fetch /api/... (Vite proxy → http://127.0.0.1:8000)
      ▼
FastAPI app (app/main.py)
      │  CORS → auth middleware → router → Pydantic → Depends(DbSession)
      ├──► app/routers/*         HTTP-слой
      ├──► app/services/creation.py  создание кампании/потоков
      │         ├──► app/keitaro.py      KeitaroClient (httpx.AsyncClient)
      │         └──► app/repositories    async SQLAlchemy
      ├──► app/services/editor.py    локальные правки + sync
      │         ├──► app/weights.py      распределение весов
      │         ├──► app/keitaro.py      KeitaroClient
      │         └──► app/repositories    baseline / soft delete / revision CAS
      └──► app/repositories → app/models.py + app/database.py  async SQLAlchemy
```

### 4.2 Паттерны и принципы

Фактически реализовано:

- **Слоистая архитектура**: `routers` = HTTP-транспорт, `services` = бизнес-логика и транзакции, `repositories` = персистентность, `keitaro.py` = инфраструктурный шлюз к внешнему API, `models`/`database` = ORM, `schemas` = контракты ввода/вывода.
- **Gateway / Anti-Corruption Layer** — `KeitaroClient` изолирует «сырой» Admin API и его ошибки от остального кода.
- **Dependency Injection** — `DbSession`/`KeitaroClientDep` на базе `Depends`; сессия БД и HTTP-клиент живут в рамках запроса.
- **Settings-объект** (pydantic-settings) вместо прямого чтения `os.environ`.
- **Специализированные исключения**: `PartialCreationError` (частичный успех в Keitaro) и `LocalPersistenceError` (сбой локальной записи после успеха в Keitaro).
- **Идемпотентные upsert'ы** по естественным ключам (`campaigns.keitaro_id`, `streams(campaign_id, keitaro_id)`, `offers(stream_id, keitaro_id)`).

Не реализовано (и не стоит искать): Unit of Work, DI-контейнер, event bus, фоновые задачи, retry/backoff, circuit breaker, idempotency-ключи HTTP-запросов, версионирование API. Единственный кэш — каталог офферов Keitaro в памяти процесса (`KEITARO_OFFERS_CACHE_TTL`).

### 4.3 Где живёт бизнес-логика

Прикладные правила сосредоточены в `app/services/creation.py` (`create_campaign`, `create_campaign_streams`, `find_by_name`, `campaign_alias`) и в валидаторах `app/schemas.py` (нормализация GEO). Оркестрация, порядок коммитов и журналирование операции — в `create_campaign_with_persistence` (`services/creation.py`). Чтение и запись локальных сущностей — в `app/repositories/`.

### 4.4 Особенности исполнения (важно для доработок)

- Приложение полностью **асинхронное**: Keitaro вызывается через `httpx.AsyncClient`, БД — через async SQLAlchemy (`aiosqlite`/`asyncpg`). Все `db.scalars()`/`db.commit()`/`db.flush()` вызываются с `await`; синхронных блокирующих операций в event loop нет.
- `KeitaroClient` создаётся на запрос через `get_keitaro_client` и закрывается в `finally` зависимости. Общего пула соединений между запросами нет.
- `Base.metadata.create_all()` и `ensure_schema()` выполняются в async `lifespan` при старте процесса (если `AUTO_MIGRATE=true`), а не при импорте модуля. Для нескольких воркеров DDL лучше вынести в отдельный шаг: `python -m scripts.init_db` + `AUTO_MIGRATE=false`.
- Создание кампании выполняется **тремя коммитами**: журнал `started` → сохранение кампании сразу после `POST /campaigns` → сохранение потоков/офферов вместе с финальным статусом журнала. Это гарантирует, что кампания уже в локальной БД, даже если создание потоков упадёт.
- Изменения редактора используют compare-and-swap по `campaigns.revision`: сначала ранняя проверка `expected_revision`, затем условный `UPDATE ... WHERE revision = expected`. Гонка двух вкладок даёт `409 REVISION_CONFLICT`.

---

## 5. Поток обработки HTTP-запросов

### 5.1 Маршрутизация и эндпоинты

Маршруты разложены по `APIRouter` в `app/routers/` и подключаются в `create_app()`:

| Метод и путь | Функция | Тип | Назначение |
|---|---|---|---|
| `GET /api/health` | `health` | `async def` | Проверка живости, `{"ok": true}` |
| `GET /api/admin/stream-actions` | `stream_actions` | `async def` | Проброс `GET /streams_actions` из Keitaro (список доступных ключей действий) |
| `GET /api/offers-remote?q=` | `search_offers_remote` | `async def` | Активные офферы Keitaro с фильтрацией по подстроке имени или ID; `q` ≤ 150 символов; `id` — Keitaro ID |
| `POST /api/campaigns/create` | `create_campaign_endpoint` | `async def` | Основная операция: кампания + 2 потока + локальное сохранение + журнал |
| `GET /api/campaigns?limit=&offset=&q=&state=` | `campaigns_list` | `async def` | Локальный список кампаний, `created_at DESC, id DESC` |
| `GET /api/campaigns/history?limit=` | `campaign_history` | `async def` | Последние записи журнала; `limit` 1..200, по умолчанию 50 |
| `GET /api/campaigns/{campaign_id}` | `campaign_detail` | `async def` | Локальные детали для редактора (`CampaignEditorOut`: потоки, офферы, `has_local_changes`, `revision`); 404 `CAMPAIGN_NOT_FOUND` |
| `GET /api/offers?campaign_id=&q=&limit=&offset=` | `campaign_offers` | `async def` | Офферы кампании из локальной БД; `campaign_id` обязателен |
| `POST /api/campaigns/{campaign_id}/sync/load` | `campaign_sync_load` | `async def` | Загрузка снимка из Keitaro; 409 `LOCAL_CHANGES_PENDING` без `force` |
| `POST /api/campaigns/{campaign_id}/sync/push` | `campaign_sync_push` | `async def` | Отправка изменённых потоков в Keitaro; частичный успех — 200 + `success=false` |
| `POST /api/campaigns/{campaign_id}/sync/discard` | `campaign_sync_discard` | `async def` | Откат рабочего состояния к baseline |
| `POST /api/streams/{stream_id}/offers` | `add_stream_offer` | `async def` | Добавить/восстановить оффер в потоке (локально; Keitaro только читается для проверки); принимает `expected_revision` |
| `PATCH /api/offers/{offer_id}` | `patch_offer_endpoint` | `async def` | Удалить/восстановить/закрепить оффер, изменить закреплённый вес; принимает `expected_revision` |

Порядок объявления важен: `GET /api/campaigns/history` объявлен **до** `GET /api/campaigns/{campaign_id}`, иначе `history` матчился бы как `{campaign_id}` и давал 422. Это закреплено регрессионным тестом.

Автоматически FastAPI также отдаёт `/docs`, `/redoc`, `/openapi.json` (не отключались).

### 5.2 Middleware

Два middleware (`app/main.py`):

- `CORSMiddleware`:
  - `allow_origins` — список из `CORS_ORIGINS` (через запятую, значения `strip()`, пустые пропускаются); по умолчанию `http://localhost:5173`;
  - `allow_credentials=True`, `allow_methods=["*"]`, `allow_headers=["*"]`.
- `require_api_token` — опциональная аутентификация по общему секрету. Если `API_AUTH_TOKEN` задан, все пути `/api/*`, кроме `/api/health`, требуют `X-API-Token` или `Authorization: Bearer <token>`; иначе **401** `UNAUTHORIZED`. Сравнение — `secrets.compare_digest`. Если переменная пуста (локальная разработка), проверка отключена.

Других middleware нет: нет rate limiting, request-id, GZip, TrustedHost, логирования запросов.

### 5.3 Валидация входных данных

- **Тело запроса** — модель `CampaignCreate` (`app/schemas.py`):
  - `name`: строка, `min_length=1`, `max_length=255`, валидатор обрезает пробелы и запрещает пустое значение;
  - `geo`: строка 2..255; валидатор `normalize_geo` заменяет `;` и пробелы на запятые, приводит к верхнему регистру, проверяет каждый код через `pycountry` (должен быть валидным `alpha_2`), удаляет дубликаты с сохранением порядка и возвращает нормализованную строку вида `"MX, AU, RO"`. Нормализованная строка дополнительно проверяется на длину ≤ 255 (лимит `campaign_creation_logs.geo VARCHAR(255)`); иначе — `422`;
  - `offer_id`: целое `> 0`.
- **Тела редактора**: `AddOfferRequest` — `offer_id > 0`, `name` ≤ 255, `expected_revision` (опционально); `OfferPatch` — `is_deleted`, `is_pinned`, `pinned_share`, `state` ≤ 20, `expected_revision` (опционально).
- **Query-параметры** — через `Query(...)`: `q` (по умолчанию `""`, `max_length=150`), `limit` (`ge=1`, `le=200`, default 50).
- **Ошибки валидации** обрабатываются стандартным обработчиком FastAPI → **HTTP 422** и тело `{"detail": [{"loc": ..., "msg": ..., "type": ...}]}`. Своих `exception_handler` нет. Доменные валидаторы `name`/`geo` используют `PydanticCustomError`, поэтому `msg` содержит сразу русский текст без добавленного Pydantic префикса `Value error, ` (например, `Некорректные ISO-коды стран: ZH`).

### 5.4 Формирование ответов

Ответы объявлены через `response_model` (`CampaignOut`, `CampaignEditorOut`, `OfferOut`, `CampaignCreatedOut`, `CampaignHistoryOut`, `OfferSearchOut`, `HealthOut`) — это даёт корректную OpenAPI-схему и сериализацию дат. `GET /api/campaigns`, `GET /api/offers`, `GET /api/campaigns/history` и `GET /api/offers-remote` возвращают **bare list**.

Код успеха — стандартный **200** (201 не выставляется). Формат успешного создания не изменился:

```
{
  "success": true,
  "campaign": {"id": ..., "name": ..., "alias": ...},
  "streams": [{"id": ..., "name": "GEO - Google"}, {"id": ..., "name": "Default - Offer"}]
}
```

Детали кампании включают `id` (локальный) и `keitaro_id`; вложенные `streams[].offers[]` содержат `stream_id` (локальный) и `keitaro_stream_id`. В ответе `GET /api/offers` — `id` (локальный), `keitaro_id`, `campaign_id`, `stream_id`, `keitaro_stream_id`.

Все mutating-эндпоинты редактора (`load`, `discard`, `POST /streams/{id}/offers`, `PATCH /api/offers/{id}`) возвращают **полный** `CampaignEditorOut`, чтобы фронтенд заменял состояние одним `setState`. `CampaignEditorOut` расширяет `CampaignDetailOut` полями `keitaro_campaign_url`, `has_local_changes`, `last_loaded_at`, `last_pushed_at`, `last_sync_error`, `revision`, `warnings`; `StreamOut` — `comments`, `weight`, `is_deleted`, `origin`; `OfferOut` — `keitaro_offer_stream_id`, `is_deleted`, `is_pinned`, `pinned_share`, `origin`. Поля `base_*` наружу не отдаются.

`POST /sync/push` отвечает `SyncPushOut`: `{"success", "code", "campaign", "results": [{"stream_id", "keitaro_id", "status", "action", "code", "message"}]}`. Полный успех — `success=true`; частичный — HTTP 200 с `success=false`, `code="PARTIAL_SYNC"`; если не отправлен ни один изменённый поток — 502 `SYNC_FAILED` с `results` в `detail`.


### 5.5 Обработка ошибок

Ошибки транслируются централизованно в `app/api_errors.py` (`register_exception_handlers`), поэтому роутеры не содержат повторяющихся `try/except`:

| Источник | HTTP | `detail.code` | Доп. поля |
|---|---|---|---|
| `KeitaroError` (сеть, HTTP-ошибка Keitaro) | **502** | `KEITARO_API_ERROR` | `message` (включает HTTP-статус, метод/путь и текст ответа), `keitaro_status`, `keitaro_method`, `keitaro_path`, `details` |
| `PartialCreationError` | **502** | `PARTIAL_CREATION` | `message`, `campaign_id`, `google_stream_id` |
| `LocalPersistenceError` / `SQLAlchemyError` | **500** | `LOCAL_PERSISTENCE_ERROR` | `message` |
| `EditorError` с `KEITARO_INVALID_RESPONSE` (невалидный snapshot Keitaro) | **502** | `KEITARO_INVALID_RESPONSE` | `message` |
| Кампания не найдена (`/api/campaigns/{id}`, `/api/offers`) | **404** | `CAMPAIGN_NOT_FOUND` | `message` |
| Нет/неверный `API_AUTH_TOKEN` (если настроен) | **401** | `UNAUTHORIZED` | `message` |
| Бизнес-валидация создания (`ValueError`) | **400** | `CAMPAIGN_CREATION_ERROR` | `message` |
| Непредвиденное исключение | **500** | `INTERNAL_ERROR` | `message`; трассировка пишется в лог |
| Ошибка валидации Pydantic/Query | **422** | — (формат FastAPI) | — |
| `GET /api/admin/stream-actions`, `GET /api/offers-remote` при `KeitaroError` | **502** | `KEITARO_API_ERROR` | как выше |

Ошибки редактора (`EditorError`) содержат `code` и `message`, плюс контекст (например, `stream_id`, `has_local_changes`, `streams`, `results`):

| HTTP | `detail.code` | Когда |
|---|---|---|
| 404 | `STREAM_NOT_FOUND`, `OFFER_NOT_FOUND` | нет локальной строки |
| 409 | `LOCAL_CHANGES_PENDING` | load без `force` при наличии локальных правок |
| 409 | `REVISION_CONFLICT` | `expected_revision` не совпал |
| 409 | `STREAM_DELETED`, `OFFER_ALREADY_IN_STREAM` | добавление оффера в поток, помеченный Keitaro как удалённый / дубликат |
| 422 | `OFFER_NOT_ACTIVE` | оффер неактивен в Keitaro |
| 422 | `WEIGHT_VALIDATION_ERROR` | невалидные веса перед push (список в `streams`) |
| 422 | `PINNED_SHARE_*`, `ALL_PINNED_SUM_MISMATCH`, `NO_REMAINING_WEIGHT`, `INSUFFICIENT_REMAINING_WEIGHT` | невозможная комбинация весов |
| 502 | `SYNC_FAILED` | push: ни один изменённый поток не отправлен (`results` в `detail`) |
| 502 | `KEITARO_API_ERROR`, `REMOTE_CHANGED` (в `results[].code`) | ошибка Keitaro / поток изменён после загрузки |


Тело ошибки всегда обёрнуто в `{"detail": ...}` (стандарт FastAPI), но `detail` — объект с полем `code`, а не строка. Фронтенд (`frontend/src/App.jsx`) читает именно `detail.message`.

Внутри `KeitaroClient.request()` ошибки нормализуются: сетевые сбои `httpx.HTTPError` → `KeitaroError("Не удалось связаться с Keitaro (METHOD /path): ...")`; ответы `4xx/5xx` → `KeitaroError` с `status_code`, `method`, `path` и распарсенным телом (`json`, иначе текст). Текст ответа (до 1500 символов) добавляется прямо в `message`; если тело пустое, указывается `пустой ответ Keitaro`. Пустой успешный ответ → `None`; не-JSON тело → строка.

---

## 6. Сценарии выполнения (трассировка по коду)

### 6.1 Сценарий A — успешное создание кампании `POST /api/campaigns/create`

1. **Uvicorn → FastAPI.** `CORSMiddleware` проверяет Origin; запрос уходит в роутер, совпадает маршрут `create_campaign_endpoint` (`app/main.py`).
2. **Валидация.** Тело парсится в `CampaignCreate` (`app/schemas.py`). Например `{"name":" Test campaign ","geo":"MX, AU, RO","offer_id":123}` → `name="Test campaign"`, `geo="MX, AU, RO"`.
3. **DI.** `DbSession` (`app/deps.py` → `get_db`) открывает `AsyncSession`.
4. **Журнал (до внешних вызовов).** Создаётся `CampaignCreationLog(status="started")`, `db.add` → `db.commit()` → `db.refresh(log)` (commit #1).
5. **Клиент Keitaro.** `KeitaroClientDep` (`app/deps.py`) создаёт `httpx.AsyncClient` с `base_url=<KEITARO_BASE_URL>/admin_api/v1`, заголовком `Api-Key` и таймаутом `KEITARO_TIMEOUT`.
6. **Сервис, часть 1 — `create_campaign(api, name, geo, offer_id)`** (`app/services/creation.py`):
   1. `geo` разбивается по запятым на список ISO-кодов (`MX`, `AU`, `RO`).
   2. `GET /offers/{offer_id}` (`get_offer`) — оффер должен существовать и иметь `state == "active"` (при отсутствии поля считается активным).
   3. После проверки оффера независимые `GET /domains` (с пагинацией `list_all`), `GET /groups?type=campaigns`, `GET /traffic_sources` и `GET /streams_actions` выполняются параллельно через `asyncio.gather`. Источник трафика разрешается по имени `KEITARO_TRAFFIC_SOURCE_NAME` и передаётся как `traffic_source_id`.
   4. `find_by_name(domains, KEITARO_DOMAIN_NAME, "домен")`, `find_by_name(groups, KEITARO_GROUP_NAME, "группа кампаний")` и `find_by_name(sources, KEITARO_TRAFFIC_SOURCE_NAME, "источник трафика")` — точное совпадение имени без учёта регистра (`casefold`), ровно одно совпадение; иначе `ValueError`.
   5. Проверка `KEITARO_STREAM_ACTION_TYPE`: не пустой, не плейсхолдер `replace_with_action_key`, затем проверка вхождения ключа в множество `key` из `GET /streams_actions`. Иначе `ValueError` со списком доступных ключей.
   6. `POST /campaigns` с payload: `name` = `<CAMPAIGN_NAME_PREFIX><slug>`, `alias` = `<slug>_<6 hex>`, `type="position"`, `state="active"`, `domain_id` (int), `group_id` (**строка**), `traffic_source_id` (int).
   7. Возврат `CreatedCampaign(campaign={**payload, **ответ Keitaro}, context=CampaignContext(...))`. В `CampaignContext` сохраняются страны, `action_key`, выбранный оффер (снимок `GET /offers/{id}`) — всё, что нужно для потоков.
7. **Локальная запись кампании (commit #2).** `await save_campaign(db, created.campaign, log_id=log.id)` + `await db.commit()` — **сразу после** `POST /campaigns` и **до** создания потоков. Upsert по `keitaro_id`.
8. **Сервис, часть 2 — `create_campaign_streams(api, created)`** (`app/services/creation.py`):
   1. `POST /streams` №1 — GEO: `schema="redirect"`, `type="regular"`, `name="GEO - Google"`, `position=1`, `state="active"`, `action_type=<ключ>`, `action_payload="https://www.google.com/"`, `collect_clicks=true`, `filter_or=false`, `filters=[{name:"country", mode:"accept", payload:"MX AU RO"}]` (коды через пробел — требование Country-фильтра Keitaro). Любое исключение → `PartialCreationError` с уже созданной кампанией.
   2. `POST /streams` №2 — оффер: `schema="landings"`, `type="default"`, `name="Default - Offer"`, `position=2`, `state="active"`, `action_type=<ключ>`, `collect_clicks=true`, `offers=[{offer_id, share:100, state:"active"}]`, `offer_selection="before_click"`. Исключение → `PartialCreationError` с кампанией и GEO-потоком.
   3. Возврат `CreatedStreams(streams=[geo_stream, offer_stream], offers=[{stream: offer_stream, offer_id, share:100, state:"active", snapshot}])`. Снимок потока = `{**payload, **ответ}` (ответ имеет приоритет для `id`).
9. **Локальная запись потоков/офферов (commit #3).** `await save_streams_and_offers(db, campaign_row, result.streams, result.offers)` (внутри — upsert + `flush`, без commit), затем обработчик заполняет `keitaro_campaign_id`, `google_stream_id`, `offer_stream_id`, `status="success"` и делает один `db.commit()`.
10. **Очистка.** `get_keitaro_client` закрывает `httpx`-клиент в `finally`; `get_db` закрывает `AsyncSession`.

### 6.2 Сценарий B — частичное создание (поток не создался)

Если падает создание GEO-потока или потока оффера (HTTP-ошибка Keitaro, таймаут, отсутствие `id` в ответе и т.п.), `services/creation.py` оборачивает **ожидаемые** ошибки (`KeitaroError`, `ValueError`) в `PartialCreationError` с контекстом. Непредвиденные ошибки не маскируются: они логируются и дают `500 INTERNAL_ERROR`. Кампания к этому моменту уже сохранена (commit #2), поэтому обработчик:

- получает локальную кампанию через `get_campaign_by_keitaro_id`;
- сохраняет только фактически созданные потоки/офферы: `save_streams_and_offers(db, campaign_row, exc.streams, exc.offers)` (упал GEO-поток → пусто; упал поток оффера → только GEO-поток, без офферов);
- сохраняет `keitaro_campaign_id` и, если есть, `google_stream_id`; ставит `status="partial"`, пишет `error_message`;
- **не выполняет откат в Keitaro** — кампания/поток остаются;
- отвечает **502** `{"code":"PARTIAL_CREATION", "campaign_id":..., "google_stream_id":...}`.

Потоки/офферы и обновление журнала коммитятся одной транзакцией. Это осознанное поведение, зафиксированное в README.

### 6.3 Сценарий C — ошибка Keitaro, бизнес-валидация или ошибка локальной записи

- `KeitaroError` из `create_campaign()` (до/во время `POST /campaigns`) → `log.status="failed"`, `error_message` (с `details`, если есть) → **502** `KEITARO_API_ERROR`. Локальных сущностей нет.
- `ValueError` из `create_campaign()` (оффер неактивен, домен/группа не найдены или неоднозначны, неверный `KEITARO_STREAM_ACTION_TYPE`, отсутствует `id` кампании в ответе) → `status="failed"` → **400** `CAMPAIGN_CREATION_ERROR`. Локальных сущностей нет.
- `LocalPersistenceError` при сохранении кампании → `db.rollback()`, `create_campaign_streams()` **не вызывается** (потоки в Keitaro не создаются), best-effort `status="partial"` с `keitaro_campaign_id` → **500** `LOCAL_PERSISTENCE_ERROR`.
- `LocalPersistenceError` при сохранении потоков/офферов → `db.rollback()` только этой транзакции (кампания остаётся в БД), best-effort `status="partial"` → **500** `LOCAL_PERSISTENCE_ERROR`.
- `KeitaroError`/`ValueError` из `create_campaign_streams()` оборачивается сервисом в `PartialCreationError` → сценарий B.
- Любое непредвиденное исключение логируется (`logger.exception`), журнал переводится в `failed`/`partial`, API отвечает **500** `INTERNAL_ERROR`. Это не маскируется под `400`.

Восстановление после `LOCAL_PERSISTENCE_ERROR` — идемпотентный бэкфилл/синхронизация из Keitaro (§11.2), либо повторный вызов с upsert. Сущности в Keitaro не откатываются.

### 6.4 Сценарий D — поиск офферов в Keitaro `GET /api/offers-remote?q=...`

1. `KeitaroClient.offers()` (`app/keitaro.py`) вызывает `_offer_catalogue()`, который кэширует `GET /offers` в памяти процесса на `KEITARO_OFFERS_CACHE_TTL` секунд (по умолчанию 30; `0` отключает кэш).
2. `list_all` листает `GET /offers?offset=N&limit=500`, пока страница не вернёт меньше 500 элементов; если ответ — объект-обёртка (`{"data": [...]}`), он разворачивается, не-словарные элементы отбрасываются.
3. Локально оставляются только элементы с `state == "active"` (отсутствие `state` трактуется как `active`).
4. В маршруте `search_offers_remote` `q` приводится к `casefold()`, оффер проходит, если подстрока входит в `name` **или** в `id`; берутся первые 50; на выходе `[{"id": int, "name": str}]`, где `id` — **Keitaro ID** (фронтенд отправляет его как `offer_id`).
5. Пустой `q` совпадает со всеми → возвращаются первые 50 активных офферов.

Фильтрация сделана на стороне backend, а не в Keitaro, — комментарий в коде объясняет это «консистентностью».

### 6.5 Сценарий E — история `GET /api/campaigns/history`

Асинхронный `async def`-эндпоинт: `repositories.list_creation_logs` выполняет `SELECT ... ORDER BY id DESC LIMIT :limit` и возвращает ORM-строки, сериализуемые через `CampaignHistoryOut`. Читает только локальную БД, к Keitaro не обращается. Объявлен до `/{campaign_id}`, поэтому `history` не перехватывается как ID.

### 6.6 Сценарий F — локальное чтение `/api/campaigns`, `/api/campaigns/{id}`, `/api/offers`

- `GET /api/campaigns` — `repositories.campaigns.list_campaigns`: фильтры `q` (подстрока в `name`/`alias`) и `state` (точное совпадение), сортировка `created_at DESC, id DESC`, `limit` 1..200, `offset` ≥ 0.
- `GET /api/campaigns/{campaign_id}` — `repositories.campaigns.get_campaign` с `selectinload(streams → offers)`, чтобы не было N+1. Локальный ID; при отсутствии — 404 `CAMPAIGN_NOT_FOUND`. Кампания без потоков отдаётся с пустым `streams`.
- `GET /api/offers?campaign_id=` — `repositories.campaigns.list_offers`: join `streams`, фильтр по `campaign_id` и подстроке в `name`/`keitaro_id`, `keitaro_stream_id` вычисляется из связи. Отсутствие кампании → 404 (отличается от «кампания есть, офферов нет»), отсутствие `campaign_id` → 422.

### 6.7 Различия способов обработки

Принципиально есть три типа обработчиков:

1. **Проброс к Keitaro** (`/api/admin/stream-actions`, `/api/offers-remote`) — без БД, ответ формируется из данных трекера.
2. **Оркестрация с записью состояния** (`/api/campaigns/create`) — единственный эндпоинт с журналом, внешними вызовами Keitaro и многошаговой компенсацией ошибок.
3. **Чисто локальное чтение** (`/api/campaigns`, `/api/campaigns/{id}`, `/api/offers`, `/api/campaigns/history`) — только БД, выполняется асинхронно (без threadpool).

---

## 7. Работа с данными

### 7.1 СУБД и подключение

`app/database.py`:

- `create_async_engine(async_database_url(settings.database_url), pool_pre_ping=True)`; `sqlite://` автоматически превращается в `sqlite+aiosqlite://`, `postgresql://` — в `postgresql+asyncpg://`;
- для SQLite на событии `connect` (`engine.sync_engine`) выполняются `PRAGMA foreign_keys=ON` и `PRAGMA busy_timeout=5000`;
- `SessionLocal = async_sessionmaker(..., class_=AsyncSession, autoflush=False, expire_on_commit=False)` — async-сессии на запрос;
- `get_db()` — async-генератор: отдаёт `AsyncSession`, делает `rollback` при исключении и закрывает сессию в `finally`.

`DATABASE_URL` по умолчанию: `sqlite:///backend/campaign_creator.db` — абсолютный путь от каталога `backend/`, не зависит от текущего рабочего каталога процесса. Для PostgreSQL используйте `postgresql+asyncpg://...`.

### 7.2 Модель

Четыре таблицы (`app/models.py`). Существующая `campaign_creation_logs` не изменялась:

| Колонка | Тип | Примечание |
|---|---|---|
| `id` | INTEGER PK | автоинкремент |
| `campaign_name` | VARCHAR(255), NOT NULL | имя кампании из запроса |
| `geo` | VARCHAR(255), NOT NULL | нормализованная строка GEO |
| `offer_id` | INTEGER, NOT NULL | ID оффера Keitaro |
| `keitaro_campaign_id` | INTEGER, NULL | ID созданной кампании |
| `google_stream_id` | INTEGER, NULL | ID GEO-потока |
| `offer_stream_id` | INTEGER, NULL | ID потока оффера |
| `status` | VARCHAR(20), NOT NULL, default `started` | `started` / `success` / `partial` / `failed` |
| `error_message` | TEXT, NULL | текст ошибки (для `KeitaroError` — с `details`) |
| `created_at` | DATETIME (timezone=True), NOT NULL | `datetime.now(timezone.utc)` по умолчанию |

`campaigns` — снимок кампании Keitaro:

| Колонка | Тип | Ограничения | Примечание |
|---|---|---|---|
| `id` | INTEGER | PK | локальный ID |
| `keitaro_id` | INTEGER | NOT NULL, UNIQUE, index | ID кампании в Keitaro |
| `name` | VARCHAR(255) | NOT NULL | из payload/ответа |
| `alias` | VARCHAR(64) | NULL | из payload/ответа |
| `type` | VARCHAR(32) | NULL | `position` |
| `state` | VARCHAR(20) | NULL | `active` |
| `domain_id` | INTEGER | NULL | ID домена Keitaro |
| `group_id` | VARCHAR(64) | NULL | Keitaro ожидает строку |
| `traffic_source_id` | INTEGER | NULL | ID источника трафика Keitaro |
| `campaign_creation_log_id` | INTEGER | FK → `campaign_creation_logs.id` ON DELETE SET NULL, index | трассировка операции |
| `raw` | JSON | NULL | payload + ответ Keitaro |
| `last_loaded_at` / `last_pushed_at` | DATETIME(tz) | NULL | последняя успешная загрузка/отправка (редактор) |
| `last_sync_error` | TEXT | NULL | причина последней неудачной синхронизации |
| `revision` | INTEGER | NOT NULL, default 0 | растёт при каждой локальной мутации и после успешного/частичного push; optimistic concurrency для всех мутаций |
| `created_at` / `updated_at` | DATETIME(tz) | NOT NULL | UTC; `updated_at` обновляется при upsert |

`streams` — снимок потока:

| Колонка | Тип | Ограничения | Примечание |
|---|---|---|---|
| `id` | INTEGER | PK | локальный ID |
| `keitaro_id` | INTEGER | NOT NULL | ID потока |
| `campaign_id` | INTEGER | NOT NULL, FK → `campaigns.id` ON DELETE CASCADE, index | владелец |
| `name` | VARCHAR(255) | NOT NULL | `GEO - Google` / `Default - Offer` |
| `type` | VARCHAR(32) | NULL | `regular` / `default` |
| `schema` | VARCHAR(32) | NULL | `redirect` / `landings` |
| `position` | INTEGER | NULL | 1 / 2 |
| `state` | VARCHAR(20) | NULL | `active` / `disabled` / `deleted` |
| `action_type` | VARCHAR(64) | NULL | ключ действия |
| `action_payload` | TEXT | NULL | URL редиректа |
| `raw` | JSON | NULL | payload + ответ Keitaro |
| `comments` / `weight` | TEXT / FLOAT | NULL | дополнительные поля потока из Keitaro |
| `keitaro_updated_at` | VARCHAR(32) | NULL | `updated_at` из Keitaro; используется для `REMOTE_CHANGED` |
| `is_deleted` | BOOLEAN | NOT NULL, default false | заполняется только при загрузке из Keitaro (поток удалён/отсутствует); из приложения не меняется |
| `origin` | VARCHAR(16) | NOT NULL, default `keitaro` | `keitaro` / `local` |
| `base_state` / `base_is_deleted` | VARCHAR(20) / BOOLEAN | NULL / NOT NULL default false | базовая линия (последнее подтверждённое состояние Keitaro); для потоков ведётся для полноты снимка |
| `created_at` / `updated_at` | DATETIME(tz) | NOT NULL | UTC |


Уникальность: `(campaign_id, keitaro_id)`.

`offers` — снимок оффера **в разрезе потока**:

| Колонка | Тип | Ограничения | Примечание |
|---|---|---|---|
| `id` | INTEGER | PK | локальный ID |
| `keitaro_id` | INTEGER | NOT NULL | ID оффера в Keitaro |
| `campaign_id` | INTEGER | NOT NULL, FK → `campaigns.id` ON DELETE CASCADE, index | денормализация, всегда из `stream.campaign_id` |
| `stream_id` | INTEGER | NOT NULL, FK → `streams.id` ON DELETE CASCADE, index | владелец |
| `name` | VARCHAR(255) | NULL | снимок из `GET /offers/{id}` |
| `state` | VARCHAR(20) | NULL | `active` |
| `share` | INTEGER | NULL | текущий вес, % (сумма активных = 100) |
| `raw` | JSON | NULL | снимок оффера Keitaro |
| `keitaro_offer_stream_id` | INTEGER | NULL | `OfferStream.id`; только диагностика, не ключ сопоставления |
| `is_deleted` | BOOLEAN | NOT NULL, default false | мягкое удаление предложения из потока |
| `is_pinned` / `pinned_share` | BOOLEAN / INTEGER | NOT NULL default false / NULL | закреплённый вес (локальные метаданные, в Keitaro не отправляются) |
| `origin` | VARCHAR(16) | NOT NULL, default `keitaro` | `keitaro` / `local` (добавлен пользователем, ещё не отправлен) |
| `base_share` / `base_state` / `base_is_deleted` | INTEGER / VARCHAR(20) / BOOLEAN | NULL / NULL / NOT NULL default false | базовая линия |
| `created_at` / `updated_at` | DATETIME(tz) | NOT NULL | UTC |

Уникальность: `(stream_id, keitaro_id)`. Один и тот же оффер Keitaro в двух кампаниях/потоках = две строки. Глобального каталога офферов нет.

Редактор разделяет **рабочее состояние** (`share`, `state`, `is_deleted`, `is_pinned`) и **базовую линию** (`base_*` — последнее подтверждённое состояние Keitaro). Признак «есть несинхронизированные изменения» вычисляется сравнением этих полей (`campaign_has_local_changes`), а не хранится флагом. `origin='local'` означает, что предложение добавлено пользователем и ещё не отправлено; после успешного push становится `keitaro`.

Поля `is_deleted`/`base_is_deleted` у **потоков** не являются пользовательской функцией: удаление и восстановление потоков из API/UI не поддерживаются. Они заполняются только `apply_remote_snapshot` (поток пришёл со `state="deleted"` или исчез из ответа Keitaro) и используются для отображения и guard'а при добавлении оффера. Редактируемыми остаются только офферы.


### 7.3 Репозиторий и доступ к данным

`app/repositories/` — единственное место записи/чтения кэширующих сущностей. Все функции async и принимают `AsyncSession`:

- `campaigns.save_campaign(db, data, log_id=...)` — upsert по `keitaro_id`; вызывается сервисом и коммитится **сразу** после `POST /campaigns`;
- `campaigns.save_streams_and_offers(db, campaign, streams, offers)` — upsert потоков и офферов, **без commit** (коммит вместе с обновлением журнала); офферы ищут уже upsert-нутый поток по `keitaro_id`;
- `campaigns.upsert_stream`, `upsert_stream_offers` — низкоуровневые upsert'ы;
- `campaigns.get_campaign`, `get_campaign_by_keitaro_id`, `campaign_exists` — чтение одной кампании (детали — с `selectinload(streams → offers)`);
- `editor.get_stream`, `get_offer`, `find_offer` — чтение потока/оффера для редактора (включая мягко удалённые);
- `editor.create_offer` — вставка локально добавленного оффера (`origin='local'`);
- `editor.apply_remote_snapshot` — применение снимка Keitaro: upsert, заполнение `base_*`, soft delete отсутствующих потоков/офферов; если у потока в ответе **нет ключа `offers`** или список частично невалиден (частичный снимок), офферы не удаляются и добавляется `warning`; пустой ответ даёт `warning`;
- `editor.reset_to_baseline` — откат к `base_*`; физически удаляет только `origin='local'` без `keitaro_offer_stream_id`;
- `editor.commit_stream_baseline` — после успешного push одного потока: `base_*`, `keitaro_offer_stream_id`, `keitaro_updated_at`, `last_pushed_at`. Если в ответе `PUT` нет `updated_at`, значение перезапрашивается через `GET /streams/{id}`; если и там нет — пишется `NULL`, чтобы не сравнивать с устаревшей меткой;
- `editor.bump_revision` — инкремент `revision` с compare-and-swap по `expected_revision`; при гонке — `RevisionConflictError` → `409`;
- `changes.campaign_has_local_changes` — вычисляемый признак грязного состояния. Учитывает только офферы (потоки не редактируются из приложения);
- `campaigns.list_campaigns`, `list_offers`, `list_creation_logs` — списки с пагинацией и фильтрами;
- `LocalPersistenceError` — обёртка над `SQLAlchemyError` (и нарушением обязательных полей), несёт необязательный `campaign`.

Правила:

- поля из ответа Keitaro имеют приоритет над отправленным payload (снимок = `{**payload, **response}`);
- отсутствующие необязательные поля пишутся как `NULL`; обязательные (`keitaro_id`/`id`, `name`, `campaign_id`, `stream_id`) при отсутствии дают `LocalPersistenceError`;
- маппинг Stream/Offer вынесен в `repositories/mapping.py`, поэтому создание и загрузка используют одни правила;
- `campaign_id` оффера никогда не берётся из внешних данных — только из `stream.campaign_id`;
- несериализуемое в JSON значение `raw` превращается в `NULL`;
- async ORM не допускает ленивых обращений: `get_campaign`/`get_stream`/`get_offer` явно загружают нужные связи, а `_reload_campaign_graph` гарантирует загруженный граф перед snapshot/reset.

Транзакционность: журнал `started` → кампания (commit #2) → потоки/офферы + финальный статус журнала (commit #3). Атомарности «всё или ничего» между Keitaro и БД нет — компенсация через идемпотентный upsert/бэкфилл.

### 7.4 Миграции

Alembic не используется. Схема создаётся/дополняется при старте приложения в `lifespan` (`app/main.py`), а не при импорте модуля:

```python
if settings.auto_migrate:
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)  # отсутствующие таблицы
    await ensure_schema(engine)                         # недостающие колонки + бэкфилл
```

Для нескольких воркеров DDL лучше выполнить один раз и отключить авто-миграции:

```bash
python -m scripts.init_db
AUTO_MIGRATE=false uvicorn app.main:app --workers 4
```

`app/migrations.py` (`ensure_schema`) — лёгкая идемпотентная миграция:

- список новых колонок зафиксирован в `COLUMNS`; уже существующие пропускаются;
- DDL транслируется под диалект: `DATETIME → TIMESTAMP`, а `DEFAULT 0 → DEFAULT FALSE` только для `BOOLEAN`-колонок (`revision INTEGER NOT NULL DEFAULT 0` сохраняет числовой default);
- бэкфилл baseline выполняется **только для колонок, добавленных в этом запуске**: `base_share = share`, `base_state = state`, `base_is_deleted = is_deleted`, `origin = 'keitaro'`. Повторный старт на уже обновлённой базе ничего не перезаписывает, поэтому несинхронизированные правки (например, локальное удаление оффера) не становятся частью baseline;
- колонки не удаляются и не переименовываются.

Ограничения: `ALTER TABLE ADD COLUMN` в SQLite не поддерживает `UNIQUE`/`FOREIGN KEY`, а изменение типа или удаление колонки по-прежнему требует ручной миграции.


---

## 8. Безопасность

### 8.1 Аутентификация и авторизация

- **Опциональная аутентификация по общему токену.** Если задан `API_AUTH_TOKEN`, middleware требует `X-API-Token` или `Authorization: Bearer <token>` на всех маршрутах `/api/*`, кроме `/api/health`; иначе — **401** `UNAUTHORIZED`. Сравнение выполняется через `secrets.compare_digest`.
- Если `API_AUTH_TOKEN` пуст (значение по умолчанию для локальной разработки), API открыт: любой, кто может достучаться до сервиса, может создавать кампании и менять потоки от имени серверного API-ключа Keitaro. Для любого развёртывания вне localhost токен обязателен (или аутентификация на reverse-proxy).
- **CORS** (`CORS_ORIGINS`) ограничивает только браузерные cross-origin запросы и не является механизмом авторизации.
- Авторизация в Keitaro выполняется на сервере: `Api-Key` в заголовке, ключ берётся из `KEITARO_API_KEY` (`app/keitaro.py`). В браузер ключ не попадает — это и есть основная цель проксирования. Токен API в браузер тоже не встраивается: его добавляет reverse-proxy, обслуживающий SPA.

### 8.2 Секреты и чувствительные данные

- Секреты хранятся в `backend/.env` (файл в `.gitignore`) и читаются `pydantic-settings`. `backend/.env.example` содержит только плейсхолдеры.
- SQLite-база `backend/campaign_creator.db` — runtime-артефакт: она исключена из git (`*.db`) и не должна коммититься.
- API-ключ Keitaro **никогда не логируется** и не возвращается в ответах; в `error_message` и в `detail` попадают только сообщения/`details` ответа Keitaro, которые могут содержать служебную информацию трекера.
- Ответы Keitaro пробрасываются в `GET /api/admin/stream-actions` без фильтрации — это административные данные, доступные клиенту API (см. 8.1).

### 8.3 Защита API

Реализовано: опциональный общий токен (8.1), ограничения длины/типа входных данных (Pydantic, `Query(max_length=...)`), таймаут внешних запросов (`KEITARO_TIMEOUT`, default 20 с), валидация ISO-кодов (нельзя передать произвольный payload в фильтр), сравнение токена без утечки по времени.

Не реализовано: роли/права, rate limiting, аудит-логи запросов, ограничение размера тела запроса, HTTPS-терминация, CSRF-защита, idempotency-ключи. README прямо предупреждает, что дубликаты кликов предотвращаются только в UI и для продакшена нужен idempotency key / таблица уникальных запросов.

---

## 9. Внешние интеграции

### 9.1 Keitaro Admin API

Клиент: `app/keitaro.py` (`httpx.AsyncClient`). База: `{KEITARO_BASE_URL}/admin_api/v1`. Заголовки: `Api-Key`, `Content-Type: application/json`.

| Метод клиента | HTTP-запрос | Где используется |
|---|---|---|
| `offers()` | `GET /offers` (пагинация по 500, кэш процесса) + локальный фильтр `state=active` | `GET /api/offers-remote` |
| `get_offer(id)` | `GET /offers/{id}` | проверка оффера и снимок для локальной БД при создании |
| `domains()` | `GET /domains` (пагинация) | поиск домена по имени |
| `groups()` | `GET /groups?type=campaigns` | поиск группы кампаний по имени |
| `traffic_sources()` | `GET /traffic_sources` | поиск источника трафика по имени, `traffic_source_id` |
| `stream_actions()` | `GET /streams_actions` | валидация `KEITARO_STREAM_ACTION_TYPE`, эндпоинт админ-просмотра |
| `create_campaign(payload)` | `POST /campaigns` | создание кампании |
| `create_stream(payload)` | `POST /streams` | создание двух потоков |
| `campaign_streams(id)` | `GET /campaigns/{id}/streams` | загрузка снимка в редакторе, бэкфилл |
| `get_stream(id)` | `GET /streams/{id}` | проверка `REMOTE_CHANGED` перед push |
| `update_stream(id, payload)` | `PUT /streams/{id}` | отправка массива `offers` из редактора |
| `offers_all()` | `GET /offers` (пагинация) без фильтра `active` | карта `id → name` при загрузке |
| `get_campaign(id)` | `GET /campaigns/{id}` | опциональный бэкфилл (`scripts/backfill_campaigns.py`) |
| `list_all(path)` | цикл `GET path?offset&limit` | универсальная пагинация |

Важно: основной поток создания **не делает дополнительных GET-запросов** — для сохранения достаточно ответов на `POST /campaigns` и `POST /streams` плюс уже полученного снимка оффера. Так как `POST /streams` может вернуть только `{"id": ...}`, снимок строится как `{**payload, **ответ}`.

Особенности:

- Пагинация `list_all` прекращается, когда страница вернула меньше `page_size` (500), либо если ответ не список (тогда он возвращается как есть без агрегации).
- Каталог офферов кэшируется на `KEITARO_OFFERS_CACHE_TTL` секунд (по умолчанию 30); кэш общий для автокомплита и загрузки снимка. Остальные ответы не кэшируются.
- Нет retry/backoff и ограничения конкурентности.
- `GET /groups` вызывается с query-параметром `type=campaigns`; форма ответа (список или объект-обёртка) по коду не проверяется — `find_by_name` ожидает список словарей с полем `name`. **Достоверно не подтверждено** без обращения к реальному инстансу Keitaro.

### 9.2 Очереди, фоновые задачи, кэш

Очередей и фоновых задач нет: все внешние вызовы выполняются в рамках HTTP-запроса (асинхронно, без очередей). Ни Celery/RQ, ни `BackgroundTasks`, ни Redis в проекте нет. Локальная БД выполняет роль кэша созданных сущностей (`campaigns`/`streams`/`offers`), а каталог офферов Keitaro кэшируется в памяти процесса на `KEITARO_OFFERS_CACHE_TTL` секунд. Периодической сверки с Keitaro нет — только ручной бэкфилл.

---

## 10. Ключевые бизнес-модули и правила

### 10.1 Создание кампании (`app/services/creation.py`)

Правила, реализованные в коде:

- **Проверка оффера**: `GET /offers/{id}` должен вернуть объект с `state="active"`; иначе `ValueError("Оффер не найден или неактивен")`. Тот же объект сохраняется в `CampaignContext.offer` и затем в `offers.raw`.
- **Разрешение сущностей по имени**: домен и группа кампаний ищутся по точному имени из конфигурации (`KEITARO_DOMAIN_NAME`, `KEITARO_GROUP_NAME`), регистронезависимо. Ноль совпадений — ошибка; несколько совпадений — ошибка неоднозначности. ID подставляются в payload: `domain_id` как `int`, `group_id` как `str`.
- **Источник трафика**: домен, группа кампаний и источник трафика ищутся по точному имени из конфигурации (`KEITARO_DOMAIN_NAME`, `KEITARO_GROUP_NAME`, `KEITARO_TRAFFIC_SOURCE_NAME`), регистронезависимо; ID подставляются в payload (`domain_id` как `int`, `traffic_source_id` как `int`, `group_id` как `str`).
- **Имя и alias кампании**: `campaign_name(name)` = `<CAMPAIGN_NAME_PREFIX>` + `slugify(name, max_length=45)`; `campaign_alias(name)` = `slugify(name, max_length=45)` + `_` + 6 hex-символов (`secrets.token_hex(3)`). Alias URL-безопасен и укладывается в `VARCHAR(64)`; уникальность обеспечивает случайный суффикс.
- **Проверка ключа действия**: `KEITARO_STREAM_ACTION_TYPE` обязателен, не должен быть плейсхолдером и должен присутствовать среди `key` из `GET /streams_actions`. Проверка выполняется на каждый запрос создания.
- **Разделение на две функции**: `create_campaign()` (валидация + `POST /campaigns`, возвращает `CreatedCampaign`) и `create_campaign_streams()` (два `POST /streams` + снимок оффера, возвращает `CreatedStreams`). Сервис не знает о `Session`; порядок «сохранить кампанию → создать потоки» обеспечивает обработчик.
- **GEO-фильтр**: список кодов из `geo` (после валидации) склеивается **через пробел** и передаётся в `filters[0].payload` при `name="country"`, `mode="accept"`, `filter_or=false`.
- **Поток оффера**: 100% (`share: 100`) на выбранный оффер, выбор оффера до клика (`offer_selection="before_click"`), схема `landings`.
- **Снимки**: кампания и поток = `{**payload, **ответ}`; оффер = снимок `GET /offers/{id}` + поля из payload (`offer_id`, `share`, `state`).
- **Политика частичного успеха**: при ошибке создания потока сущности в Keitaro не откатываются; любое исключение оборачивается в `PartialCreationError` с `campaign`, `streams` (фактически созданные) и `offers`.

### 10.2 Журнал операций (`app/main.py` + `app/models.py`)

Каждая попытка создания кампании порождает запись со статусом `started` **до** обращения к Keitaro. Далее статус меняется на `success` / `partial` / `failed`, заполняются ID и `error_message`. Это единственный источник истории; отдельного аудита действий пользователя нет.

### 10.3 Поиск офферов (`app/main.py`)

- `GET /api/offers-remote` — локальная фильтрация активных офферов Keitaro и подстрочный поиск по имени/ID; каталог офферов кэшируется на `KEITARO_OFFERS_CACHE_TTL` секунд, лимит выдачи 50. Используется фронтендом для автокомплита (debounce 250 мс на стороне UI). `id` — Keitaro ID.
- `GET /api/offers?campaign_id=` — только локальная БД, офферы одной кампании; `id` — локальный, `keitaro_id` — Keitaro ID. Для автокомплита не используется.

### 10.4 Редактор кампании (`app/services/editor.py`, `app/weights.py`)

**Веса.** `distribute_shares(offers)` учитывает только активные предложения (`is_deleted == false` и `state == "active"`). Закреплённые (`is_pinned`) сохраняют `pinned_share` без изменений; остаток `100 - сумма(pinned)` делится между незакреплёнными целочисленно, остаток раздаётся последним по `Offer.id`. Сумма всегда ровно 100. Невозможные комбинации дают `WeightError` с кодом (`PINNED_SHARE_OVERFLOW`, `ALL_PINNED_SUM_MISMATCH`, `NO_REMAINING_WEIGHT`, `INSUFFICIENT_REMAINING_WEIGHT`, `PINNED_SHARE_OUT_OF_RANGE`, `PINNED_SHARE_MISSING`), и операция откатывается — невалидные веса не попадают в БД.

**Локальные мутации** (`add_offer`, `patch_offer`, `discard`) меняют только локальную БД и не пишут в Keitaro. Все мутации принимают `expected_revision` и при расхождении отвечают `409 REVISION_CONFLICT` до записи; успешная мутация увеличивает `revision`. Потоки не редактируются и не удаляются из приложения: их состояние (`state`, `is_deleted`) приходит только из Keitaro при загрузке. `POST /streams/{id}/offers` дополнительно делает `GET /offers/{id}` для проверки активности. Удаление оффера — всегда soft delete (`is_deleted`), строки не удаляются физически; повторное добавление восстанавливает существующую строку благодаря `UNIQUE (stream_id, keitaro_id)`.

**Загрузка (`POST /sync/load`).** Сначала все `await` к Keitaro (`GET /campaigns/{id}/streams`, каталог `/offers` из кэша), затем одна транзакция: `apply_remote_snapshot` upsert'ит строки, обновляет `base_*` и помечает отсутствующие потоки/офферы удалёнными. Если у потока в ответе нет ключа `offers`, его офферы не трогаются, а в `warnings` добавляется предупреждение. При наличии локальных правок без `force` — 409 `LOCAL_CHANGES_PENDING` и БД не меняется; с `force` сначала выполняется `reset_to_baseline`. Ошибка Keitaro → 502 без изменений в БД.

**Отправка (`POST /sync/push`).** Перед первым HTTP-запросом валидируются веса всех изменённых потоков и проверяется `expected_revision`. Для каждого изменённого потока выполняется `PUT /streams/{id}` с `{"offers": [...]}`; `DELETE`/`restore` потоков не используются. Локально удалённые офферы исключаются из массива; `disabled` отправляются с `share=0`. Поток, в котором удалены все офферы, **отправляется с пустым массивом** `{"offers": []}` — это разрешено и очищает офферы потока в Keitaro. После успешного ответа baseline фиксируется **отдельным commit для этого потока**, а `keitaro_updated_at` обновляется из ответа `PUT` или перезапрашивается через `GET /streams/{id}` (если Keitaro вернул минимальный ответ). Упавший поток остаётся «грязным». Если не отправлен ни один изменённый поток — 502 `SYNC_FAILED`; частичный успех — 200 с `success=false`. После успешного или частичного push `revision` увеличивается, чтобы другие вкладки получили `REVISION_CONFLICT`. С `force=false` перед `PUT` сверяется `updated_at` потока (если он известен) и при расхождении возвращается `REMOTE_CHANGED`.

**Отмена (`POST /sync/discard`).** Восстанавливает у офферов `share`/`state`/`is_deleted` из `base_*`, снимает pin; физически удаляет только локально добавленные предложения (`origin='local'` и без `keitaro_offer_stream_id`).


---

## 11. Конфигурация и запуск

### 11.1 Переменные окружения (`app/config.py`, `.env.example`)

| Переменная | Обязательна | Значение по умолчанию | Назначение |
|---|---|---|---|
| `KEITARO_BASE_URL` | **да** | — | Базовый URL трекера (без `/admin_api/v1`) |
| `KEITARO_API_KEY` | **да** | — | API-ключ Keitaro (заголовок `Api-Key`) |
| `KEITARO_STREAM_ACTION_TYPE` | **да** | — | Ключ действия потока из `GET /streams_actions`, например `http` |
| `KEITARO_DOMAIN_NAME` | **да** | — | Имя домена для привязки кампании |
| `KEITARO_GROUP_NAME` | **да** | — | Имя группы кампаний |
| `KEITARO_TRAFFIC_SOURCE_NAME` | **да** | — | Имя источника трафика |
| `KEITARO_TIMEOUT` | нет | `20` (float) | Таймаут запросов к Keitaro, сек |
| `KEITARO_OFFERS_CACHE_TTL` | нет | `30` (float) | Время жизни кэша каталога офферов, сек; `0` отключает кэш |
| `DATABASE_URL` | нет | `sqlite:///<backend>/campaign_creator.db` | DSN SQLAlchemy; путь по умолчанию абсолютный (от каталога `backend/`) |
| `CORS_ORIGINS` | нет | `http://localhost:5173` | Список Origin через запятую |
| `API_AUTH_TOKEN` | нет | пусто | Общий токен для `/api/*` (кроме `/api/health`); пусто — без аутентификации |
| `AUTO_MIGRATE` | нет | `true` | Выполнять `create_all`/`ensure_schema` при старте |
| `CAMPAIGN_NAME_PREFIX` | нет | `test_` | Префикс имени создаваемой кампании |

Конфигурация читается из `backend/.env` (абсолютный путь) и `.env` в рабочем каталоге (`SettingsConfigDict(env_file=(BASE_DIR / ".env", ".env"), extra="ignore")`). Неизвестные переменные игнорируются. Keitaro-поля объявлены опциональными на этапе импорта, чтобы `python -m scripts.init_db` работал без трекера; `Settings.require_keitaro()` вызывается в `lifespan` приложения и в `KeitaroClient.__init__`, поэтому при старте API или первом обращении к Keitaro отсутствие переменной даёт понятную ошибку.

### 11.2 Запуск

Согласно README и структуре проекта:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env      # заполнить KEITARO_BASE_URL, KEITARO_API_KEY, KEITARO_STREAM_ACTION_TYPE, DATABASE_URL
uvicorn app.main:app --reload
```

- ASGI-приложение: `app.main:app` (`app/main.py`).
- Порт по умолчанию — 8000 (значение uvicorn; в проекте не задаётся).
- При старте в `lifespan` выполняются `create_all` и `ensure_schema` (если `AUTO_MIGRATE=true`); файл SQLite создастся автоматически. Для нескольких воркеров: `python -m scripts.init_db` + `AUTO_MIGRATE=false`.
- Фронтенд (`frontend/`) проксирует `/api` на `http://127.0.0.1:8000` (`frontend/vite.config.ts`); явный IPv4 предотвращает попадание в чужие сервисы на `[::1]:8000`.

### 11.3 Окружения и развёртывание

Разделения конфигураций по окружениям (dev/staging/prod) в коде нет — один `.env`. Также отсутствуют `Dockerfile`, `docker-compose`, CI-конфиги, systemd/Procfile, конфигурация reverse proxy. Для продакшена README рекомендует PostgreSQL через `DATABASE_URL` (драйвер `asyncpg` включён в `requirements.txt`), предупреждает о недопустимости раскрытия ключа Keitaro в браузере и требует задать `API_AUTH_TOKEN` (либо аутентификацию на прокси), если сервис доступен не только с localhost.

### 11.4 Первичная настройка ключа действия

Порядок из README: запустить backend → открыть `GET /api/admin/stream-actions` (или `GET /admin_api/v1/streams_actions` в Keitaro) → выбрать `key`, соответствующий прямому HTTP-редиректу в конкретной инсталляции → прописать в `KEITARO_STREAM_ACTION_TYPE`. Значение зависит от версии/конфигурации Keitaro, поэтому в коде оно не угадывается.

---

## 12. Тестирование

Инфраструктура тестов добавлена:

- `backend/tests/` (`conftest.py`, `test_creation.py`, `test_read_api.py`, `test_repository.py`, `test_migrations.py`, `test_weights.py`, `test_repository_editor.py`, `test_editor_api.py`, `test_sync_load.py`, `test_sync_push.py`, `test_auth.py`, `test_keitaro.py`, `test_service.py`, `test_schemas.py`, `test_config.py`, `test_database.py`, вспомогательные билдеры в `editor_helpers.py`);
- dev-зависимости: `pytest`, `pytest-asyncio`, `respx` в `backend/requirements-dev.txt`;
- `backend/pytest.ini`;
- тестовая БД — временный SQLite-файл (async `aiosqlite`), API-тесты используют `httpx.ASGITransport`, Keitaro замокан через `respx` (сеть не используется). `pytest.ini` включает `asyncio_mode=auto`.

Запуск:

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Покрыто: успешное создание (1 кампания / 2 потока / 1 оффер и связи), порядок «кампания закоммичена до создания потоков», идемпотентный повторный upsert, partial при падении GEO-потока и потока оффера, ошибка Keitaro до создания кампании, обе ветки `LOCAL_PERSISTENCE_ERROR`, локальные списки/детали/фильтры, 404/422, доступность `/api/campaigns/history`, `/api/offers-remote` с Keitaro ID. Дополнительно: все сценарии распределения весов и их коды ошибок, идемпотентность миграций и разовый бэкфилл baseline (включая сохранение локальных правок при рестарте), локальные мутации редактора, load/push (включая частичный успех, `REMOTE_CHANGED`, `REVISION_CONFLICT` для всех мутаций, обновление `keitaro_updated_at`, soft delete и восстановление офферов), опциональная аутентификация по токену, кэш каталога офферов и защита от неожиданной формы ответа Keitaro.


Косвенная «проверка» вручную: прогон через UI и просмотр журнала `GET /api/campaigns/history`, а также `GET /api/health`.

---

## 13. Ссылки на важные файлы и точки входа

| Что | Файл |
|---|---|
| **Точка входа ASGI** | `backend/app/main.py` (`create_app()`, `app = create_app()`) |
| Маршруты | `backend/app/routers/` |
| Маппинг ошибок | `backend/app/api_errors.py`, `backend/app/errors.py` |
| Бизнес-логика создания кампании/потоков | `backend/app/services/creation.py` (`create_campaign`, `create_campaign_streams`) |
| Сценарии редактора (правки/sync) | `backend/app/services/editor.py` |
| Распределение весов | `backend/app/weights.py` (`distribute_shares`, `WeightError`) |
| Идемпотентная миграция схемы | `backend/app/migrations.py` (`ensure_schema`) |
| Персистентность локальных сущностей | `backend/app/repositories/` (`campaigns.py`, `editor.py`, `mapping.py`) |
| HTTP-клиент Keitaro и нормализация ошибок | `backend/app/keitaro.py` (`KeitaroClient`, `KeitaroError`) |
| Валидация запроса и нормализация GEO | `backend/app/schemas.py` (`CampaignCreate`) |
| Конфигурация | `backend/app/config.py`, `backend/.env.example` |
| Подключение к БД, сессии, PRAGMA | `backend/app/database.py` |
| ORM-модели журнала и кэша кампаний/потоков/офферов | `backend/app/models.py` |
| Тесты | `backend/tests/` |
| Инициализация/миграция схемы одной командой | `backend/scripts/init_db.py` |
| Опциональный бэкфилл | `backend/scripts/backfill_campaigns.py` |
| Dev-проверка формы `/streams` | `backend/scripts/dev/probe_keitaro_streams.py` |
| Зависимости | `backend/requirements.txt`, `backend/requirements-dev.txt` |
| Инструкции по запуску и правила Keitaro | `README.md`, `AGENTS.md` |
| Клиентский контракт (потребитель API) | `frontend/src/shared/api/`, `frontend/vite.config.ts` |

---

## 14. Расхождения с README и ограничения (проверено по коду)

1. **Alias и имя.** README и этот документ описывают актуальную схему: имя = `<CAMPAIGN_NAME_PREFIX><slug>`, alias = `<slug>_<6 hex>`, уникальность за счёт случайного суффикса. Проверки уникальности на стороне Keitaro нет, но коллизия alias практически исключена.
2. **Источник трафика.** `KEITARO_TRAFFIC_SOURCE_NAME` обязателен; `traffic_source_id` разрешается по имени и передаётся в `POST /campaigns`.
3. **Идемпотентность HTTP.** Повторный `POST /api/campaigns/create` создаст новую кампанию в Keitaro. Идемпотентны только локальные upsert'ы по keitaro ID (повторная обработка того же ответа не даёт дублей). README признаёт это как ограничение MVP.
4. **Тесты.** Есть, но покрывают backend на уровне API/репозитория; `KeitaroClient` проверяется через моки, живые вызовы не выполняются.
5. **Миграции.** Alembic нет; схема управляется `create_all` + идемпотентным `ensure_schema` (§7.4). Добавление колонок автоматизировано, изменение типа/удаление колонок по-прежнему требует ручных действий. Для нескольких воркеров используйте `scripts/init_db.py` и `AUTO_MIGRATE=false`.
6. **Async SQLAlchemy.** БД работает через `aiosqlite`/`asyncpg`; все эндпоинты `async def`, блокирующих вызовов SQLAlchemy в event loop нет.
7. **Аутентификация API опциональна.** При пустом `API_AUTH_TOKEN` API открыт; для любого развёртывания вне localhost токен обязателен (§8.1).
8. **Драйвер PostgreSQL** (`asyncpg`) включён в `requirements.txt`; URL должен быть `postgresql+asyncpg://...` (обычный `postgresql://` автоматически приводится к async-драйверу).
9. **`lifespan`** выполняет `create_all`/`ensure_schema` при `AUTO_MIGRATE=true`; при нескольких воркерах авто-миграции нужно отключить и инициализировать схему один раз через `python -m scripts.init_db`.
10. **Параллелизм.** После проверки оффера `GET /domains`, `/groups`, `/traffic_sources` и `/streams_actions` выполняются параллельно через `asyncio.gather`; запись потоков остаётся последовательной, чтобы сохранить partial-семантику.
11. **Пустой локальный список после деплоя.** Старые кампании появятся только после новых созданий или бэкфилла (`scripts/backfill_campaigns.py`); это ожидаемо.
12. **Окно между Keitaro и БД.** Падение процесса после `POST /campaigns` и до commit #2 оставит кампанию только в Keitaro; после commit #2 и до commit #3 кампания будет локально, а потоков/офферов может не быть. Компенсация — идемпотентный бэкфилл.
13. **`keitaro_stream_id` и `schema`.** Поле `schema` в `StreamOut` перекрывает deprecated-атрибут `BaseModel` — Pydantic выдаёт `UserWarning`; имя сохранено, так как это контракт API.

### Неподтверждённые предположения

- Точная форма ответов `GET /groups?type=campaigns`, `/domains`, `/traffic_sources` не проверялась по живому Keitaro (внешние вызовы в ходе исследования не выполнялись). `find_by_name` принимает list и envelope-объект (`{"data": [...]}`, `{"items": [...]}`), отбрасывает не-словари и требует ровно одно совпадение по `name`.
- Контракт `action_payload` для `schema="redirect"` и допустимость `schema="landings"` + `offer_selection="before_click"` зависят от версии Keitaro; README прямо требует сверки с Swagger конкретной инсталляции.
- Точная форма `GET /campaigns/{id}` (вложенность потоков/офферов) не подтверждена. Основной поток от неё не зависит; бэкфилл сохраняет сырой ответ и при неожиданной форме пишет только кампанию.
- Поведение при `POST /campaigns`, возвращающем ответ без поля `id`: сервис выбрасывает `ValueError` → 400 `CAMPAIGN_CREATION_ERROR`; локальных сущностей не создаётся. Для `POST /streams` без `id` — `PartialCreationError` → 502 `PARTIAL_CREATION`.
