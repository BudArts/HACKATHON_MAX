#!/bin/sh
set -e

if [ "$RUN_MIGRATIONS" != "false" ]; then
    echo "Готовлю схему базы данных"
    python -m app.cli init-db
fi

if [ "$SYNC_POLICIES" != "false" ]; then
    python -m app.cli policies >/dev/null || echo "Не удалось опубликовать редакции документов"
fi

if [ "$SEED_DEMO" != "false" ] && [ "$APP_ENV" = "development" ]; then
    python -m app.cli seed >/dev/null 2>&1 || true
fi

if [ "$REGISTER_BOT_COMMANDS" != "false" ] && [ -n "$MAX_BOT_TOKEN" ] && [ "$MAX_TRANSPORT" != "disabled" ]; then
    python -m app.cli commands >/dev/null 2>&1 || echo "Команды меню бота не зарегистрированы"
fi

exec "$@"
