"""API v1 路由聚合。"""

from fastapi import APIRouter

from app.api.v1 import auth, chat, conversations, documents

api_router = APIRouter()

api_router.include_router(auth.router)
api_router.include_router(documents.router)
api_router.include_router(conversations.router)
api_router.include_router(chat.router)
