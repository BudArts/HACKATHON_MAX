# Развёртывание

## Требования

| Параметр | Минимум | Комментарий |
| --- | --- | --- |
| Размещение | Сервер в Российской Федерации | Требование локализации, ст. 18 ч. 5 152-ФЗ |
| ОС | Debian 12 / Ubuntu 22.04 или новее | x86-64 |
| CPU / RAM | 2 vCPU / 4 ГБ | Достаточно для школы до 1500 пользователей |
| Диск | 30 ГБ SSD | База, образы, журналы, резервные копии |
| Docker | 24+ с Compose v2 | Единственная зависимость инфраструктуры |
| Сеть | Входящий 443 (и 80 для редиректа), исходящий 443 | Доступ к `platform-api2.max.ru`, `api.giga.chat`, `ngw.devices.sberbank.ru:9443` |
| Домен | A-запись на адрес сервера | Значение `APP_DOMAIN`, используется nginx и мини-приложением MAX |

База данных доступна только из внутренней сети compose, наружу опубликованы порты 80 и 443 nginx.

## Сертификаты

В каталог `deploy/certs/` кладутся:

| Файл | Назначение |
| --- | --- |
| `fullchain.pem`, `privkey.pem`, `chain.pem` | Сертификат сайта для nginx |
| `russian_trusted_root_ca.pem` | Корневой и промежуточный сертификаты Минцифры (склеенные в один файл) для исходящих TLS-соединений к MAX и GigaChat |

Сертификаты Минцифры скачиваются с официальной страницы и склеиваются — MAX отдаёт не всю цепочку,
поэтому одного корневого недостаточно:

```bash
curl -fsSL -o /tmp/nuc-root.crt https://gu-st.ru/content/lending/russian_trusted_root_ca_pem.crt
curl -fsSL -o /tmp/nuc-sub.crt https://gu-st.ru/content/lending/russian_trusted_sub_ca_pem.crt
cat /tmp/nuc-root.crt /tmp/nuc-sub.crt > deploy/certs/russian_trusted_root_ca.pem
grep -c "BEGIN CERTIFICATE" deploy/certs/russian_trusted_root_ca.pem   # 2
```

Каталог монтируется в контейнеры backend, worker и proxy. Пути к корневому сертификату задаются
переменными `MAX_CA_BUNDLE` и `GIGACHAT_CA_BUNDLE` (в контейнере — `/etc/ssl/uchusai/…`).

Сертификат сайта выпускается любым удостоверяющим центром. Для бесплатного выпуска Let's Encrypt по
HTTP-01 каталог `deploy/acme/` проброшен в nginx как `/var/www/acme`:

```bash
certbot certonly --webroot -w ./deploy/acme -d "$APP_DOMAIN" \
  --deploy-hook "cp /etc/letsencrypt/live/$APP_DOMAIN/{fullchain.pem,privkey.pem,chain.pem} ./deploy/certs/"
```

Файлы сертификатов и ключей исключены из репозитория (`.gitignore`).

## Конфигурация

```bash
cp .env.example .env
```

Обязательные значения:

| Переменная | Как получить |
| --- | --- |
| `APP_DOMAIN`, `APP_BASE_URL` | Домен сервиса, например `school-12.ru` и `https://school-12.ru` |
| `POSTGRES_PASSWORD`, `DATABASE_URL` | Надёжный пароль; строка подключения должна совпадать с паролем |
| `SECRET_KEY` | `openssl rand -hex 32` |
| `FIELD_ENCRYPTION_KEY` | `openssl rand -hex 32`, отдельный от `SECRET_KEY` |
| `MAX_BOT_TOKEN` | Токен бота из кабинета разработчика MAX |
| `MAX_WEBHOOK_SECRET` | `openssl rand -hex 32`; MAX принимает значение, соответствующее `^[A-Za-z0-9_-]{5,256}$` |
| `MAX_WEBHOOK_URL` | `https://<домен>/webhook/max` |
| `GIGACHAT_CREDENTIALS` | Ключ авторизации GigaChat |
При `APP_ENV=production` выполняются проверки: `SECRET_KEY` и `FIELD_ENCRYPTION_KEY` не короче 32
символов, при `MAX_TRANSPORT=webhook` задан `MAX_WEBHOOK_SECRET`, а `DATABASE_URL` не указывает на
SQLite. Без выполнения условий процесс не поднимется — сообщение с перечнем недостающих переменных уходит в
журнал.

