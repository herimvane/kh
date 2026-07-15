from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.evaluations import router as evaluations_router
from app.api.master_data import router as master_data_router
from app.api.settings import router as settings_router


api_router = APIRouter(prefix="/api")
api_router.include_router(auth_router)
api_router.include_router(master_data_router)
api_router.include_router(evaluations_router)
api_router.include_router(settings_router)
