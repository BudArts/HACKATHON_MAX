# API и интеграции

## Общие положения

- Базовый путь: `https://<домен>/api/v1`. Вебхук MAX: `POST /webhook/max`. Служебные проверки:
  `GET /healthz`, `GET /readyz`.
- Авторизация: `Authorization: Bearer <access_token>`. Токен выпускается при входе по `initData`.
- Формат запросов и ответов: `application/json; charset=utf-8`, даты — ISO 8601 без часового пояса
  (UTC), идентификаторы — UUID.
- Спецификация OpenAPI 3.1 доступна на работающем сервере по адресу `/openapi.json` (в любом
  окружении); статическая копия — `openapi.yaml` в корне репозитория, обновляется командой
  `make openapi`; дескриптор API с тестовыми доступами — `DATA-API.yaml`. Интерактивная
  документация `/docs` открыта в `development` и `staging`, в `production` отключена.
- Версионирование — в пути (`/api/v1`). Изменения, ломающие клиентов, выпускаются новой версией.
- Ограничение частоты: глобально `RATE_LIMIT_PER_MINUTE` на изменяющие запросы, вход — 10 попыток в
  минуту, обновление токена — 30, обращение к наставнику — `AI_RATE_LIMIT_PER_HOUR` на ученика.
  Превышение возвращает 429.
- Каждый ответ содержит заголовок `X-Request-ID`, совпадающий с записью в журнале.

### Формат ошибки

```json
{
  "error": {
    "code": "conflict",
    "message": "Не удалось подтвердить номер телефона через MAX",
    "fields": {}
  }
}
```

| Код | HTTP | Когда возвращается |
| --- | --- | --- |
| `validation_error` | 422 | Нарушены ограничения схемы запроса |
| `unauthorized` | 401 | Нет токена, токен истёк или отозван, подпись `initData` не прошла |
| `forbidden` | 403 | Недостаточно роли, нет доступа к объекту, не принято согласие, источник webhook не подтверждён |
| `not_found` | 404 | Объект не найден или недоступен |
| `conflict` | 409 | Состояние не допускает операцию: повторный код, отозванное согласие, недостоверный хеш контакта |
| `rate_limited` | 429 | Превышен лимит запросов |
| `storage_unavailable` | 503 | База данных недоступна |
| `dependency_unavailable` | 503 | Внешний сервис (MAX, GigaChat) недоступен |
| `internal_error` | 500 | Непредвиденная ошибка, детали — только в журнале |

## Маршруты

### Авторизация

| Метод | Путь | Назначение | Доступ |
| --- | --- | --- | --- |
| POST | `/auth/max` | Вход по стартовым данным MAX, выдача пары токенов, состояний согласий и признака `onboarding_required` | публично |
| POST | `/auth/refresh` | Ротация refresh-токена, отзыв прежней сессии | публично |
| POST | `/auth/logout` | Отзыв текущей сессии | владелец токена |

### Локальная проверка

Маршруты существуют только при `DEV_LOGIN_ENABLED=true` и `APP_ENV=development`; в остальных режимах
возвращают 404 `not_found`. Выдача стартовых данных пишется в журнал аудита.

| Метод | Путь | Назначение | Доступ |
| --- | --- | --- | --- |
| GET | `/dev/users` | Пользователи для выбора кабинета (до 50 записей: идентификатор MAX, роль, имя) | публично в демо-режиме |
| GET | `/dev/init-data?max_user_id=` | Подписанные стартовые данные для входа вне MAX | публично в демо-режиме |

### Профиль, согласия, персональные данные

| Метод | Путь | Назначение | Доступ |
| --- | --- | --- | --- |
| GET | `/me` | Профиль: роль, имя, язык, признаки наличия телефона и e-mail | авторизованный |
| PATCH | `/me` | Обновить e-mail (пустая строка удаляет значение) | согласие `service` |
| PATCH | `/me/phone` | Сохранить номер, подтверждённый MAX (`phone`, `auth_date`, `hash`) | согласие `service` |
| GET | `/me/personal-data` | Выписка: профиль, согласия, счётчики, записи журнала | авторизованный |
| DELETE | `/me` | Прекращение обработки и обезличивание данных | авторизованный, кроме администратора |
| GET | `/consents` | Состояние согласий по трём целям с редакциями документов | авторизованный |
| POST | `/consents/{purpose}` | Предоставить согласие (`purpose`: `service`, `notifications`, `ai_processing`) | авторизованный |
| DELETE | `/consents/{purpose}` | Отозвать согласие | авторизованный |
| GET | `/legal` | Действующие редакции юридических документов | публично |
| GET | `/legal/{code}` | Текст документа (`terms`, `privacy_policy`, `consent_processing`, `consent_ai`) | публично |
| POST | `/personal-data/erasure-request` | Регистрация заявления об удалении (202) | авторизованный |

### Задачи ученика

