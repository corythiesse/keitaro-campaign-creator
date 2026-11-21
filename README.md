# Keitaro Campaign Creator

MVP: FastAPI + async SQLAlchemy + React + MUI. Создаёт кампанию и два потока, после чего позволяет редактировать её потоки/офферы локально и синхронизировать изменения обратно в Keitaro:

1. Обычный поток: фильтр Country принимает настроенные коды стран и перенаправляет на Google.
2. Поток по умолчанию: направляет 100% трафика на выбранный активный оффер.

Если создание потока не удалось, кампания и уже созданные потоки намеренно остаются в Keitaro. Операция помечается в журнале как `partial`.

## Быстрый запуск

```bash
# backend
cd backend
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn app.main:app --reload
```

```bash
# frontend
cd frontend
cp .env.example .env
npm ci
npm run dev
```

## Локальное хранилище

Созданные сущности также кэшируются в локальной базе данных (по умолчанию SQLite) и читаются из неё:

1. Кампания сохраняется **сразу после** успешного `POST /campaigns` (отдельный commit, до создания потоков).
2. Потоки (`GEO - Google`, `Default - Offer`) сохраняются после их создания.
3. Оффер, привязанный к потоку офферов, сохраняется как снимок на уровне потока.
4. `GET /api/campaigns`, `GET /api/campaigns/{id}` и `GET /api/offers?campaign_id=` читают только локальную БД и никогда не обращаются к Keitaro.
5. `GET /api/offers-remote` сохраняет прежний автокомплит на основе Keitaro.

Таблицы (`campaigns`, `streams`, `offers`, `campaign_creation_logs`) создаются `Base.metadata.create_all` при старте приложения (или командой `python -m scripts.init_db`); недостающие колонки в существующей БД добавляет идемпотентный `app/migrations.py` (`ensure_schema`). Базовая линия редактора (`base_*`) бэкфиллится **только для колонок, добавленных в этом запуске**, поэтому перезапуск приложения никогда не превращает несинхронизированные локальные правки (например, soft-deleted оффер) в состояние «уже синхронизировано». Alembic не используется. Существующие кампании появляются локально только после нового создания или после запуска опционального скрипта бэкфилла.

По умолчанию используется база `backend/campaign_creator.db`; путь вычисляется относительно каталога `backend/`, поэтому не зависит от текущего рабочего каталога. Файл SQLite — runtime-артефакт, git его не отслеживает.

Слой БД работает через async SQLAlchemy (`aiosqlite` для SQLite, `asyncpg` для PostgreSQL). Вызовы репозиториев ожидаются end-to-end, поэтому I/O Keitaro и базы данных не блокируют event loop.

## Редактор кампании

`GET /api/campaigns/{id}` заполняет страницу редактора (`/campaigns/{id}` в UI):

- локальное рабочее состояние vs. базовая линия Keitaro (`base_*`); признак «есть несинхронизированные изменения» вычисляется, а не хранится;
- soft-delete/восстановление офферов (`is_deleted`) и локальное закрепление весов офферов (`is_pinned`/`pinned_share`); сами потоки из приложения не удаляются и не восстанавливаются;
- веса активных офферов всегда суммируются в 100; невозможные комбинации закреплений отклоняются с `422` и никогда не сохраняются;
- `POST /api/campaigns/{id}/sync/load` вытягивает потоки/офферы из Keitaro (`force=true` отбрасывает локальные правки);
- `POST /api/campaigns/{id}/sync/push` отправляет только изменённые потоки, по одному commit на поток (при частичном успехе неудавшиеся потоки остаются «грязными»);
- `POST /api/campaigns/{id}/sync/discard` восстанавливает последнюю загруженную/отправленную версию.

Каждая мутация редактора принимает опциональный `expected_revision` (также для `PATCH /api/offers/{id}` и `POST /api/streams/{id}/offers`). Устаревшая ревизия возвращает `409 REVISION_CONFLICT` до любой записи; успешный push увеличивает ревизию, поэтому другая вкладка не может молча перезаписать результат. Инкремент ревизии выполняется compare-and-swap обновлением, поэтому две вкладки не могут закоммитить изменения на основе одной и той же версии. UI автоматически отправляет ту ревизию, которую отрисовал.

