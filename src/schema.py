from datetime import datetime 
from typing import Optional, Literal
from pydantic import (BaseModel, Field, field_validator)


class Signal(BaseModel):
    id:str
    source: Literal['github','hackernews','pypi']
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
    source_signal_id: Optional[str] = None
    evidence_kind: Optional[Literal['primary_report', 'cross_source', 'registry_match']] = None


class MarketSignal(BaseModel):
    """Whether employers ask for a tool and how widely it is installed. None means
    the source could not be read, which is not the same as nobody wanting it."""
    subject: str
    job_term: Optional[str] = None
    jobs: Optional[int] = None
    downloads: Optional[int] = None
    months: int = 3


class PackageFacts(BaseModel):
    """What PyPI records about a package's whole history, read at collection, so a
    replay judges maturity and prerequisites without the network."""
    subject: str
    pypi: str
    first_release: Optional[datetime] = None
    latest_stable: Optional[str] = None
    requires: list[str] = []


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
    # What the releases changed, read from their notes, and whether the market
    # wants the tool. Kept beside the score so the reason can quote them.
    changes: dict = Field(default_factory=dict)
    market: dict = Field(default_factory=dict)
    # How ready the course is to teach it: maturity, prerequisites and difficulty,
    # kept out of the priority, with what each was measured from.
    feasibility: Optional[float] = None
    factors: dict = Field(default_factory=dict)


class Recommendation(BaseModel):
    trend_id: str
    action: Literal['update_existing_material', 'add_new_lesson', 'add_optional_content',
                    'investigate_larger_change', 'watch']
    chapter_id: Optional[str] = None
    rationale: str
    # Who wrote the English reason: the model, checked for the facts, or the rules.
    rationale_by: Optional[Literal['model', 'rules']] = None
    # The same reason in Arabic, always built from the rules, never the model.
    rationale_ar: Optional[str] = None
    # The first steps a teacher takes, step for step in both languages, from the rules.
    action_plan: list[str] = []
    action_plan_ar: list[str] = []
    # Lines in the course notebooks to change, each checked against a release.
    edits: list[dict] = []
    chapter_version: Optional[str] = None
    latest_version: Optional[str] = None
    gap_kind: Optional[str] = None
    releases_since: int = 0
    legacy_uses: list[str] = []
    runs_flagged: int = 1
    first_seen_run: Optional[str] = None
    version_moved: bool = False
