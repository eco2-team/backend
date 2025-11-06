from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional

app = FastAPI(
    title="Recycle Info API",
    description="재활용 정보 서비스 - 품목별 분리배출 안내",
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
class RecycleItem(BaseModel):
    id: int
    name: str
    category: str
    subcategory: Optional[str] = None
    disposal_method: str
    notes: List[str] = []
    recyclable: bool


class Category(BaseModel):
    id: int
    name: str
    icon: str
    item_count: int


class SearchRequest(BaseModel):
    query: str


class FAQ(BaseModel):
    id: int
    question: str
    answer: str
    category: str


@app.get("/health")
def health():
    return {"status": "healthy", "service": "recycle-info-api"}


@app.get("/ready")
def ready():
    return {"status": "ready", "service": "recycle-info-api"}


@app.get("/api/v1/recycle/items/{item_id}", response_model=RecycleItem)
async def get_item(item_id: int):
    """품목 정보 조회"""
    # TODO: DB에서 품목 조회
    return {
        "id": item_id,
        "name": "페트병",
        "category": "플라스틱",
        "subcategory": "PET",
        "disposal_method": "내용물을 비우고 세척 후 라벨 제거, 압착하여 배출",
        "notes": [
            "뚜껑과 라벨은 별도 분리",
            "음료 잔여물은 완전히 제거",
            "압착하면 보관 공간 절약",
        ],
        "recyclable": True,
    }


@app.get("/api/v1/recycle/categories", response_model=List[Category])
async def get_categories():
    """카테고리 목록"""
    # TODO: DB에서 카테고리 조회
    return [
        {"id": 1, "name": "플라스틱", "icon": "🧴", "item_count": 50},
        {"id": 2, "name": "종이", "icon": "📄", "item_count": 30},
        {"id": 3, "name": "유리", "icon": "🍾", "item_count": 20},
        {"id": 4, "name": "금속", "icon": "🥫", "item_count": 15},
    ]


@app.post("/api/v1/recycle/search", response_model=List[RecycleItem])
async def search_items(request: SearchRequest):
    """품목 검색"""
    # TODO: Elasticsearch 또는 DB 전문 검색
    return [
        {
            "id": 1,
            "name": "페트병",
            "category": "플라스틱",
            "disposal_method": "세척 후 압착 배출",
            "notes": [],
            "recyclable": True,
        }
    ]


@app.get("/api/v1/recycle/rules/{region}")
async def get_regional_rules(region: str):
    """지역별 배출 규정"""
    # TODO: 지역별 규정 조회
    return {
        "region": region,
        "rules": [
            "투명 페트병은 별도 배출",
            "스티로폼은 요일제 배출",
            "음식물은 물기 제거 후 배출",
        ],
    }


@app.get("/api/v1/recycle/faq", response_model=List[FAQ])
async def get_faq(
    category: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=50),
):
    """FAQ 목록"""
    # TODO: DB에서 FAQ 조회
    return [
        {
            "id": 1,
            "question": "페트병 라벨은 어떻게 제거하나요?",
            "answer": "물에 담가두면 쉽게 벗겨집니다. 또는 칼로 잘라내세요.",
            "category": "플라스틱",
        }
    ]


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="0.0.0.0", port=8000)
