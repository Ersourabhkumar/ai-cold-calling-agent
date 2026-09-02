from pydantic import BaseModel, Field


class TestCallRequest(BaseModel):
    """Trigger exactly one live outbound call through the configured provider."""

    phone: str = Field(min_length=8, max_length=20)
    lead_name: str = Field(default="Demo Customer", min_length=2, max_length=150)
    city: str | None = Field(default=None, max_length=100)
    requirement: str | None = Field(default=None, max_length=500)
    budget: str | None = Field(default=None, max_length=100)
    timeline: str | None = Field(default=None, max_length=100)
    campaign_name: str = Field(
        default="AI Real Estate Demo",
        min_length=2,
        max_length=150,
    )


class TestCallStatusRequest(BaseModel):
    """Optional refresh of a test call; body is currently unused."""

    pass