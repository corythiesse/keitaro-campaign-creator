# Frontend (React + TypeScript) — техническая документация

> Документ описывает фактическое состояние `frontend/` после рефакторинга: TypeScript, ESLint/Prettier, разделение на `app / pages / features / shared`, feature-hooks, единый API-слой, пагинация и фильтры списка, 404 и ErrorBoundary, тесты и CI.

---

## 1. Назначение и бизнес-контекст

Frontend — SPA для управления кампаниями в трекере **Keitaro** через собственный Backend API.

Основные сценарии:

1. **Список кампаний** — загрузка из локальной БД backend, поиск по названию/alias, фильтр по статусу, догрузка по «Показать ещё».
2. **Создание кампании** — имя, GEO (ISO-коды), активный оффер Keitaro; backend создаёт кампанию и два потока (`GEO - Google`, `Default - Offer`).
3. **Редактор кампании** — просмотр потоков и офферов, soft delete/restore, закрепление веса, добавление оффера, синхронизация с Keitaro:
   - загрузка снимка из Keitaro;
   - отправка локальных изменений;
   - отмена локальных изменений;
   - обработка revision conflict и частичного push.

Ключевой принцип: **браузер не обращается к Keitaro напрямую** и не знает Keitaro API key. Все внешние вызовы выполняет backend; frontend общается только с `/api/*`.

Backend остаётся источником истины: после каждой мутации редактор заменяет состояние полным ответом `CampaignEditorOut`.

---

## 2. Технологический стек

| Технология | Версия | Назначение |
|---|---|---|
| TypeScript | `^6.0.3` | Строгая типизация, `tsc --noEmit` |
| React | `^18.3.1` | UI |
| React DOM | `^18.3.1` | Рендер |
| React Router DOM | `^6.30.6` | Маршрутизация |
| MUI Material | `^6.4.6` | UI-компоненты |
| MUI Icons | `^6.4.6` | Иконки |
| Emotion | `^11.14.0` | Styling engine MUI (peer dependency) |
| Vite | `^6.1.0` | Dev-сервер и сборка |
| Vitest | `^3.2.7` | Тесты |
| Testing Library | `^16.3` / `^6.9` / `^14.6` | Компонентные тесты |
| jsdom | `^26.1.0` | DOM-окружение тестов |
| ESLint | `^10.15` | Линтинг |
| Prettier | `^3.10` | Форматирование |
| `@vitest/coverage-v8` | `^3.2.7` | Coverage |

### Чего в стеке нет

- Redux/Zustand/MobX/Jotai/Recoil и глобального стора;
- TanStack Query/SWR/Apollo;
- Axios (используется нативный `fetch`);
- React Hook Form/Formik/Zod/Yup;
- CSS Modules/Sass/Tailwind/styled-components;
- Playwright/Cypress (e2e отсутствуют);
- Docker/CI для backend (frontend CI добавлен).

Решение **не добавлять** React Query, глобальный store и CSS-препроцессоры зафиксировано осознанно: для двух экранов и серверного source-of-truth это преждевременное усложнение.

---

## 3. Структура проекта

