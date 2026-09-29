# Быстрый запуск и проверка работы

Инструкция для локальной проверки на рабочем компьютере: без Docker, без публичного адреса и без
доступа к MAX. Данные хранятся в файле SQLite, внешние сервисы отключены — этого достаточно, чтобы
пройти сценарии кабинетов ученика, родителя и педагога.

## 1. Что понадобится

| Компонент | Версия | Проверка |
| --- | --- | --- |
| Python | 3.11+ | `python --version` |
| Node.js | 20+ (рекомендуется 22) | `node --version` |
| npm | 10+ | `npm --version` |

Docker и PostgreSQL для локальной проверки не нужны. Доступ в интернет нужен только для установки
зависимостей.

## 2. Вариант с Docker Compose

Если установлен Docker 24+ с Compose v2, этапы 3–7 этой инструкции заменяются тремя командами:

```bash
cp .env.example .env       # вписать MAX_BOT_TOKEN
docker compose up -d
```

Сервис будет на `http://localhost:8080`: база, миграции, редакции документов и демо-данные готовятся
автоматически, бот в MAX работает через long polling без публичного адреса. При открытии
`http://localhost:8080` в браузере мини-приложение показывает выбор кабинета — те же пользователи,
что перечислены ниже в разделе 9. Профили значений и перевод в боевой режим —
[docs/deployment.md](deployment.md).

## 3. Настройка окружения

Из корня репозитория:

**Linux / macOS**

```bash
cd backend
python3 -m venv .venv
. .venv/bin/activate
pip install -e ".[dev]"
```

**Windows (PowerShell)**

```powershell
cd backend
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"
```

Если PowerShell не даёт активировать виртуальное окружение, выполните один раз
`Set-ExecutionPolicy -Scope CurrentUser RemoteSigned` или используйте `.venv\Scripts\python.exe`
вместо `python` в командах ниже.

## 4. Файл конфигурации

Создайте `backend/.env` со следующим содержимым (Linux/macOS: `cp ../.env.example .env` и затем
замените значения; Windows — создайте файл вручную):

```ini
APP_NAME=УчусьИИ
APP_ENV=development
APP_DEBUG=true
APP_BASE_URL=http://localhost:8000
API_PREFIX=/api/v1
CORS_ALLOWED_ORIGINS=

DATABASE_URL=sqlite+aiosqlite:///./demo.sqlite3

SECRET_KEY=local-development-secret-key-0123456789abcdef
FIELD_ENCRYPTION_KEY=local-development-field-key-0123456789abcdef
ACCESS_TOKEN_TTL_MINUTES=30
REFRESH_TOKEN_TTL_DAYS=14
MINIAPP_AUTH_WINDOW_SECONDS=86400

MAX_BOT_TOKEN=local-development-bot-token-0123456789
MAX_TRANSPORT=disabled
MAX_WEBHOOK_SECRET=local-development-webhook-secret-0123456789

GIGACHAT_ENABLED=false

LOG_LEVEL=INFO
```

Значения ключей здесь — демонстрационные, для локальной проверки их достаточно. Файл `.env`
исключён из репозитория и не должен попадать в git.

`MINIAPP_AUTH_WINDOW_SECONDS=86400` увеличивает срок жизни подписанных стартовых данных до суток,
чтобы не перегенерировать их каждый час.

## 5. База данных и демо-данные

```bash
python -m app.cli init-db      # создать схему (файл demo.sqlite3)
python -m app.cli policies     # опубликовать редакции юридических документов
python -m app.cli seed --force # школа, классы 7А и 8А, ученики, родители, задачи
```

Ожидаемый вывод последней команды:

```
Заполнено: СОШ № 12, классов 2, педагогов 2, учеников 5, родителей 2, задач 6
```

## 6. Запуск API

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

Проверка в отдельном окне:

```bash
curl http://localhost:8000/healthz
```

Ответ должен содержать `"status":"ok"`, `"database":"up"`, `"gigachat":"disabled"`.
Сообщение `bot_profile_unavailable` при старте — норма для демо-режима: сервис не обращается к MAX.

## 7. Стартовые данные для входа