## Профили развёртывания

Состав запуска регулируется переменными `.env`, менять compose-файл не нужно:

| Профиль | Значения | Что получается |
| --- | --- | --- |
| Локальная проверка (по умолчанию) | `SSL_ENABLED=false`, `APP_ENV=development`, `MAX_TRANSPORT=polling`, `DEV_LOGIN_ENABLED=true`, `SEED_DEMO=true` | Сервис на `http://localhost:8080` после `docker compose up -d`: бот через long polling без публичного адреса, в браузере выбор кабинета, демо-данные |
| Боевой контур | `APP_ENV=production`, `SSL_ENABLED=true`, `HTTP_PORT=80`, `HTTPS_PORT=443`, `MAX_TRANSPORT=webhook`, `DEV_LOGIN_ENABLED=false`, `SEED_DEMO=false`, доменные `APP_DOMAIN` и `APP_BASE_URL` | Публичный сервис с TLS; вход в мини-приложение только из MAX |

При `APP_ENV=production` отклоняются демонстрационные секреты (префикс `dev-only-`, `CHANGE_ME`) и
значение `DEV_LOGIN_ENABLED=true` — контейнер backend завершится с ошибкой конфигурации.

## Первый запуск

### Локальная проверка

```bash
cp .env.example .env        # вписать MAX_BOT_TOKEN
docker compose up -d --build
docker compose ps           # все сервисы healthy
curl http://localhost:8080/healthz
```

Контейнер backend при старте сам готовит базу (`RUN_MIGRATIONS`), публикует редакции юридических
документов (`SYNC_POLICIES`), заполняет демо-данные при `APP_ENV=development` (`SEED_DEMO`) и
регистрирует команды меню бота (`REGISTER_BOT_COMMANDS`). Каждое действие отключается значением
`false`. Логи: `docker compose logs -f backend worker`.

### Боевой контур

```bash
cp .env.example .env        # заполнить боевые значения, см. «Профили развёртывания»
docker compose up -d --build
docker compose ps

# проверка токена бота и профиля MAX
docker compose exec backend python -m app.cli me

# подписка на события (транспорт webhook, после публикации сертификата и открытия 443 порта)
docker compose exec backend python -m app.cli webhook set \
  --url "$MAX_WEBHOOK_URL" --secret "$MAX_WEBHOOK_SECRET"

# роли педагогов и администраторов
docker compose exec backend python -m app.cli grant-role teacher --max-user-id 123456789
docker compose exec backend python -m app.cli grant-role administrator --max-user-id 987654321
```

Порядок важен: `webhook set` выполняется после публикации сертификата и открытия 443 порта.

Проверка результата:

```bash
curl -s https://"$APP_DOMAIN"/healthz
```

Ожидаемый ответ — `"status":"ok"`, `"database":"up"`, `"max_api":"configured"`,
`"assistant":"ready"` при включённом GigaChat.

## Интеграция с MAX

1. Токен выданного бота — в `MAX_BOT_TOKEN`. Имя бота (username) возвращается запросом
   `GET /me`; его же печатает команда `app.cli me` — по username бота находят в MAX.