```
frontend/
├── index.html                 # #root, /src/main.tsx
├── package.json               # зависимости и скрипты
├── package-lock.json
├── tsconfig.json              # strict, noEmit, jsx react-jsx
├── vite.config.ts             # React plugin, proxy, test/coverage, manualChunks
├── eslint.config.js           # flat config, typescript-eslint, react-hooks
├── .prettierrc.json
├── .prettierignore
└── src/
    ├── main.tsx               # StrictMode, ThemeProvider, CssBaseline, ErrorBoundary, BrowserRouter
    ├── vite-env.d.ts
    ├── app/
    │   ├── App.tsx            # Routes
    │   ├── ErrorBoundary.tsx  # fallback при ошибке рендера
    │   └── theme.ts           # MUI theme
    ├── pages/
    │   ├── CampaignsPage.tsx
    │   ├── CampaignsPage.test.tsx
    │   ├── CampaignEditorPage.tsx
    │   ├── CampaignEditorPage.test.tsx
    │   └── NotFoundPage.tsx
    ├── features/
    │   ├── campaigns/
    │   │   ├── CampaignFilters.tsx
    │   │   ├── CampaignForm.tsx
    │   │   ├── CampaignForm.test.tsx
    │   │   ├── CampaignList.tsx
    │   │   ├── CreateCampaignDialog.tsx
    │   │   ├── campaignFormValidation.ts
    │   │   ├── campaignFormValidation.test.ts
    │   │   ├── useCampaigns.ts
    │   │   ├── useCreateCampaign.ts
    │   │   └── useCreateCampaign.test.tsx
    │   └── campaign-editor/
    │       ├── AddOfferForm.tsx
    │       ├── ConfirmDialog.tsx
    │       ├── OfferList.tsx
    │       ├── OfferRow.tsx
    │       ├── StreamItem.tsx
    │       ├── StreamList.tsx
    │       ├── SyncToolbar.tsx
    │       └── useCampaignEditor.ts
    ├── shared/
    │   ├── api/
    │   │   ├── client.ts      # request, ApiError, parseApiError, timeout/abort
    │   │   ├── campaigns.ts   # доменные вызовы кампаний/редактора
    │   │   ├── offers.ts      # /api/offers-remote
    │   │   └── types.ts       # контракты API
    │   ├── hooks/
    │   │   ├── useLatestRequest.ts
    │   │   ├── useNotice.ts
    │   │   └── useOfferSearch.ts
    │   ├── lib/
    │   │   ├── constants.ts
    │   │   ├── formatDate.ts
    │   │   └── stateColors.ts
    │   └── ui/
    │       ├── ErrorAlert.tsx
    │       ├── LoadingBlock.tsx
    │       ├── NoticeSnackbar.tsx
    │       ├── OfferAutocomplete.tsx
    │       ├── PageShell.tsx
    │       └── StateChip.tsx
    └── test/
        ├── setup.ts
        └── fixtures.ts
```

### Правила организации

- `app` → `pages` → `features` → `shared`.
- `shared` не импортирует `features/pages/app`.
- `features/*` не импортируют друг друга; общее — в `shared`.
- HTTP и `/api/` — только в `shared/api`.
- Страницы не вызывают API напрямую; данные и действия приходят из feature-hooks.
- Общий UI-примитив появляется после второго реального потребителя.
- Тесты лежат рядом с проверяемым unit.

---

## 4. Архитектура

### 4.1 Граф зависимостей

```
main.tsx
└─ ThemeProvider + CssBaseline + ErrorBoundary + BrowserRouter
   └─ App.tsx
      ├─ CampaignsPage
      │  ├─ useCampaigns ── shared/api/campaigns
      │  ├─ CampaignFilters
      │  ├─ CampaignList
      │  ├─ CreateCampaignDialog → CampaignForm → useOfferSearch
      │  │                                      └─ shared/api/offers
      │  └─ useNotice → NoticeSnackbar
      ├─ CampaignEditorPage
      │  └─ useCampaignEditor ── shared/api/campaigns
      │     ├─ SyncToolbar
      │     └─ StreamList → StreamItem
      │                     ├─ OfferList → OfferRow
      │                     └─ AddOfferForm → useOfferSearch → shared/api/offers
      └─ NotFoundPage
```

Циклических зависимостей нет.

### 4.2 Разделение ответственности

| Слой | Ответственность |
|---|---|
| `app` | Провайдеры, routes, theme, ErrorBoundary |
| `pages` | Композиция экрана: header, фильтры, состояния, вызов feature-hook |
| `features/campaigns` | Список, фильтры, форма, создание, пагинация |
| `features/campaign-editor` | Потоки, офферы, pin, soft delete, синхронизация, подтверждения |
| `shared/api` | HTTP-транспорт, ошибки, таймауты, контракты |
| `shared/hooks` | Повторяемые механизмы: notice, guard, debounce-поиск |
| `shared/ui` | Презентационные примитивы без доменной логики |
| `shared/lib` | Форматирование, состояния, константы |

### 4.3 Состояние

- Глобального стора нет.
- `useCampaigns` владеет списком, пагинацией, поиском, фильтром, `loading/refreshing/loadingMore/error`.
- `useCampaignEditor` владеет `campaign`, `loading/error/busy`, `confirm`, `pushResults`, `revisionConflict`, `notice`, действиями синхронизации.
- `useCreateCampaign` владеет `submitting` и вызовом создания.
- `CampaignForm` владеет только полями и ошибками валидации.
- `useOfferSearch` владеет query/offers/loading/debounce.
- `useLatestRequest` защищает от гонок; `useNotice` — от дублирования Snackbar.
- `AbortController` отменяет устаревшие загрузки; `request()` имеет timeout.

