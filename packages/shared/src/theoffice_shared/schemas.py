from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    """API health payload shared by BFF and clients."""

    status: str = Field(default="ok", description="Service status.")
