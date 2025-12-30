"""Common response schemas for standardized API responses."""

from __future__ import annotations

from typing import Generic, Optional, TypeVar

from pydantic import BaseModel, ConfigDict, Field

DataT = TypeVar("DataT")


class ErrorDetail(BaseModel):
    """Error detail schema."""

    model_config = ConfigDict(exclude_none=True)

    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Human-readable error message")
    field: Optional[str] = Field(None, description="Field name if validation error")


class SuccessResponse(BaseModel, Generic[DataT]):
    """Success response - only success and data fields."""

    success: bool = Field(default=True, description="Always true for success response")
    data: DataT = Field(..., description="Response data")


class ErrorResponse(BaseModel):
    """Error response - only success and error fields."""

    model_config = ConfigDict(exclude_none=True)

    success: bool = Field(default=False, description="Always false for error response")
    error: ErrorDetail = Field(..., description="Error details")
