from __future__ import annotations

from fastapi import APIRouter

from app.api.v1 import auth, consents, dev, notifications, parent, profile, tasks, tutor

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(profile.router)
api_router.include_router(consents.router)
api_router.include_router(tutor.router)
api_router.include_router(tasks.router)
api_router.include_router(notifications.router)
api_router.include_router(dev.router)
api_router.include_router(parent.router)

__all__ = ["api_router"]