---

## 5. Страницы и UI

### 5.1 Список кампаний

`CampaignsPage`:

- заголовок «Кампании» и кнопка «Создать»;
- `CampaignFilters`: поиск по `q` и фильтр `state`;
- `CampaignList`: loading / error+retry / empty / filtered-empty / data;
- строки кликабельны, ведут на `/campaigns/:localId`;
- кнопка «Показать ещё» при `hasMore` (offset += 50);
- `LinearProgress` при silent-refresh;
- `CreateCampaignDialog` с `key`-remount: каждое открытие — чистые поля;
- `NoticeSnackbar`.

Пустой список без фильтров предлагает «Создать кампанию»; пустой результат фильтра — «Ничего не найдено» и «Сбросить фильтры».

### 5.2 Создание кампании

`CampaignForm` — controlled-поля:

- `TextField` «Название» (`maxLength=255`);
- `TextField` «Код страны» (`maxLength=255`);
- `OfferAutocomplete` с debounce-поиском.

Валидация — чистая функция `validateCampaignForm`:

| Поле | Правило |
|---|---|
| name | непустое после `trim()` |
| geo | непустое; коды после `[,\s;]+` имеют формат `^[A-Z]{2}$`; нет дубликатов |
| offer | выбран объект оффера |

Проверяется только формат ISO; существование страны проверяет backend через `pycountry`. Ошибки формата и дубликатов взаимоисключающие: сначала формат, затем дубликаты.

`useCreateCampaign`:

- `submitting` — единственный источник истины (форма получает его пропсом);
- повторный submit во время запроса отклоняется;
- ошибка пробрасывается в форму, которая вызывает `onError(message, code)`.

`CreateCampaignDialog` блокирует закрытие (Esc, backdrop, «Отмена») во время `submitting`.

### 5.3 Редактор кампании

`CampaignEditorPage`:

- header: «К списку кампаний», имя, `StateChip` кампании, Keitaro ID, кнопка «Открыть в Keitaro» (новая вкладка; URL приходит с backend из `KEITARO_BASE_URL`);
- `SyncToolbar`:
  - «Загрузить из Keitaro»;
  - «Отправить изменения в Keitaro»;
  - «Отменить изменения»;
  - индикаторы dirty/synced, даты, revision, `last_sync_error`;
- `LinearProgress` при любой операции;
- `Alert` при `REVISION_CONFLICT` с кнопкой «Обновить»;
- `Alert warning` при частичном push со списком ошибок и «Повторить отправку»;
- `StreamList` → `StreamItem`:
  - имя, `StateChip`, чип «Удалён», «Локальный»;
  - `OfferList` → `OfferRow`;
  - `AddOfferForm` только для неудалённого и не-redirect потока.

`OfferRow`:

- имя, Keitaro ID, OfferStream ID;
- вес с pin-иконкой;
- `StateChip` оффера;
- pin: диалог веса с проверкой целого `0..100`;
- soft delete/restore.

`AddOfferForm`:

- поиск офферов ленивый: `useOfferSearch` включается при открытии/вводе, чтобы не делать N запросов при монтировании всех потоков;
- после успешного добавления выбор и query сбрасываются.

### 5.4 MUI и тема

- `ThemeProvider` + `CssBaseline`; тема вынесена в `app/theme.ts`.
- Палитра: primary `#315fba`, borderRadius 8, Roboto/Arial.
- Стилизация — `sx`; CSS-файлов нет.
- Общие примитивы: `StateChip`, `NoticeSnackbar`, `PageShell`, `LoadingBlock`, `ErrorAlert`, `OfferAutocomplete`, `ConfirmDialog`.
- Статусы локализованы через `stateLabel`; неизвестные значения показываются как есть.
- `Tooltip describeChild` + `aria-label` у icon-button; `Dialog` с focus trap.

---

## 6. Маршрутизация

`BrowserRouter` в `main.tsx`; маршруты в `app/App.tsx`.

