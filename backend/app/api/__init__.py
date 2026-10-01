from fastapi import APIRouter
from app.api.auth import router as auth_router
from app.api.crimes import router as crimes_router
from app.api.risk import router as risk_router
from app.api.sos import router as sos_router
from app.api.patrols import router as patrols_router
from app.api.prp import router as prp_router
from app.api.admin import router as admin_router
from app.api.contacts import router as contacts_router
from app.api.help_points import router as help_points_router
from app.api.analytics import router as analytics_router

api_router = APIRouter()

api_router.include_router(auth_router)
api_router.include_router(crimes_router)
api_router.include_router(risk_router)
api_router.include_router(sos_router)
api_router.include_router(patrols_router)
api_router.include_router(prp_router)
api_router.include_router(admin_router)
api_router.include_router(contacts_router)
api_router.include_router(help_points_router)
api_router.include_router(analytics_router)

__all__ = ["api_router"]