Вне MAX мини-приложение не получает `initData` от мессенджера, поэтому в режиме разработки
используется подписанная строка. Сгенерируйте её для демо-ученика:

```bash
python -m app.cli dev-init-data --max-user-id 9100101 --first-name "Артём" --last-name "Ковалёв"
```

Команда печатает одну строку вида `query_id=…&auth_date=…&user=…&chat=…&hash=…` — это и есть
`initData`. Скопируйте её целиком.

Положите значение в файл `miniapp/.env.development.local` (файл создаётся вручную, в git не
попадает):

```ini
VITE_DEV_INIT_DATA="query_id=…&auth_date=…&user=…&chat=…&hash=…"
VITE_BACKEND_ORIGIN="http://127.0.0.1:8000"
```

Альтернатива — передать переменные в командной строке:

```bash
# Linux / macOS
VITE_DEV_INIT_DATA="$(cat /path/to/initdata.txt)" npm run dev

# Windows PowerShell
$env:VITE_DEV_INIT_DATA = "query_id=…&hash=…"
npm run dev
```

Строка действительна сутки (`MINIAPP_AUTH_WINDOW_SECONDS`); если вход перестал проходить —
сгенерируйте новую той же командой.

## 8. Запуск мини-приложения

Вторым окном, из корня репозитория:

```bash
cd miniapp
npm ci          # или npm install, если нет package-lock.json
npm run dev
```

Откройте `http://localhost:5173`.

## 9. Что проверить

Кабинет ученика (демо-ученик Артём Ковалёв, 7А):

1. **Экран согласия** — первое, что показывает сервис: обработка данных и ИИ-обработка, ссылки на
   документы. Без согласия остальные разделы недоступны.
2. **Главная** — приветствие, счётчики «всего/решено/в работе», недавние темы, напоминание, что
   задачи решаются в чате с ботом.
3. **Задачи** — история: «Проценты» (в работе), «Теорема Пифагора» (решено).
4. **Карточка задачи** — тред диалога: сообщение ученика, наводящие вопросы наставника, итог.
5. **Настройки** — профиль, переключатель согласия на ИИ, документы, выход.
6. **Персональные данные** — выписка по ст. 14 152-ФЗ: профиль, согласия с редакциями, счётчики,
   журнал действий; прекращение обработки и удаление.

Кабинет родителя — сгенерируйте стартовые данные для Марии Ковалёвой:

```bash
python -m app.cli dev-init-data --max-user-id 9100001 --first-name "Мария" --last-name "Ковалёва"
```

Запустите второе приложение на другом порту с этим значением:

```bash
VITE_DEV_INIT_DATA="…" npm run dev -- --port 5174
```

Что проверить у родителя: дети (Артём привязан), недельный дайджест — начато/решено, темы,
активность по дням; ввод кода привязки (код ученику выдаёт бот командой `/code`).

Кабинет педагога — стартовые данные для Ольги Лебедевой (классный руководитель 7А):

```bash
python -m app.cli dev-init-data --max-user-id 9000000 --first-name "Ольга" --last-name "Лебедева"
```

Что проверить у педагога: обзор по классам — сколько задач начато и решено, темы класса с долями;
группа риска — ученики с тремя и более нерешёнными задачами за неделю.

Проверка ограничения доступа: раздел «Задачи» недоступен родителю и педагогу, обзор педагога
возвращает 403 ученику, дайджест родителя — только по своим детям.

## 10. Проверка API напрямую

Токен получается из стартовых данных и используется в заголовке `Authorization`:

```bash
INIT="$(python -m app.cli dev-init-data --max-user-id 9100001 --first-name Мария --last-name Ковалёва)"
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/max \
  -H 'Content-Type: application/json' -d "{\"init_data\": \"$INIT\"}" \
  | python -c "import sys,json;print(json.load(sys.stdin)['tokens']['access_token'])")

curl -s -X POST http://localhost:8000/api/v1/consents/service \
  -H "Authorization: Bearer $TOKEN" -H 'Content-Type: application/json' -d '{"accept": true}'
curl -s http://localhost:8000/api/v1/tasks/statistics -H "Authorization: Bearer $TOKEN"
curl -s http://localhost:8000/api/v1/me/personal-data -H "Authorization: Bearer $TOKEN"
curl -s http://localhost:8000/api/v1/legal
```

