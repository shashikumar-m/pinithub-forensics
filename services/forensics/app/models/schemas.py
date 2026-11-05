"""
Pydantic schemas for the forensic service API.
"""
from pydantic import BaseModel, Field
from typing import Optional, Any
from datetime import datetime


class HealthResponse(BaseModel):
    """Health check response."""
    status: str = "ok"
    service: str = "pinithub-forensics"
    version: str = "0.1.0"
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class ReadyResponse(BaseModel):
    """Readiness check response."""
    status: str
    service: str = "pinithub-forensics"
    checks: dict[str, str]
    timestamp: str = Field(default_factory=lambda: datetime.utcnow().isoformat())


class DetectorResultSchema(BaseModel):
    """Serializable detector result — mirrors DetectorResult."""
    detector: str
    version: str
    category: str
    score: Optional[float] = None
    confidence: Optional[float] = None
    map_path: Optional[str] = None
    details: Optional[dict[str, Any]] = None
    execution_time_ms: Optional[int] = None


class AvailableDetectorSchema(BaseModel):
    """Describes a registered detector."""
    name: str
    version: str
    category: str
    implemented: bool
