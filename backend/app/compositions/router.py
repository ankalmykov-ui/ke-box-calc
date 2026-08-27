from __future__ import annotations

from typing import Callable
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from ..db import DatabaseNotConfigured
from . import service
from .models import (
    BctResultCreate,
    CompositionCreate,
    CompositionVersionInput,
    CostSnapshotCreate,
)


router = APIRouter(prefix="/api/v1", tags=["v0.9 compositions"])


def _call(fn: Callable, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except DatabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except service.CompositionNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.CompositionConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/compositions", status_code=201)
def create_composition(req: CompositionCreate):
    return _call(service.create_composition, req)


@router.post("/compositions/{definition_id}/versions", status_code=201)
def create_composition_version(definition_id: UUID, req: CompositionVersionInput):
    return _call(service.create_version, definition_id, req)


@router.get("/compositions")
def list_compositions(
    organization_id: UUID,
    board_grade_code: str | None = Query(default=None),
    profile_code: str | None = Query(default=None),
):
    return _call(
        service.list_compositions,
        organization_id,
        board_grade_code=board_grade_code,
        profile_code=profile_code,
    )


@router.post("/composition-versions/{version_id}/bct-results", status_code=201)
def record_bct(version_id: UUID, req: BctResultCreate):
    return _call(service.record_bct, version_id, req)


@router.post("/composition-versions/{version_id}/cost-snapshots", status_code=201)
def record_cost(version_id: UUID, req: CostSnapshotCreate):
    return _call(service.record_cost, version_id, req)
