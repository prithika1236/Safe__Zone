"""SafeZone Analytics and Academic Evaluation API.

Provides endpoints for:
- Evaluating Reference vs Dynamic vs Baseline patrol deployment strategies
- Fetching live operational summaries for the Admin Dashboard
"""

from fastapi import APIRouter, Depends, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.session import get_async_db
from app.core.security import require_admin
from app.models.user import User
from app.services.analytics_service import analytics_service
from app.schemas.analytics import (
    EvaluationRequest,
    EvaluationComparisonResponse,
    OperationalSummaryResponse,
)

router = APIRouter(prefix="/analytics", tags=["Analytics"])


@router.post(
    "/evaluate",
    response_model=EvaluationComparisonResponse,
    summary="Evaluate Reference vs Dynamic Strategy (Admin Only)",
)
async def evaluate_strategies(
    request: EvaluationRequest = EvaluationRequest(),
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Perform comparative evaluation of Reference vs Dynamic SafeZone PRPs on prototype dataset."""
    return await analytics_service.evaluate_strategies(db=db, req=request)


@router.get(
    "/summary",
    response_model=OperationalSummaryResponse,
    summary="Get Operational Analytics Summary (Admin Only)",
)
async def get_operational_summary(
    db: AsyncSession = Depends(get_async_db),
    current_user: User = Depends(require_admin),
):
    """Retrieve live counts of crimes, patrol units, active PRPs, and emergency incidents."""
    return await analytics_service.get_operational_summary(db=db)
