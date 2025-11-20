from typing import List, Optional

from pydantic import BaseModel


class RecycleItem(BaseModel):
    id: int
    name: str
    category: str
    subcategory: Optional[str] = None
    disposal_method: str
    notes: List[str] = []
    recyclable: bool = True


class RecycleCategory(BaseModel):
    id: int
    name: str
    icon: str
    item_count: int


class RecycleSearchRequest(BaseModel):
    query: str


class RegionalRule(BaseModel):
    region: str
    rules: List[str]


class FAQEntry(BaseModel):
    id: int
    question: str
    answer: str
    category: str