2. Мини-приложение разместить по публичной HTTPS-ссылке (`https://<домен>/`) и передать адрес через
   [форму организаторов](https://sbor-ssylok-dlya-mini-prilojeniy.testograf.ru/); привязку к боту
   выполняют организаторы, регистрация в «MAX для партнёров» не требуется. Приложение открывается
   кнопкой `open_app` в боте и по ссылке `https://max.ru/<имя-бота>?startapp=<payload>`.
3. Выбрать транспорт:
   - `MAX_TRANSPORT=webhook` — боевой режим. Требования MAX: HTTPS на 443 порт с сертификатом
     доверенного центра (самоподписанные не принимаются), ответ 200 в течение 30 секунд, до десяти
     повторных доставок с интервалом 60 секунд и множителем 2,5, автоматическая отписка при восьми
     часах ошибок. Подписка создаётся командой `app.cli webhook set`.
   - `MAX_TRANSPORT=polling` — режим по умолчанию и отладка без публичного адреса: сервис сам
     забирает обновления методом long polling.
   - `MAX_TRANSPORT=disabled` — API без бота.
4. Проверить сценарии: `/start` в боте показывает запрос согласия, после принятия — клавиатуру с
   кнопками «Личный кабинет» и «Мои задачи».

Значения `startapp` (`start_param`), которые распознаёт мини-приложение: `cabinet`,
`legal`. Ограничение MAX на длину — `^[A-Za-z0-9_-]{0,512}$`.

На онлайн-этапе название, ник и логотип выданного бота не меняются; административные настройки бота
недоступны участникам — если сценарию нужна настройка, недоступная через Bot API, её запрашивают у
организаторов. Сервис работает только через Bot API по выданному токену.

Сервис не использует удалённые методы MAX API (`GET /chats` удалён в июне 2026,
`POST /chats/{chatId}/members` выводится из эксплуатации 30 сентября 2026): отправка идёт в диалог
по `user_id`.

## GigaChat

| Параметр | Значение |
| --- | --- |
| Авторизация | `POST https://ngw.devices.sberbank.ru:9443/api/v2/oauth`, `Authorization: Basic base64(GIGACHAT_CREDENTIALS)`, заголовок `RqUID` — UUID запроса, `scope=GIGACHAT_API_PERS` |
| Токен доступа | Действует 30 минут, кэшируется сервисом |
| Запросы | `POST https://api.giga.chat/v1/chat/completions`, модель `GIGACHAT_MODEL` |
| Лимит | До 10 запросов в секунду на ключ; сервис дополнительно ограничивает `AI_RATE_LIMIT_PER_HOUR` на пользователя |
| TLS | Требуется корневой сертификат Минцифры (`GIGACHAT_CA_BUNDLE`) |

Наставник отключается без остановки сервиса, если `GIGACHAT_ENABLED=false`, ключ не задан или
внешний вызов завершился ошибкой: ученик получает сообщение о временной недоступности и может
повторить позже. Перед отправкой
текст обезличивается, в ответе восстанавливаются только имена.

## Обновление версии

```bash
git pull
docker compose build
# миграции применяются контейнером backend автоматически при старте
docker compose up -d
docker compose logs -f --tail=100
```

Мини-приложение собирается внутри образа nginx (стадия `miniapp` в `deploy/nginx/Dockerfile`),
отдельной публикации статики не требуется.

Откат: вернуть предыдущий коммит, пересобрать образы и, если применялась миграция схемы, откатить
её ревизией Alembic (`alembic downgrade -1`) либо восстановить базу из копии.

## Резервное копирование

```bash
make backup          # pg_dump в backups/db-<метка времени>.dump
```

Восстановление:

```bash
docker compose exec -T postgres pg_restore -U "$POSTGRES_USER" -d "$POSTGRES_DB" --clean --if-exists < backups/db-20260929-1200.dump
```

Резервные копии хранятся на территории РФ. Проверка восстановления — не реже раза в квартал;
журналы контейнеров и `.env` в копию не включаются, их сохраняют отдельно.

## Мониторинг и журналы

- `GET /healthz` — состояние базы, наличие токена MAX, готовность наставника, версия. Используется
  healthcheck'ами контейнеров и внешним мониторингом.
- `GET /readyz` — проверка соединения с базой для оркестратора.
- `docker compose logs -f --tail=200 backend worker proxy` — журналы в формате JSON (structlog):
  `event`, `level`, `timestamp`, `request_id`, `method`, `path`, `status`, `duration_ms`.
- Ключевые события журнала: `auth_rejected`, `token_rejected`, `webhook_rejected`,
  `max_transport_error`, `outbox_failed`, `retention_cycle`, `assistant_skipped`, `policy_published`.
- Внешний мониторинг: проверка `/healthz` раз в минуту, алерт при `"status":"degraded"`, контроль
  свободного места и возраста последней резервной копии.

События безопасности (отказы во входе, превышения лимитов, отзывы согласий, заявления об удалении)
дополнительно попадают в таблицу `audit_events` и доступны для выборки.

## Диагностика

| Симптом | Вероятная причина | Действие |
| --- | --- | --- |
| `"database":"down"` в `/healthz` | База не поднята или неверный `DATABASE_URL` | `docker compose ps`, журнал postgres, сверить пароль и имя базы |
| `max_transport_error` при старте | Нет исходящего доступа, неверный токен, отсутствует корневой сертификат | `app.cli me`, проверить `MAX_CA_BUNDLE` и сетевые правила |
| События бота не приходят | Подписка не создана, секрет не совпадает, автоотписка после восьми часов ошибок | `app.cli webhook info`, при необходимости `webhook set` заново |
| Мини-приложение показывает «Вход не выполнен» | Неверный `MAX_BOT_TOKEN` (подпись `initData` не проходит), часы на сервере расходятся | Сверить токен с кабинетом MAX, включить синхронизацию времени |
| Кнопка «Личный кабинет» не появляется | Профиль бота не загрузился, имя бота неизвестно | `app.cli me`, затем перезапуск backend |
| Наставник не отвечает ученику | `GIGACHAT_ENABLED=false`, неверный ключ, отсутствие согласия `ai_processing` | `/healthz` (`gigachat`), журнал `tutor_*`, проверить согласие ученика |
| Уведомления не уходят в MAX | Очередь не разбирается, пользователь остановил бота, лимит двух сообщений в секунду | Журнал `outbox_dispatched` и `outbox_failed`, статусы в `outbox_messages`, `bot_stopped_at` |
| 429 на входе | Сработал лимит 10 попыток в минуту на IP | Проверить, не идёт ли трафик через один NAT; при необходимости изменить лимиты nginx и `RATE_LIMIT_PER_MINUTE` |
| Белый экран мини-приложения | Неверный `root` или CSP блокирует скрипт | Журнал proxy, консоль браузера, проверить `script-src` и сборку `miniapp/dist` в образе |

## Локальный демо-режим

Для проверки без Docker и без доступа к MAX используется SQLite:

```bash
cd backend
cp ../.env.example .env
# APP_ENV=development
# DATABASE_URL=sqlite+aiosqlite:///./demo.sqlite3
# MAX_TRANSPORT=disabled
# GIGACHAT_ENABLED=false
# MINIAPP_AUTH_WINDOW_SECONDS=86400

python -m app.cli init-db
python -m app.cli policies
python -m app.cli seed --force
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Мини-приложение запускается отдельно (`cd miniapp && npm ci && npm run dev`) и проксирует `/api` и
`/healthz` на backend. Вне MAX вход выполняется по переменной `VITE_DEV_INIT_DATA` — подписанной
строке стартовых данных демо-пользователя; строку печатает команда
`python -m app.cli dev-init-data --max-user-id 9100001 --first-name "Мария" --last-name "Ковалёва"`
(отключена при `APP_ENV=production`), значение кладётся в `miniapp/.env.development.local`.
Учитывается оно только сборкой `vite dev`.

Подробная инструкция для рабочего компьютера — [docs/quickstart.md](quickstart.md).

Демо-данные: СОШ № 12, классы 7А и 8А, два педагога, пять учеников, два родителя с подтверждённой
привязкой, шесть задач (решённые, активные, заброшенная). В production использование SQLite запрещено
проверкой конфигурации.

## Чек-лист приёмки

- [ ] Домен разрешается в адрес сервера, сертификат действителен, HTTP редиректит на HTTPS.
- [ ] `/healthz` возвращает `"status":"ok"`, `"database":"up"`, `"max_api":"configured"`.
- [ ] `/docs` и `/openapi.json` недоступны в production.
- [ ] Миграции применены, редакции документов опубликованы (`GET /api/v1/legal` отдаёт четыре документа).
- [ ] Бот отвечает на `/start`, запрашивает согласие, показывает клавиатуру с кнопкой мини-приложения.
- [ ] Мини-приложение открывается из бота, вход по `initData` проходит, экран согласия отображается.
- [ ] Ученик присылает задачу, наставник ведёт наводящими вопросами, задача фиксируется в базе.
- [ ] Роль педагога назначена приказом и командой `grant-role`.
- [ ] В кабинете доступна выписка по персональным данным, отзыв согласия и удаление работают.
- [ ] Настроено резервное копирование, выполнено пробное восстановление копии.
- [ ] Токены MAX и GigaChat выпущены заново после передачи в переписке.
