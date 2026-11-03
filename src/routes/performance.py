import uuid
from typing import Literal

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from src.deps import get_db
from src.schemas.performance import IngestionSummary, PerformanceRunOut, PerformanceSummary, QuerySummary
from src.services import metrics

router = APIRouter(tags=["performance"])


@router.get("/performance", response_model=list[PerformanceRunOut])
async def list_runs(
    operation: Literal["query", "ingestion"] | None = None,
    file_id: uuid.UUID | None = None,
    limit: int = Query(50, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
):
    """Most recent runs first."""
    return await metrics.recent_runs(db, operation, file_id, limit)


@router.get("/performance/summary", response_model=PerformanceSummary)
async def get_summary(file_id: uuid.UUID | None = None, db: AsyncSession = Depends(get_db)):
    return PerformanceSummary(
        query=QuerySummary(**await metrics.query_summary(db, file_id)),
        ingestion=IngestionSummary(**await metrics.ingestion_summary(db, file_id)),
    )