| Метод | Путь | Назначение | Доступ |
| --- | --- | --- | --- |
| GET | `/tasks` | История задач ученика (тема, предмет, статус, шаги, итог) | согласие `service` |
| GET | `/tasks/statistics` | Счётчики всего/решено/в работе и недавние темы | согласие `service` |
| GET | `/tasks/{id}` | Задача с тредом диалога ученика и наставника | владелец задачи |
| POST | `/tasks/{id}/abandon` | Прекратить работу над активной задачей | владелец задачи |

### Аналитика педагога

| Метод | Путь | Назначение | Доступ |
| --- | --- | --- | --- |
| GET | `/tutor/overview` | Обзор по классам: ученики, задачи, доли решённых, проблемные темы | `teacher`, `administrator` |
| GET | `/tutor/risk` | Ученики с ≥3 нерешёнными задачами за 7 дней и их темы | `teacher`, `administrator` |
| POST | `/tutor/link-code` | Одноразовый код привязки родителя (6 цифр, 30 минут, до 5 попыток) | `student` |

### Кабинет родителя

| Метод | Путь | Назначение | Доступ |
| --- | --- | --- | --- |
| GET | `/parent/children` | Дети, привязанные к кабинету | согласие `service`, родитель |
| POST | `/parent/link` | Привязать ребёнка кодом из бота | родитель |
| GET | `/parent/children/{id}/digest` | Недельный дайджест: начато/решено, темы, дни | родитель ребёнка |

### Уведомления

| Метод | Путь | Назначение | Доступ |
| --- | --- | --- | --- |
| GET | `/notifications` | Входящие уведомления кабинета | согласие `service` |
| POST | `/notifications/{id}/read` | Отметить прочитанным | владелец |
| POST | `/notifications/read-all` | Отметить все прочитанными | владелец |

## Примеры вызовов

Вход по стартовым данным MAX:

```bash
curl -s -X POST https://<домен>/api/v1/auth/max \
  -H 'Content-Type: application/json' \
  -d '{"init_data": "query_id=…&auth_date=…&user=…&chat=…&hash=…"}'
```

Ответ:

```json
{
  "user": {"id": "…", "role": "parent", "first_name": "Мария", "last_name": "Ковалёва",
           "locale": "ru", "is_active": true, "has_phone": false, "has_email": false,
           "created_at": "2026-09-29T12:16:51"},
  "tokens": {"access_token": "…", "refresh_token": "…", "expires_in": 1800},
  "consents": [{"purpose": "service", "granted": false, "policy_code": "consent_processing",
                "policy_version": "1.0.0", "granted_at": null, "revoked_at": null}],
  "onboarding_required": true
}
```

Согласие, статистика ученика, обзор педагога:

```bash
TOKEN=<access_token>

curl -s -X POST https://<домен>/api/v1/consents/service \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"accept": true}'

curl -s https://<домен>/api/v1/tasks/statistics -H "Authorization: Bearer $TOKEN"

curl -s https://<домен>/api/v1/tutor/overview -H "Authorization: Bearer $TEACHER_TOKEN"
```

Номер телефона, подтверждённый мини-приложением MAX:

```bash
curl -s -X PATCH https://<домен>/api/v1/me/phone \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' \
  -d '{"phone": "+79141234567", "auth_date": "1790684220", "hash": "<hex hmac>"}'
```

Выписка и прекращение обработки:

```bash
curl -s https://<домен>/api/v1/me/personal-data -H "Authorization: Bearer $TOKEN"
curl -s -X DELETE https://<домен>/api/v1/me -H "Authorization: Bearer $TOKEN"   # 202
```

## Вебхук MAX

`POST /webhook/max` принимает объект события MAX. Требования:

- заголовок `X-Max-Bot-Api-Secret` равен `MAX_WEBHOOK_SECRET` (сравнение постоянным по времени),
  иначе 403;
- ответ 200 возвращается немедленно, обработка выполняется в фоновой задаче;
- событие с уже известным ключом отбрасывается (таблица `processed_updates`), поэтому повторные
  доставки MAX не приводят к дублям;
- непригодный JSON или неизвестный `update_type` не вызывают ошибку: сервис отвечает 200, чтобы MAX
  не копил повторы.

Обрабатываемые типы событий: `bot_added`, `bot_started`, `bot_stopped`, `bot_removed`,
`chat_title_changed`, `dialog_cleared`, `dialog_muted`, `dialog_unmuted`, `dialog_removed`,
`message_callback`, `message_created`, `message_edited`, `message_removed`, `comment_created`,
`comment_edited`, `comment_removed`. Поля события: `update_type`, `timestamp` (мс), `chat_id`,
`user`, `is_channel`, тело сообщения и данные callback.

## Используемые методы MAX Bot API

Базовый адрес `https://platform-api2.max.ru`, авторизация — заголовок
`Authorization: <MAX_BOT_TOKEN>`.

| Метод | Назначение в сервисе |
| --- | --- |
| `GET /me` | Профиль бота: `user_id` и имя для кнопок `open_app` и ссылок мини-приложения |
| `GET /updates?limit&timeout&marker&types` | Транспорт `polling` |
| `GET /subscriptions`, `POST /subscriptions`, `DELETE /subscriptions` | Управление вебхуком (`app.cli webhook info\|set\|remove`) |
| `POST /messages?user_id=` | Сообщения и уведомления в диалог, до двух в секунду на диалог |
| `PUT /messages?message_id=` | Правка отправленного сообщения |
| `POST /answers?callback_id` | Ответ на нажатие inline-кнопки |
| `POST /chats/{chat_id}/actions` | Индикация набора текста |
| `PATCH /me/commands` | Регистрация команд меню бота (`app.cli commands`) |

