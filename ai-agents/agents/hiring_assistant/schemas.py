from pydantic import BaseModel
from typing import Optional, Any
from enum import Enum

class TaskStatus(str, Enum):
    pending = 'pending'
    running = 'running'
    awaiting_approval = 'awaiting_approval'
    approved = 'approved'
    rejected = 'rejected'
    completed = 'completed'
    failed = 'failed'
    cancelled = 'cancelled'

class HiringRequest(BaseModel):
    job_id: str
    recruiter_id: str
    top_k: int = 5

class ShortlistedCandidate(BaseModel):
    member_id: str
    match_score: float
    skills_overlap: list[str]
    explanation: str
    candidate_name: Optional[str] = None
    candidate_headline: Optional[str] = None
    candidate_location: Optional[str] = None
    years_experience: Optional[float] = None
    outreach_draft: Optional[str] = None

class HiringTaskStatus(BaseModel):
    trace_id: str
    status: TaskStatus
    job_id: str
    recruiter_id: str
    shortlist: list[ShortlistedCandidate] = []
    step: str = ''
    error: Optional[str] = None
    approval_action: Optional[str] = None
    history: list[dict[str, Any]] = []

class ApprovalRequest(BaseModel):
    trace_id: str
    action: str  # approve | edit | reject
    edited_outreach: Optional[str] = None


class MatchingQualityMetrics(BaseModel):
    tasks_with_shortlist: int
    avg_shortlist_size: float
    avg_topk_skills_overlap_ratio: float
    avg_top1_match_score: float


class ApprovalRateMetrics(BaseModel):
    tasks_awaiting_approval: int
    approved_as_is: int
    edited: int
    rejected: int
    approved_as_is_rate: float
    edited_rate: float
    rejected_rate: float


class EvaluationSummaryResponse(BaseModel):
    total_tasks_considered: int
    matching_quality: MatchingQualityMetrics
    human_in_loop_effectiveness: ApprovalRateMetrics