Ничего не отправляется в Keitaro, пока пользователь явно не нажмёт «Отправить изменения в Keitaro».

## Важная конфигурация Keitaro

Документация Admin API требует `action_type` при создании потока, и его значение должно быть одним из action key, возвращаемых `GET /admin_api/v1/streams_actions`. Точный action key зависит от установленной версии и конфигурации Keitaro. Не угадывайте его.

1. Запустите backend.
2. Откройте `GET /api/admin/stream-actions` (или вызовите Keitaro `GET /admin_api/v1/streams_actions`).
3. Укажите в `.env` `KEITARO_STREAM_ACTION_TYPE` — action `key`, подходящий для прямого HTTP-редиректа в вашем трекере.
4. Перед использованием в продакшене сверьте запрос со Swagger вашей инсталляции.

В справочнике API описаны поля кампании (`alias`, `name`, `domain_id`, `group_id`, `traffic_source_id`), поля потока (`campaign_id`, `schema`, `type`, `name`, `action_type`, `action_payload`, `filters`, `offers`), а также значения фильтра Country. В руководстве Keitaro по фильтрам сказано, что несколько кодов стран можно вводить через пробел. Поэтому реализация отправляет, например, `MX AU RO` в payload фильтра Country.

## Настройка backend

```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Заполните .env: base URL, API key, БД и action key потока
uvicorn app.main:app --reload
```

По умолчанию для простого локального запуска используется SQLite. В деплое задайте `DATABASE_URL` как async PostgreSQL URL, например `postgresql+asyncpg://user:password@host/db` (драйвер `asyncpg` включён в `requirements.txt`).

Ключевые настройки (см. `backend/.env.example`):

| Переменная | По умолчанию | Назначение |
|---|---|---|
| `KEITARO_OFFERS_CACHE_TTL` | `30` | Процессный кэш `GET /offers` для автокомплита и загрузки в редакторе; `0` отключает его. |
| `API_AUTH_TOKEN` | пусто | Если задан, все маршруты `/api/*`, кроме `/api/health`, требуют `X-API-Token` или `Authorization: Bearer`. Для локальной разработки оставьте пустым. |
| `AUTO_MIGRATE` | `true` | Создавать/обновлять схему при старте. Для multi-worker деплоя установите `false` и один раз выполните `python -m scripts.init_db`. |
| `CAMPAIGN_NAME_PREFIX` | `test_` | Префикс генерируемого имени кампании Keitaro (`<prefix><slug>`). |

Для нескольких воркеров инициализируйте базу данных один раз и запустите uvicorn с отключённой миграцией:

```bash
python -m scripts.init_db
AUTO_MIGRATE=false uvicorn app.main:app --workers 4
```

## Настройка frontend

```bash
cd frontend
cp .env.example .env   # опционально: цель прокси / dev API-токен
npm ci
npm run dev
```

Vite проксирует `/api` на `http://127.0.0.1:8000` по умолчанию (переопределяется через `VITE_API_PROXY_TARGET`). Явный IPv4-адрес избегает коллизий с другими сервисами, слушающими `[::1]:8000`.
Frontend написан на TypeScript; полная локальная проверка:

```bash
npm run check          # typecheck + lint + проверка форматирования + тесты + сборка
npm run test:coverage  # покрытие с порогами
```

## API

- `GET /api/offers-remote?q=` — активные офферы из Keitaro для автокомплита (`id` — ID оффера в Keitaro).
- `GET /api/offers?campaign_id=` — офферы кампании из локальной БД (`campaign_id` обязателен).
- `GET /api/admin/stream-actions` — посмотреть установленные action key потоков.
- `POST /api/campaigns/create` — создать кампанию и потоки, сохранить их локально.
- `GET /api/campaigns?limit=&offset=&q=&state=` — локальный список кампаний (сначала новые).
- `GET /api/campaigns/{id}` — локальная кампания с вложенными потоками/офферами и полями редактора (`has_local_changes`, `revision`, `is_deleted`, `is_pinned`, ...).
- `GET /api/campaigns/history` — история операций.
- `POST /api/campaigns/{id}/sync/load` — перезагрузить потоки/офферы из Keitaro (`{"force": true}` отбрасывает локальные правки; иначе `409 LOCAL_CHANGES_PENDING`).
- `POST /api/campaigns/{id}/sync/push` — отправить локальные изменения (`{"expected_revision": N, "force": false}`); частичный успех возвращает `200` с `success=false`.
- `POST /api/campaigns/{id}/sync/discard` — откатиться к последней загруженной/отправленной версии.
- `POST /api/streams/{id}/offers` — добавить/восстановить оффер в потоке (только локально; Keitaro читается для валидации).
- `PATCH /api/offers/{id}` — `{is_deleted}`, `{is_pinned, pinned_share}`, `{state}`.

