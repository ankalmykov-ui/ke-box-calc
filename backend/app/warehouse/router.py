from __future__ import annotations

from typing import Callable
from uuid import UUID

from fastapi import APIRouter, HTTPException, Query

from ..db import DatabaseNotConfigured
from . import service
from .models import (
    MaterialCreate,
    OrganizationCreate,
    ReceiptCreate,
    ReversalCreate,
    SiteCreate,
    WarehouseCreate,
    WriteoffConfirm,
)


router = APIRouter(prefix="/api/v1", tags=["v0.9 warehouse"])


def _call(fn: Callable, *args, **kwargs):
    try:
        return fn(*args, **kwargs)
    except DatabaseNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except service.WarehouseNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except service.InsufficientStock as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except service.WarehouseConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/organizations", status_code=201)
def create_organization(req: OrganizationCreate):
    return _call(service.create_organization, req)


@router.post("/sites", status_code=201)
def create_site(req: SiteCreate):
    return _call(service.create_site, req)


@router.post("/warehouses", status_code=201)
def create_warehouse(req: WarehouseCreate):
    return _call(service.create_warehouse, req)


@router.post("/materials", status_code=201)
def create_material(req: MaterialCreate):
    return _call(service.create_material, req)


@router.get("/materials")
def list_materials(organization_id: UUID, include_inactive: bool = False):
    return _call(service.list_materials, organization_id, include_inactive=include_inactive)


@router.post("/stock/receipts", status_code=201)
def create_receipt(req: ReceiptCreate):
    return _call(service.create_receipt, req)


@router.get("/stock/warehouses/{warehouse_id}/balances")
def balances(
    warehouse_id: UUID,
    include_zero: bool = Query(default=False),
):
    return _call(service.list_balances, warehouse_id, include_zero=include_zero)


@router.post("/stock/writeoffs/confirm", status_code=201)
def confirm_writeoff(req: WriteoffConfirm):
    return _call(service.confirm_writeoff, req)


@router.post("/stock/writeoffs/{document_id}/reverse", status_code=201)
def reverse_writeoff(document_id: UUID, req: ReversalCreate):
    return _call(service.reverse_writeoff, document_id, req)
