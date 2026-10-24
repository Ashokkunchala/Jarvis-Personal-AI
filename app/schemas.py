from typing import Literal
from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=8000)
    language: Literal["auto", "en", "te"] = "auto"


class ChatResponse(BaseModel):
    reply: str
    model: str
    language: str