Сообщения: текст до 4000 символов, форматирование `markdown` или `html`, вложения —
`inline_keyboard` и `request_contact`. Ограничения клавиатуры: до 210 кнопок, до 30 рядов, до семи
кнопок в ряду и до трёх, если ряд содержит `link`, `open_app`, `request_geo_location` или
`request_contact`. Типы кнопок в сервисе: `callback`, `link`, `message`, `request_contact`,
`open_app`.

Команды меню бота: `/start`, `/appeals`, `/consent`, `/help`, `/stop`.

Мини-приложение открывается кнопкой `open_app` с полезной нагрузкой
`{web_app: <имя бота>, contact_id: <user_id бота>, payload: <start_param>}` либо ссылкой
`https://max.ru/<имя бота>?startapp=<payload>`; ограничения `payload` — `^[A-Za-z0-9_-]{0,512}$`.
В мини-приложении доступны WebApp SDK (`initData`, `requestContact`, `BackButton`, `openLink`,
`openMaxLink`, `downloadFile`); `MainButton` и `themeParams` платформой не поддерживаются, поэтому
интерфейс использует собственную нижнюю навигацию.

## Проверка подписей

**`initData` мини-приложения.** Строка параметров разбирается, дубликаты ключей и более одного
`hash` отклоняются, значения декодируются из URL-кодировки. Ключи сортируются по алфавиту и
соединяются в `launch_params` в виде `key=value` с разделителем `\n`:

```
secret_key = HMAC_SHA256(key=b"WebAppData", msg=MAX_BOT_TOKEN)
signature  = hex(HMAC_SHA256(key=secret_key, msg=launch_params))
```

Подпись сравнивается с `hash` постоянным по времени, возраст `auth_date` не должен превышать
`MINIAPP_AUTH_WINDOW_SECONDS` (с допуском 60 секунд на расхождение часов).

**Контакт, переданный кнопкой бота.** MAX прикладывает к сообщению vCard и хеш:

```
hex(HMAC_SHA256(key=MAX_BOT_TOKEN, msg=vcf_info)) == hash
```

**Контакт, переданный мини-приложением** (`requestContact`). Хеш проверяется на сервере:

```
hex(HMAC_SHA256(key=MAX_BOT_TOKEN,
                msg="auth_date=<auth_date>\nphone=<только цифры, без +>\nuser_id=<user_id>")) == hash
```

`user_id` подставляется из подтверждённой сессии пользователя, а не из запроса клиента; возраст
`auth_date` ограничен 3600 секундами. При несовпадении `PATCH /me/phone` возвращает 409, номер не
сохраняется, попытка фиксируется в журнале.

## Основные схемы ответов

**UserView** — `id`, `role` (`guest`, `parent`, `teacher`, `administrator`), `first_name`,
`last_name`, `username`, `locale`, `is_active`, `has_phone`, `has_email`, `created_at`. Телефон и
e-mail наружу не отдаются, только признак наличия.

**ConsentState** — `purpose`, `granted`, `policy_code`, `policy_version`, `granted_at`,
`revoked_at`.

**TaskView** — `id`, `subject` (`math`, `physics`), `grade`, `topic`, `status`
(`active`, `solved`, `abandoned`), `steps`, `summary`, `started_at`, `solved_at`, `messages`.

**TaskDetail** — задача с полем `thread`: сообщения диалога (`author` — `student` или `tutor`,
`content`, `created_at`).

**TaskStatistics** — `total`, `solved`, `active`, `recent_topics`.

**GradeOverview** — `grade`, `students`, `tasks_total`, `tasks_solved`, `topics`
(список `{topic, total, solved}`).

**RiskStudent** — `user_id`, `name`, `grade`, `unsolved`, `stuck_topics`.

**ChildView** — `user_id`, `name`, `grade`.

**DigestView** — `student`, `started`, `solved`, `topics`, `daily` (день, начато, решено),
`last_activity_at`.

**NotificationView** — `id`, `kind`, `title`, `body`, `payload`, `created_at`, `read_at`.

**PolicyView** — `code`, `version`, `title`, `body` (разметка Markdown, отображается
мини-приложением без вставки HTML).

**PersonalDataReport** — `profile`, `consents`, `tasks_total`, `notifications_total`,
`audit_entries` (действие, результат, объект, время).

**HealthResponse** — `status` (`ok`, `degraded`), `version`, `database` (`up`, `down`),
`max_api` (`configured`, `missing`), `gigachat` (`ready`, `disabled`), `time`.

Значения перечислений задач: предметы `math`, `physics`; статусы `active`, `solved`, `abandoned`;
роли `student`, `parent`, `teacher`, `administrator`; цели согласий `service`, `notifications`,
`ai_processing`.
