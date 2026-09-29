.PHONY: help install dev lint typecheck test migrate revision up down logs backup seed openapi submit-archive

help:
	@echo "install    - установить зависимости backend и miniapp"
	@echo "dev        - локальный запуск API с автоперезагрузкой"
	@echo "lint       - ruff + eslint"
	@echo "typecheck  - mypy + tsc"
	@echo "test       - pytest + vitest"
	@echo "migrate    - применить миграции БД"
	@echo "revision   - создать миграцию (m='описание')"
	@echo "up/down    - docker compose up -d / down"
	@echo "backup     - дамп БД в backups/"
	@echo "openapi    - обновить openapi.yaml из кода FastAPI"
	@echo "submit-archive - архив исходников с контрольной суммой"

install:
	cd backend && pip install -e ".[dev]"
	cd miniapp && npm ci

dev:
	cd backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

lint:
	cd backend && ruff check . && ruff format --check .
	cd miniapp && npm run lint

typecheck:
	cd backend && mypy app
	cd miniapp && npm run typecheck

test:
	cd backend && pytest
	cd miniapp && npm run test

migrate:
	cd backend && alembic upgrade head

revision:
	cd backend && alembic revision --autogenerate -m "$(m)"

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f --tail=200

backup:
	mkdir -p backups
	docker compose exec -T postgres pg_dump -U $${POSTGRES_USER} -Fc $${POSTGRES_DB} > backups/db-$$(date +%Y%m%d-%H%M%S).dump

openapi:
	cd backend && python -m app.cli openapi --out ../openapi.yaml

submit-archive:
	git archive --format=zip --prefix=uchusai/ -o uchusai-src.zip HEAD
	@sh -c 'sha256sum uchusai-src.zip > uchusai-src.zip.sha256'
	@echo "Готово: uchusai-src.zip и uchusai-src.zip.sha256"
