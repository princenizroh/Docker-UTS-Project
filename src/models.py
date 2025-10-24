from pydantic import BaseModel, Field, field_validator, ConfigDict
from typing import Dict, Any, Optional
from datetime import datetime
import uuid


class Event(BaseModel):
    """
    Model untuk event yang diterima oleh aggregator.
    Sesuai spesifikasi: topic, event_id, timestamp, source, payload
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "topic": "user.login",
                "event_id": "evt-123456",
                "timestamp": "2025-10-24T10:30:00Z",
                "source": "auth-service",
                "payload": {
                    "user_id": "user123",
                    "ip": "192.168.1.1"
                }
            }
        }
    )

    topic: str = Field(..., description="Nama topic/kategori event")
    event_id: str = Field(..., description="ID unik untuk event (untuk deduplication)")
    timestamp: str = Field(..., description="Timestamp dalam format ISO8601")
    source: str = Field(..., description="Sumber event")
    payload: Dict[str, Any] = Field(default_factory=dict, description="Data payload event")

    @field_validator('event_id')
    @classmethod
    def validate_event_id(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("event_id tidak boleh kosong")
        return v

    @field_validator('topic')
    @classmethod
    def validate_topic(cls, v):
        if not v or len(v.strip()) == 0:
            raise ValueError("topic tidak boleh kosong")
        return v

    @field_validator('timestamp')
    @classmethod
    def validate_timestamp(cls, v):
        try:
            # Validasi format ISO8601
            datetime.fromisoformat(v.replace('Z', '+00:00'))
        except ValueError:
            raise ValueError(f"timestamp harus dalam format ISO8601: {v}")
        return v


class PublishRequest(BaseModel):
    """
    Request model untuk endpoint /publish
    Bisa menerima single event atau batch events
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "events": [
                    {
                        "topic": "user.login",
                        "event_id": "evt-001",
                        "timestamp": "2025-10-24T10:30:00Z",
                        "source": "auth-service",
                        "payload": {"user_id": "user123"}
                    }
                ]
            }
        }
    )

    events: list[Event] = Field(..., description="List event yang akan dipublish")


class PublishResponse(BaseModel):
    """
    Response model untuk endpoint /publish
    """
    status: str = Field(..., description="Status operasi")
    received: int = Field(..., description="Jumlah event yang diterima")
    message: str = Field(..., description="Pesan detail")


class Stats(BaseModel):
    """
    Model untuk statistik sistem
    Endpoint GET /stats
    """
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "received": 1000,
                "unique_processed": 800,
                "duplicate_dropped": 200,
                "topics": 5,
                "uptime": 3600.5
            }
        }
    )

    received: int = Field(default=0, description="Total event yang diterima")
    unique_processed: int = Field(default=0, description="Total event unik yang diproses")
    duplicate_dropped: int = Field(default=0, description="Total duplikat yang di-drop")
    topics: int = Field(default=0, description="Jumlah topic unik")
    uptime: float = Field(default=0.0, description="Uptime sistem dalam detik")


class EventsResponse(BaseModel):
    """
    Response model untuk endpoint GET /events
    """
    topic: Optional[str] = Field(None, description="Topic filter yang digunakan")
    total: int = Field(..., description="Total event yang dikembalikan")
    events: list[Event] = Field(..., description="List event")