| Путь | Компонент | Назначение |
|---|---|---|
| `/` | `CampaignsPage` | список |
| `/campaigns/:campaignId` | `CampaignEditorPage` | редактор; `campaignId` — локальный ID |
| `*` | `NotFoundPage` | 404 |

- `campaignId` валидируется как `^\d+$`; иначе сразу `NotFoundPage`, API не вызывается.
- Переход из списка — `navigate(\`/campaigns/${campaign.id}\`)`.
- Возврат — `Button component={RouterLink} to="/"`.
- SPA fallback для production должен обеспечить сервер/прокси.
- Lazy loading не используется осознанно: две страницы, эффект близок к нулю.

---

## 7. Данные и API

### 7.1 HTTP-клиент

`shared/api/client.ts`:

- `request<T>()` — единая точка `fetch`;
- заголовки `Accept`, `Content-Type` при теле;
- timeout по умолчанию 30 с;
- `AbortController`, поддержка внешнего `signal`;
- `ApiError` с `status`, `code`, `body`, `cause`;
- `parseApiError` разбирает `detail` строкой, массивом Pydantic и объектом; если у объекта есть `details`, он добавляется к `message` (строка или JSON, до 500 символов), чтобы в UI был виден текст ошибки Keitaro;
- `getErrorMessage`, `getApiErrorCode`.

Ошибки:

| Ситуация | Код |
|---|---|
| FastAPI `detail.code` | исходный код (`REVISION_CONFLICT`, `SYNC_FAILED`, ...) |
| сеть | `NETWORK_ERROR` |
| timeout | `TIMEOUT` |
| отмена | `ABORTED` |

`useOfferSearch` и все доменные функции используют один клиент.

### 7.2 Endpoint'ы

| Метод и путь | Функция | Назначение |
|---|---|---|
| `GET /api/campaigns?limit=&offset=&q=&state=` | `fetchCampaigns` | список, поиск, фильтр |
| `POST /api/campaigns/create` | `createCampaign` | создание |
| `GET /api/campaigns/{id}` | `fetchCampaignDetail` | детали редактора |
| `POST /api/campaigns/{id}/sync/load` | `loadCampaignStreams` | загрузка из Keitaro (`force`) |
| `POST /api/campaigns/{id}/sync/push` | `pushCampaignChanges` | отправка (`expected_revision`) |
| `POST /api/campaigns/{id}/sync/discard` | `discardCampaignChanges` | отмена локальных изменений |
| `POST /api/streams/{id}/offers` | `addOffer` | добавление/восстановление оффера |
| `PATCH /api/offers/{id}` | `updateOffer` | soft delete/restore/pin/state |
| `GET /api/offers-remote?q=` | `searchOffers` | autocomplete активных офферов |

Не используются frontend'ом: `/api/health`, `/api/admin/stream-actions`, `/api/campaigns/history`, `/api/offers`.

### 7.3 Обработка sync-сценариев

- `REVISION_CONFLICT` → `Alert` + «Обновить»; успешный `load` сбрасывает флаг.
- `LOCAL_CHANGES_PENDING` от `sync/load` → confirm «Потерять изменения?» → повтор с `force=true`.
- `SYNC_FAILED` → `pushResults` из `detail.results`, error-Snackbar.
- partial push (`200`, `success=false`) → warning-Alert + retry.
- `has_local_changes` → `beforeunload`.
- focus-refresh не выполняется при `busy` или открытом confirm.

### 7.4 Кеширование

Клиентского кеша нет. Список загружается при открытии, после создания/частичного создания — silent-refresh. Поиск офферов debounce 250 мс. При росте требований (общий кеш, фильтры на нескольких экранах) можно рассмотреть TanStack Query, но не сейчас.

---

## 8. Аутентификация

Backend поддерживает optional `API_AUTH_TOKEN`: при заданном токене все `/api/*`, кроме `/api/health`, требуют `X-API-Token` или `Authorization: Bearer`.

Frontend **не хранит токен**:

- production: reverse proxy добавляет заголовок при проксировании `/api`;
- dev/preview: `vite.config.ts` читает `API_AUTH_TOKEN` из окружения и добавляет `X-API-Token` в proxy;
- `API_AUTH_TOKEN` не имеет префикса `VITE_`, поэтому не попадает в клиентский бандл.

