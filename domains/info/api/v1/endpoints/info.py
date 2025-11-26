from fastapi import APIRouter, Depends, Query

from domains.info.schemas.info import (
    FAQEntry,
    RecycleCategory,
    RecycleItem,
    RecycleSearchRequest,
    RegionalRule,
)
from domains.info.services.info import InfoService

router = APIRouter(prefix="/info", tags=["info"])


@router.get("/items/{item_id}", response_model=RecycleItem, summary="Fetch recycle item detail")
async def get_item(item_id: int, service: InfoService = Depends()):
    return await service.get_item(item_id)


@router.get("/categories", response_model=list[RecycleCategory], summary="List categories")
async def list_categories(service: InfoService = Depends()):
    return await service.list_categories()


@router.post("/search", response_model=list[RecycleItem], summary="Search recycle items")
async def search(
    payload: RecycleSearchRequest,
    service: InfoService = Depends(),
):
    return await service.search(payload)


@router.get("/rules/{region}", response_model=RegionalRule, summary="Regional rules")
async def rules(region: str, service: InfoService = Depends()):
    return await service.regional_rules(region)


@router.get("/faq", response_model=list[FAQEntry], summary="Frequently asked questions")
async def faq(
    category: str | None = Query(default=None),
    skip: int = Query(default=0, ge=0),
    limit: int = Query(default=10, ge=1, le=50),
    service: InfoService = Depends(),
):
    return await service.faq(category=category, skip=skip, limit=limit)
