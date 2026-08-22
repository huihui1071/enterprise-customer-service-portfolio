from typing import List, Literal, Optional

from pydantic import BaseModel, Field


class TokenRequest(BaseModel):
    user_id: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    expires_in: int


class TicketCreate(BaseModel):
    ticket_type: str
    organization_id: str
    case_id: Optional[str] = None
    summary: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=4000)
    evidence: List[str] = Field(default_factory=list)
    risk_level: Literal["low", "medium", "high", "critical"]
    source: Literal["dify", "web", "api"]
