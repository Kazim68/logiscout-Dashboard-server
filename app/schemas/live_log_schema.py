from typing import Optional, Dict, Literal, List, Union
from pydantic import BaseModel, Field


class LiveLogEntrySchema(BaseModel):
    id: str
    timestamp: str
    level: Literal["error", "warning", "info", "success"]
    service: str
    message: str
    metadata: Optional[Dict[str, str]] = None


class LiveLogIngestItem(BaseModel):
    project_id: str = Field(..., min_length=1)
    level: Literal["error", "warning", "info", "success"]
    service: str = Field(..., min_length=1, max_length=200)
    message: str = Field(..., min_length=1)
    metadata: Optional[Dict[str, str]] = None
    id: Optional[str] = None
    timestamp: Optional[str] = None
