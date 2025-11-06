from typing import List, Optional

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

app = FastAPI(
    title="Location API",
    description="지도/위치 서비스 - Kakao Map API 연동",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic 모델
class Coordinates(BaseModel):
    latitude: float
    longitude: float


class Location(BaseModel):
    id: int
    name: str
    type: str  # "bin" | "center"
    address: str
    coordinates: Coordinates
    distance: Optional[float] = None  # km


class GeocodeRequest(BaseModel):
    address: str


class GeocodeResponse(BaseModel):
    address: str
    coordinates: Coordinates


@app.get("/health")
def health():
    return {"status": "healthy", "service": "location-api"}


@app.get("/ready")
def ready():
    return {"status": "ready", "service": "location-api"}


@app.get("/api/v1/locations/bins", response_model=List[Location])
async def find_nearby_bins(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius: int = Query(1000, ge=100, le=10000, description="반경(m)"),
):
    """근처 분리수거함 검색"""
    # TODO: Kakao Local API 호출 또는 자체 DB 조회
    return [
        {
            "id": 1,
            "name": "강남구청 앞 수거함",
            "type": "bin",
            "address": "서울특별시 강남구 삼성로 xx",
            "coordinates": {"latitude": lat + 0.001, "longitude": lon + 0.001},
            "distance": 0.3,
        }
    ]


@app.get("/api/v1/locations/centers", response_model=List[Location])
async def find_nearby_centers(
    lat: float = Query(..., ge=-90, le=90),
    lon: float = Query(..., ge=-180, le=180),
    radius: int = Query(5000, ge=100, le=50000),
):
    """근처 재활용 센터 검색"""
    # TODO: DB에서 재활용 센터 조회
    return [
        {
            "id": 1,
            "name": "강남구 재활용센터",
            "type": "center",
            "address": "서울특별시 강남구 xxx",
            "coordinates": {"latitude": lat + 0.01, "longitude": lon + 0.01},
            "distance": 2.5,
        }
    ]


@app.post("/api/v1/locations/geocode", response_model=GeocodeResponse)
async def geocode(request: GeocodeRequest):
    """주소 → 좌표 변환"""
    # TODO: Kakao Local API 호출
    return {
        "address": request.address,
        "coordinates": {"latitude": 37.5665, "longitude": 126.9780},
    }


@app.post("/api/v1/locations/reverse-geocode")
async def reverse_geocode(coordinates: Coordinates):
    """좌표 → 주소 변환"""
    # TODO: Kakao Local API 호출
    return {"coordinates": coordinates, "address": "서울특별시 중구 세종대로 110"}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