Полный перечень маршрутов — [docs/api.md](api.md). Интерактивная документация OpenAPI в
демо-режиме: `http://localhost:8000/docs`.

## 11. Тесты и проверки качества

```bash
# backend (из каталога backend, в активированном окружении)
pytest
mypy app
ruff check . && ruff format --check .

# miniapp (из каталога miniapp)
npm run test
npm run typecheck
npm run lint
```

Из корня репозитория то же самое делает `make test`, `make typecheck`, `make lint` (нужен `make`;
на Windows используйте команды напрямую).

## 12. Подключение настоящих MAX и GigaChat

Демо-режим не обращается к внешним сервисам. Чтобы проверить реальную интеграцию:

**Бот MAX (локально, без публичного адреса)** — в `backend/.env`:

```ini
MAX_BOT_TOKEN=<токен вашего бота>
MAX_TRANSPORT=polling
```

После перезапуска API бот отвечает в MAX: `/start` запрашивает класс и согласия, после принятия
ученик присылает задачу. Зарегистрируйте команды меню: `python -m app.cli commands`. События
приходят длинным опросом `GET /updates`, публичный адрес не требуется.

Кнопка «Личный кабинет» в боте открывает мини-приложение MAX — для этого приложение размещается по
публичному HTTPS-адресу, а ссылка передаётся организаторам через
[форму](https://sbor-ssylok-dlya-mini-prilojeniy.testograf.ru/), привязку выполняют они. Локально
кнопка не работает: кабинет проверяется в браузере по стартовым данным из раздела 7.

**GigaChat** — в `backend/.env`:

```ini
GIGACHAT_ENABLED=true
GIGACHAT_CREDENTIALS=<ключ авторизации>
GIGACHAT_CA_BUNDLE=<путь к корневому сертификату Минцифры>
```

Сертификаты НУЦ Минцифры из `deploy/certs` обязательны: без них TLS-соединение с
`ngw.devices.sberbank.ru` не устанавливается. После включения наставник отвечает ученику в боте:
наводящие вопросы, а после самостоятельного решения — разбор; диалоги записываются в базу и
появляются в аналитике педагога и дайджесте родителя. В тексте перед отправкой идентификаторы
заменяются на служебные метки.

Боевое развёртывание с Docker, webhook и nginx — [docs/deployment.md](deployment.md).

## 13. Если что-то не работает

| Симптом | Причина | Решение |
| --- | --- | --- |
| «Вход не выполнен» в мини-приложении | `VITE_DEV_INIT_DATA` не задана, устарела или подписана другим токеном | Пересоздать строку `dev-init-data`, убедиться, что `MAX_BOT_TOKEN` в `.env` совпадает, перезапустить `npm run dev` |
| `pip install -e ".[dev]"` падает | Python старше/младше 3.11 или нет компилятора | Использовать Python 3.11–3.13; на Windows установить Build Tools либо взять предкомпилированные пакеты |
| `ModuleNotFoundError: app` | Команды запускаются не из каталога `backend` | `cd backend` и активировать виртуальное окружение |
| `RuntimeError: Database engine is not initialized` | API запущен без `.env` или с пустым `DATABASE_URL` | Проверить наличие `backend/.env` и путь к файлу базы |
| Запросы к API возвращают 404 | Мини-приложение обращается не к тому порту | Задать `VITE_BACKEND_ORIGIN=http://127.0.0.1:8000` |
| 429 при входе | Лимит 10 попыток в минуту на IP | Подождать минуту |
| `npm ci` сообщает об отсутствии lock-файла | Каталог распакован без `package-lock.json` | Использовать `npm install` |
| Пустые списки задач | База не заполнена | `python -m app.cli seed --force` |
| Экран согласия не уходит после принятия | Не принято согласие `service` | Принять основное согласие; переключатель `ai_processing` необязателен |

Полный перечень диагностических сценариев боевого контура — в разделе «Диагностика»
[docs/deployment.md](deployment.md).
