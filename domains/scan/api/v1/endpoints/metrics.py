from fastapi import APIRouter, Depends

from domains.scan.services.scan import ScanService

router = APIRouter(prefix="/metrics", tags=["metrics"])


@router.get("/", summary="Scan service metrics")
async def metrics(service: ScanService = Depends()):
    return await service.metrics()
