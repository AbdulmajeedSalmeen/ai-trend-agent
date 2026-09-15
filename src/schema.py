from datetime import datetime 
from typing import Optional, Literal
from pydantic import (BaseModel, Field, field_validator)


class Signal(BaseModel):
    id:str
    source: Literal['github','hackernews']
    tier: Literal[1,2]
    subject:Optional[str] = None
    title:str
    url: str
    published_at: datetime
    body:str = ""


    @field_validator('published_at')
    @classmethod
    def must_be_utc(cls, v):
        if v.tzinfo is None: 
            raise ValueError('published_at must be timezone-aware')
        return v

    
class Claim(BaseModel):
    text:str
    subject:str
    version:Optional[str] = None
    verdict: Literal['confirmed', 'unverified'] = 'unverified'
    evidence_url:Optional[str] = None
    confidence: float = Field(0.2, ge=0.0, le=1.0)


class Trend(BaseModel):
    id:str
    subject: str
    signal_ids: list[str] 
    claims: list[Claim]


class Score(BaseModel):
    trend_id: str
    chapter_id: Optional[str] = None
    confidence: float = Field(ge=0.0, le=1.0)
    dimensions: dict[str, int]
    provenance: dict[str, str]
    priority: float  


class Recommendation(BaseModel):
    trend_id: str
    action: Literal['update_existing_material', 'add_new_lesson', 'watch']
    chapter_id: Optional[str] = None
    rationale: str
