from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import text

from app import __version__
from app.api.schemas import HealthResponse
from app.api.v1 import api_router
from app.api.webhook import router as webhook_router
from app.bot.handlers import register_commands
from app.bot.profile import load_profile
from app.core.config import get_settings
from app.core.errors import register_exception_handlers
from app.core.logging import configure_logging, get_logger
from app.db.base import get_engine, init_engine
from app.integrations.max.client import UPDATE_TYPES
from app.integrations.max.transport import PollingTask
from app.middleware import GlobalRateLimitMiddleware, RequestContextMiddleware, SecurityHeadersMiddleware
from app.runtime import get_runtime, init_runtime
from app.services.consents import ConsentService

log = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings)
    init_engine(settings)
    runtime = init_runtime(settings)

    async for session in get_engine().open_session():
        try:
            await ConsentService(session, settings).sync_policies()
            await session.commit()
        finally:
            await session.close()
        break

    polling: PollingTask | None = None
    try:
        profile = await load_profile(runtime.max_client)
        if profile.ready:
            log.info("bot_profile_loaded", username=profile.username)
            await register_commands(profile)
        if settings.max_transport == "webhook" and settings.max_webhook_url and runtime.max_client.configured:
            await runtime.max_client.subscribe(
                settings.max_webhook_url, settings.max_webhook_secret, UPDATE_TYPES
            )
            log.info("webhook_subscribed", url=settings.max_webhook_url)
        elif settings.max_transport == "polling" and runtime.max_client.configured:
            polling = PollingTask(runtime.max_client)
            polling.start()
    except Exception as exc:
        log.warning("max_bootstrap_skipped", error=str(exc))

    try:
        yield
    finally:
        if polling is not None:
            await polling.stop()
        await runtime.close()
        await get_engine().dispose()
        log.info("shutdown_complete")


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title=settings.app_name,
        version=__version__,
        description=(
            "API ИИ-наставника «УчусьИИ»: вход через MAX, задачи учеников, диалоги с наставником, "
            "аналитика педагога, дайджесты родителя, согласия и персональные данные (152-ФЗ). "
            "Маршруты /dev/* существуют только в режиме локальной проверки (DEV_LOGIN_ENABLED)."
        ),
        docs_url="/docs" if not settings.is_production else None,
        redoc_url=None,
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    app.add_middleware(RequestContextMiddleware)
    app.add_middleware(SecurityHeadersMiddleware, settings=settings)
    app.add_middleware(GlobalRateLimitMiddleware, settings=settings)
    if settings.cors_origins:
        app.add_middleware(
            CORSMiddleware,
            allow_origins=settings.cors_origins,
            allow_credentials=False,
            allow_methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
            expose_headers=["X-Request-ID"],
            max_age=600,
        )

    register_exception_handlers(app)
    app.include_router(webhook_router)
    app.include_router(api_router, prefix=settings.api_prefix)

    @app.get("/healthz", include_in_schema=False)
    async def healthz() -> HealthResponse:
        database = "down"
        max_configured = "missing"
        gigachat = "disabled"
        try:
            runtime = get_runtime()
            max_configured = "configured" if runtime.max_client.configured else "missing"
            gigachat = "ready" if runtime.gigachat.enabled else "disabled"
        except RuntimeError:
            log.warning("healthcheck_runtime_missing")
        try:
            async for session in get_engine().open_session():
                await session.execute(text("SELECT 1"))
                database = "up"
                await session.close()
                break
        except Exception as exc:
            log.error("healthcheck_db_failed", error=str(exc))
        return HealthResponse(
            status="ok" if database == "up" else "degraded",
            version=__version__,
            database=database,
            max_api=max_configured,
            gigachat=gigachat,
            time=datetime.now(),
        )

    @app.get("/readyz", include_in_schema=False)
    async def readyz() -> dict[str, str]:
        async for session in get_engine().open_session():
            await session.execute(text("SELECT 1"))
            await session.close()
            break
        return {"status": "ready"}

    return app


app = create_app()