При 401 backend возвращает `{detail:{code:"UNAUTHORIZED", message:"..."}}`; UI показывает сообщение. Экрана входа и ролей нет — это ответственность внешнего прокси/периметра.

---

## 9. Конфигурация и скрипты

### 9.1 Окружение

| Переменная | Где | Назначение |
|---|---|---|
| `VITE_API_PROXY_TARGET` | `.env`/shell frontend | target dev/preview proxy, по умолчанию `http://127.0.0.1:8000` |
| `API_AUTH_TOKEN` | `.env`/shell frontend | добавляется proxy в `X-API-Token`; не экспортируется в браузер |

Шаблон: `frontend/.env.example`.

Backend-переменные (Keitaro key, БД) настраиваются в `backend/.env` и frontend не касаются.

### 9.2 Скрипты

| Скрипт | Команда | Назначение |
|---|---|---|
| `dev` | `vite --host 0.0.0.0` | dev-сервер + proxy |
| `build` | `tsc --noEmit && vite build` | typecheck + production build |
| `preview` | `vite preview` | preview с proxy |
| `test` | `vitest run` | тесты |
| `test:watch` | `vitest` | watch |
| `test:coverage` | `vitest run --coverage` | coverage + thresholds |
| `typecheck` | `tsc --noEmit` | типы |
| `lint` | `eslint .` | линт |
| `format` | `prettier --write .` | форматирование |
| `format:check` | `prettier --check .` | проверка формата |
| `check` | typecheck + lint + format:check + test + build | полный локальный/CI-контур |

CI: `.github/workflows/frontend-ci.yml` — `npm ci`, `npm run check`, `npm run test:coverage` на Node 22.

### 9.3 Vite

- `server.proxy` и `preview.proxy` для `/api`;
- `manualChunks`: `react`, `mui`, app;
- Vitest: `jsdom`, `globals`, `setupFiles`, coverage thresholds 70/60;
- ESLint: `typescript-eslint`, `react-hooks`, `react-refresh`, Prettier;
- `react-hooks/set-state-in-effect` отключён: data-fetching эффекты намеренно управляют loading-состоянием.

---

## 10. Тестирование и качество

- 14 test-файлов, 61 тест; coverage ~96% statements.
- Покрыто:
  - API-клиент: success/error/network/timeout, `parseApiError`;
  - доменные вызовы: query-параметры, `expected_revision`, sync endpoints;
  - `useOfferSearch`: debounce, `enabled`, ошибки;
  - `useCreateCampaign`: успех, параллельный submit, ошибка;
  - валидация формы;
  - форма: ошибки, ISO, дубликаты, submit, disabled;
  - список: loading/empty/error/retry, поиск, пагинация, filtered-empty, создание, `PARTIAL_CREATION`, навигация;
  - редактор: потоки/офферы, soft delete/restore, pin и его валидация, dirty, push, partial push, confirm load, `LOCAL_CHANGES_PENDING`, revision conflict + refresh, discard, добавление оффера, 404;
  - `App`, `ErrorBoundary`, `formatDate`, `stateColors`, theme.
- API-модули мокаются через `vi.mock`; `fetch` подменяется в транспортных тестах.
- E2E отсутствуют; при появлении критичных пользовательских путей — Playwright отдельным этапом.

---

## 11. Сборка и развёртывание

`npm run build` создаёт:

```
dist/index.html
dist/assets/index-*.js   # приложение
dist/assets/react-*.js   # react/react-dom/react-router
dist/assets/mui-*.js     # MUI/Emotion
```

Требования production:

- раздача статики с fallback на `index.html` для SPA-маршрутов;
- reverse proxy `/api` → backend;
- при `API_AUTH_TOKEN` proxy добавляет `X-API-Token`;
- кеширование hashed assets.

`vite preview` теперь тоже проксирует `/api` (ранее не проксировал).

---

## 12. Пользовательские сценарии

### 12.1 Список

1. `useCampaigns` запрашивает `limit=50&offset=0`.
2. Поиск debounce 300 мс, фильтр статуса — сразу.
3. «Показать ещё» запрашивает следующий offset; `hasMore = data.length === 50`.
4. Ошибка показывается `ErrorAlert`; при наличии данных список сохраняется.

### 12.2 Создание