Все мутирующие эндпоинты редактора принимают опциональный `expected_revision`; UI всегда его отправляет.

Если задан `API_AUTH_TOKEN`, все эндпоинты под `/api`, кроме `/api/health`, требуют заголовок `X-API-Token` (или `Authorization: Bearer <token>`). Frontend не читает токен из браузера: добавьте заголовок в reverse proxy, который раздаёт SPA и проксирует `/api`. Для локального Vite dev/preview экспортируйте `API_AUTH_TOKEN` в окружении frontend, и прокси добавит заголовок автоматически (переменная не попадает в браузер, так как у неё нет префикса `VITE_`).

Запрос:
```json
{"name":"Test campaign","geo":"MX, AU, RO","offer_id":123}
```

Пути `/api/campaigns` используют **локальный** ID кампании; `keitaro_id` всегда присутствует в ответах. Автокомплит по-прежнему использует ID Keitaro и отправляет `offers-remote.id` как `offer_id`.

## Тесты

```bash
cd backend
pip install -r requirements-dev.txt
pytest
```

Backend-тесты используют временную SQLite-базу и мокают Keitaro через `respx` (сетевых вызовов нет). Они покрывают создание, локальное чтение, миграции (включая сохранение несинхронизированных правок после перезапуска), распределение весов, мутации редактора, load/push (включая частичный успех и конфликты ревизий), опциональную аутентификацию API и кэш каталога офферов.

```bash
cd frontend
npm ci
npm test
```

Frontend-тесты используют Vitest + Testing Library (jsdom) и мокают модуль API. Набор покрывает API-клиент, список/фильтры/пагинацию, создание, сценарии синхронизации/конфликтов редактора и валидацию. `npm run check` — полный quality gate (typecheck, lint, проверка форматирования, тесты, сборка); CI запускает его на Node 22.

## Бэкфилл и диагностика (опционально)

Существующие кампании можно импортировать из Keitaro в локальную БД (`GET /campaigns/{id}` + `GET /campaigns/{id}/streams`):

```bash
cd backend
python -m scripts.backfill_campaigns --dry-run
python -m scripts.backfill_campaigns --limit 10
```

Эндпоинты потоков можно проверить read-only перед тем, как на них полагаться (dev-проба, для работы приложения не нужна):

```bash
python -m scripts.dev.probe_keitaro_streams <keitaro_campaign_id>
```

## Примечания

- `domain_id`, `group_id` и `traffic_source_id` разрешаются по точным настроенным именам во время выполнения.
- Приложение проверяет, что выбранный оффер существует и активен.
- Имя кампании — `<CAMPAIGN_NAME_PREFIX><slug>`; alias — `<slug>_<6 hex chars>`, поэтому он URL-safe и помещается в `VARCHAR(64)`.
- Каталог офферов, возвращаемый Keitaro, кэшируется на `KEITARO_OFFERS_CACHE_TTL` секунд; автокомплит и загрузка в редакторе используют его совместно.
- Повторные клики предотвращаются в UI; в продакшене дополнительно стоит использовать idempotency key / таблицу уникальных запросов.
- Не раскрывайте API-ключ Keitaro браузеру. Включайте `API_AUTH_TOKEN`, если backend доступен откуда-либо кроме localhost.
- Сначала проверьте кампанию на тестовом трекере. Точный action key и принимаемый payload потока нужно сверить с вашей версией Keitaro.
# keitaro-campaign-creator