1. Открытие диалога → `key` remount → чистые поля.
2. Валидация на клиенте; при ошибке — `helperText`.
3. `POST /api/campaigns/create`; `submitting` блокирует кнопки и закрытие.
4. Успех → success-Snackbar + silent-refresh списка.
5. Ошибка → error-Snackbar, поля сохранены; `PARTIAL_CREATION` дополнительно обновляет список.

### 12.3 Редактор

1. `GET /api/campaigns/{id}`; состояние заменяется ответом.
2. Load с `has_local_changes` → confirm → `sync/load` с `force=true`.
3. `sync/load` вернул `LOCAL_CHANGES_PENDING` (например, изменения из другой вкладки) → тот же confirm → `force=true`.
4. Push → `expected_revision`; partial → warning + retry; conflict → Alert + refresh.
5. Мутации офферов возвращают полный `CampaignEditorOut`; локальное состояние заменяется.
6. `beforeunload` при `has_local_changes`; focus-refresh только без busy/confirm.

---

## 13. Ключевые файлы

| Файл | Роль |
|---|---|
| `src/main.tsx` | Точка входа, провайдеры |
| `src/app/App.tsx` | Маршруты |
| `src/app/ErrorBoundary.tsx` | Fallback при ошибке рендера |
| `src/app/theme.ts` | MUI theme |
| `src/pages/CampaignsPage.tsx` | Список, фильтры, создание |
| `src/pages/CampaignEditorPage.tsx` | Редактор, sync, confirm, alerts |
| `src/features/campaigns/useCampaigns.ts` | Список, пагинация, поиск |
| `src/features/campaigns/useCreateCampaign.ts` | Создание, submitting |
| `src/features/campaigns/CampaignForm.tsx` | Поля, валидация, submit |
| `src/features/campaign-editor/useCampaignEditor.ts` | Состояние и действия редактора |
| `src/shared/api/client.ts` | Транспорт, ошибки, timeout/abort |
| `src/shared/api/campaigns.ts` | Доменные вызовы кампаний |
| `src/shared/api/offers.ts` | Поиск офферов |
| `src/shared/api/types.ts` | Контракты API |
| `src/shared/hooks/useOfferSearch.ts` | Debounce-поиск |
| `src/shared/ui/*` | Общие UI-примитивы |

---

## 14. Ограничения и открытые вопросы

- Frontend читает кампании только из локальной БД backend; кампании, созданные вне приложения, не видны без backfill-скрипта.
- Нет e2e-тестов и визуальной регрессии.
- Нет экрана входа/ролей; auth — reverse proxy или внешний периметр.
- Нет тёмной темы, переключения темы и кастомных брейкпоинтов.
- Нет optimistic updates: сервер — источник истины.
- Форма создания не защищена `beforeunload`: закрытие вкладки или диалога теряет введённые значения.
- Нет lazy loading; при росте приложения вернуться к code splitting.
- Bundle разделён на vendor-чанки, но MUI остаётся основной частью; при росте — динамические импорты.
- `InputProps` MUI v6 при миграции на v7 заменить на `slotProps.input`.
- React Router 6.30 в тестах предупреждает о v7 future flags; миграция не входит в текущий этап.
- Поведение Autocomplete после выбора проверено тестом; при смене MUI-версии — перепроверить.
- `docs/BACKEND_API.md` — источник истины по backend; frontend-типы отражают только используемые поля.

---

## 15. Правила развития

1. Новый HTTP-вызов — только в `shared/api`; `fetch` вне слоя запрещён.
2. Новый экран — новый feature-hook; страница не содержит бизнес-операций и `try/catch` API.
3. Общий UI-компонент — после второго реального потребителя.
4. Исправление бага сопровождается regression test.
5. Изменение поведения обновляет этот документ и README в том же PR.
6. Ошибки обрабатываются по `code`, а не по тексту.
7. `REVISION_CONFLICT`, `LOCAL_CHANGES_PENDING`, `SYNC_FAILED`, `PARTIAL_CREATION` — обязательные сценарии тестов редактора.
8. Новые зависимости — только с обоснованием; без «на всякий случай».
9. `useMemo`/`useCallback`/`memo` — только при измеренной проблеме.
10. Глобальный store/FSD/TS-миграция — только под конкретную боль, а не ради паттерна.
