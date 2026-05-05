import asyncio
import hashlib
import re
from typing import Optional
from shared.service_client import get_job, get_applications_by_job, get_member, search_members_by_keyword
from shared.llm_client import chat_complete, has_llm
from shared.ai_prompts import hiring_outreach_system, hiring_outreach_user_payload
from shared.kafka_client import publish_event
from shared.trace_store import upsert_trace, append_history, get_trace, list_traces
from skills.resume_parser.skill import parse_resume
from skills.job_candidate_matcher.skill import compute_match
from skills.job_candidate_matcher.schemas import MatchRequest
from .schemas import (
    HiringTaskStatus,
    ShortlistedCandidate,
    TaskStatus,
    MatchingQualityMetrics,
    ApprovalRateMetrics,
    EvaluationSummaryResponse,
)

_tasks: dict[str, HiringTaskStatus] = {}
def _job_skill_denom_from_explanation(explanation: str) -> int:
    """Parse X/Y skills count from matcher explanation (legacy or current wording)."""
    if not explanation:
        return 0
    for pattern in (
        r'Skills\s*overlap:\s*\d+\s*/\s*(\d+)',
        r'Skills:\s*\d+\s*/\s*(\d+)',
    ):
        m = re.search(pattern, explanation, re.IGNORECASE)
        if m:
            try:
                return int(m.group(1))
            except ValueError:
                return 0
    return 0


KNOWN_JOB_SKILLS = {
    'python', 'javascript', 'typescript', 'java', 'go', 'rust', 'c++',
    'react', 'react.js', 'node', 'node.js', 'vue', 'angular', 'next.js',
    'mysql', 'postgresql', 'mongodb', 'redis', 'elasticsearch', 'kafka', 'rabbitmq',
    'docker', 'kubernetes', 'aws', 'gcp', 'azure',
    'machine learning', 'tensorflow', 'pytorch', 'spark', 'scala',
    'graphql', 'rest', 'grpc', 'microservices', 'linux', 'git', 'terraform', 'sql',
}


def _task_payload(task: HiringTaskStatus) -> dict:
    return {
        'trace_id': task.trace_id,
        'job_id': task.job_id,
        'recruiter_id': task.recruiter_id,
        'status': task.status.value if hasattr(task.status, 'value') else str(task.status),
        'step': task.step,
        'error': task.error,
        'approval_action': task.approval_action,
        'shortlist': [candidate.model_dump() for candidate in task.shortlist],
        'history': task.history,
    }


async def persist_task(task: HiringTaskStatus, history_details: Optional[dict] = None) -> HiringTaskStatus:
    _tasks[task.trace_id] = task
    await upsert_trace(task.trace_id, _task_payload(task))
    await append_history(
        task.trace_id,
        task.status.value if hasattr(task.status, 'value') else str(task.status),
        task.step,
        history_details,
    )
    stored = await get_task_async(task.trace_id)
    return stored or task


async def initialize_task(trace_id: str, job_id: str, recruiter_id: str, status: TaskStatus, step: str) -> HiringTaskStatus:
    task = HiringTaskStatus(
        trace_id=trace_id,
        status=status,
        job_id=job_id,
        recruiter_id=recruiter_id,
        step=step,
    )
    return await persist_task(task, {'initialized': True})


async def get_task_async(trace_id: str) -> Optional[HiringTaskStatus]:
    if trace_id in _tasks:
        return _tasks[trace_id]
    doc = await get_trace(trace_id)
    if not doc:
        return None
    doc['status'] = TaskStatus(doc.get('status', TaskStatus.pending))
    shortlist = doc.get('shortlist', [])
    doc['shortlist'] = [ShortlistedCandidate(**item) for item in shortlist]
    task = HiringTaskStatus(**doc)
    _tasks[trace_id] = task
    return task


async def _publish_result(task: HiringTaskStatus, extra_payload: Optional[dict] = None) -> None:
    payload = {
        'job_id': task.job_id,
        'recruiter_id': task.recruiter_id,
        'status': task.status.value if hasattr(task.status, 'value') else str(task.status),
        'step': task.step,
        'approval_action': task.approval_action,
        'shortlist_count': len(task.shortlist),
        'shortlist': [candidate.model_dump() for candidate in task.shortlist],
    }
    if extra_payload:
        payload.update(extra_payload)
    publish_event('ai.results', 'ai.results', task.recruiter_id, 'ai_task', task.trace_id, payload, task.trace_id)


async def _is_cancelled(trace_id: str) -> bool:
    task = await get_task_async(trace_id)
    return bool(task and task.status == TaskStatus.cancelled)


def _compose_location(data: dict) -> str:
    return ', '.join([data.get('city', ''), data.get('state', ''), data.get('country', '')]).strip(', ')


def _extract_job_skills(job: dict) -> list[str]:
    base_skills = [str(s).strip() for s in (job.get('skills') or []) if str(s).strip()]
    if len(base_skills) >= 3:
        return base_skills
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    inferred = []
    for skill in KNOWN_JOB_SKILLS:
        if skill in text:
            pretty = skill.upper() if skill in {'aws', 'gcp', 'sql'} else skill.title().replace('Node.Js', 'Node.js').replace('React.Js', 'React')
            inferred.append(pretty)
    merged = []
    for skill in base_skills + inferred:
        if skill not in merged:
            merged.append(skill)
    return merged[:12]


def _required_experience_from_seniority(job: dict) -> float | None:
    seniority = str(job.get('seniority_level') or '').lower()
    if 'intern' in seniority:
        return 0.0
    if 'entry' in seniority:
        return 1.0
    if 'associate' in seniority:
        return 2.0
    if 'mid' in seniority or 'senior' in seniority:
        return 4.0
    if 'director' in seniority:
        return 8.0
    if 'executive' in seniority:
        return 10.0
    return None


def _heuristic_outreach(job: dict, candidate: ShortlistedCandidate) -> str:
    job_title = job.get('title', 'this role')
    candidate_name = candidate.candidate_name or 'there'
    overlap = ', '.join(candidate.skills_overlap[:3]) if candidate.skills_overlap else ''
    location_text = candidate.candidate_location or ''
    profile_anchor = candidate.candidate_headline or 'background'
    years = candidate.years_experience
    if years is None:
        years_phrase = "Your profile trajectory aligns with this role."
    elif years <= 0.5:
        years_phrase = "This internship-friendly role is a strong fit for early-career candidates."
    else:
        years_phrase = f"Given your {years:.1f} years of experience, I thought this could be a good match."

    seed_value = int(hashlib.md5(candidate.member_id.encode()).hexdigest(), 16)
    openers = [
        f"Hi {candidate_name}, I’m recruiting for a {job_title} role.",
        f"Hi {candidate_name}, I came across your profile for a {job_title} opening.",
        f"Hi {candidate_name}, I’m hiring for {job_title} and your profile looked relevant.",
    ]
    middle_parts = [
        f"Your work in {overlap} looks like a strong fit." if overlap else f"Your {profile_anchor} aligns well with what we need.",
        years_phrase,
        f"We’re speaking with candidates from {location_text} and similar markets." if location_text else "We’re moving quickly and prioritizing practical experience.",
    ]
    closers = [
        "Would you be open to a short 15-minute chat this week?",
        "If you're interested, I can share the role details and next steps.",
        "Would you like me to send over a brief overview and compensation range?",
    ]
    opener = openers[seed_value % len(openers)]
    parts = [
        middle_parts[(seed_value // 3) % len(middle_parts)],
        middle_parts[(seed_value // 7) % len(middle_parts)],
    ]
    close = closers[(seed_value // 11) % len(closers)]
    return f"{opener} {parts[0]} {parts[1]} {close}"


def _normalize_outreach_text(text: str) -> str:
    """Strip wrappers / noise from model output."""
    body = (text or '').strip()
    for prefix in ('Subject:', 'SUBJECT:', '**Subject**'):
        if body.lower().startswith(prefix.lower()):
            first_nl = body.find('\n')
            body = body[first_nl + 1 :] if first_nl != -1 else ''
            body = body.strip()
    if body.startswith('```'):
        lines = body.split('\n')
        if lines[-1].strip() == '```':
            lines = lines[1:-1]
        body = '\n'.join(lines).strip()
    if len(body) > 2800:
        body = body[:2800].rsplit('\n', 1)[0] + '…'
    return body


async def _generate_outreach(job: dict, candidate: ShortlistedCandidate) -> str:
    if not has_llm():
        return _heuristic_outreach(job, candidate)

    briefing = {
        'name': candidate.candidate_name,
        'headline': candidate.candidate_headline,
        'location': candidate.candidate_location,
        'years_experience': candidate.years_experience
        if candidate.years_experience is not None
        else 'unknown',
        'match_percent': round((candidate.match_score or 0) * 100),
        'skills': candidate.skills_overlap,
        'explanation': candidate.explanation,
    }

    try:
        raw = await chat_complete(
            [
                {'role': 'system', 'content': hiring_outreach_system()},
                {'role': 'user', 'content': hiring_outreach_user_payload(job, briefing)},
            ],
            temperature=0.28,
            max_tokens=512,
        )
        cleaned = _normalize_outreach_text(raw)
        return cleaned if cleaned else _heuristic_outreach(job, candidate)
    except Exception:
        return _heuristic_outreach(job, candidate)


async def run_hiring_workflow(job_id: str, recruiter_id: str, top_k: int, trace_id: str, source: str = 'kafka'):
    task = await get_task_async(trace_id)
    if not task:
        task = await initialize_task(trace_id, job_id, recruiter_id, TaskStatus.pending, 'Queued for processing')

    task.status = TaskStatus.running
    task.step = 'Fetching job details'
    await persist_task(task, {'source': source})

    try:
        if await _is_cancelled(trace_id):
            return await get_task_async(trace_id)

        job = await get_job(job_id)
        job_skills = _extract_job_skills(job)
        job_location = _compose_location(job)
        required_experience = _required_experience_from_seniority(job)

        task.step = 'Fetching applications'
        await persist_task(task)
        applications = await get_applications_by_job(job_id, limit=100)

        if await _is_cancelled(trace_id):
            return await get_task_async(trace_id)

        if not applications:
            task.step = 'No applicants yet — searching member pool by skills'
            await persist_task(task)
            keyword = ' '.join(job_skills[:3]) if job_skills else (job.get('title') or '')
            members = await search_members_by_keyword(keyword, limit=100)
            applications = [
                {'member_id': m['member_id'], 'resume_text': m.get('about', ''), 'cover_letter': ''}
                for m in members if m.get('member_id')
            ]
            if not applications:
                task.status = TaskStatus.completed
                task.step = 'No matching candidates found'
                task.shortlist = []
                await persist_task(task, {'applications_found': 0})
                await _publish_result(task, {'applications_found': 0})
                return task

        task.step = 'Scoring candidates'
        await persist_task(task, {'applications_found': len(applications)})
        concurrency_limit = asyncio.Semaphore(10)

        async def process_application(app: dict):
            async with concurrency_limit:
                member_id = app.get('member_id')
                if not member_id:
                    return None
                try:
                    member = await get_member(member_id)
                    resume_text = app.get('resume_text') or member.get('resume_text', '') or member.get('about', '')
                    if not resume_text:
                        return None
                    parsed = await parse_resume(resume_text)
                    match = compute_match(MatchRequest(
                        job_id=job_id,
                        member_id=member_id,
                        job_skills=job_skills,
                        resume_skills=parsed.skills,
                        job_location=job_location or None,
                        member_location=_compose_location(member) or None,
                        required_experience=required_experience,
                        member_experience=parsed.years_experience,
                    ))
                    candidate_name = f"{member.get('first_name', '')} {member.get('last_name', '')}".strip() or None
                    return ShortlistedCandidate(
                        member_id=member_id,
                        match_score=match.match_score,
                        skills_overlap=match.skills_overlap,
                        explanation=match.explanation,
                        candidate_name=candidate_name,
                        candidate_headline=member.get('headline') or None,
                        candidate_location=_compose_location(member) or None,
                        years_experience=parsed.years_experience,
                    )
                except Exception as exc:
                    print(f'Error processing {member_id}: {exc}')
                    return None

        results = await asyncio.gather(*[process_application(app) for app in applications])
        ranked = sorted([item for item in results if item], key=lambda x: x.match_score, reverse=True)
        strong = [c for c in ranked if len(c.skills_overlap) >= 1 or c.match_score >= 0.30]
        fallback = [c for c in ranked if c not in strong]
        scored = (strong + fallback)[:top_k]

        if await _is_cancelled(trace_id):
            return await get_task_async(trace_id)

        task.step = 'Generating outreach drafts'
        await persist_task(task, {'scored_candidates': len(scored)})
        outreach_limit = asyncio.Semaphore(3)

        async def generate_outreach(candidate: ShortlistedCandidate) -> None:
            async with outreach_limit:
                candidate.outreach_draft = await _generate_outreach(job, candidate)

        await asyncio.gather(*[generate_outreach(candidate) for candidate in scored])

        task.shortlist = scored
        task.status = TaskStatus.awaiting_approval
        task.step = 'Awaiting recruiter approval'
        await persist_task(task, {'shortlist_count': len(scored)})
        await _publish_result(task, {'source': source})
        return task

    except Exception as exc:
        task.status = TaskStatus.failed
        task.error = str(exc)
        task.step = 'Workflow failed'
        await persist_task(task, {'error': str(exc)})
        try:
            await _publish_result(task, {'error': str(exc), 'source': source})
        except Exception:
            pass
        print(f'Hiring workflow error [{trace_id}]: {exc}')
        return task


async def handle_approval(trace_id: str, action: str, edited_outreach: Optional[str] = None):
    task = await get_task_async(trace_id)
    if not task:
        return None

    normalized = (action or '').strip().lower()
    if normalized not in {'approve', 'edit', 'reject'}:
        raise ValueError('action must be approve, edit, or reject')

    task.approval_action = normalized
    if normalized == 'reject':
        task.status = TaskStatus.rejected
        task.step = 'Recruiter rejected AI output'
    else:
        if normalized == 'edit' and edited_outreach and task.shortlist:
            task.shortlist[0].outreach_draft = edited_outreach
        task.status = TaskStatus.approved
        task.step = 'Recruiter approved AI output'

    await persist_task(task, {'approval_action': normalized})
    await _publish_result(task, {'approval_action': normalized})
    return task


async def cancel_task_async(trace_id: str):
    task = await get_task_async(trace_id)
    if not task:
        return None

    if task.status in {TaskStatus.completed, TaskStatus.approved, TaskStatus.rejected, TaskStatus.failed}:
        return task

    task.status = TaskStatus.cancelled
    task.step = 'Cancelled by recruiter'
    await persist_task(task, {'approval_action': 'cancel'})
    await _publish_result(task, {'approval_action': 'cancel'})
    return task


async def get_evaluation_summary(limit: int = 200) -> EvaluationSummaryResponse:
    traces = await list_traces(limit=limit)
    considered = [trace for trace in traces if trace.get('job_id') and trace.get('recruiter_id')]

    shortlist_tasks = 0
    shortlist_sizes: list[int] = []
    overlap_ratios: list[float] = []
    top1_scores: list[float] = []

    awaiting_approval = 0
    approved_as_is = 0
    edited = 0
    rejected = 0

    for trace in considered:
        shortlist = trace.get('shortlist') or []
        if shortlist:
            shortlist_tasks += 1
            shortlist_sizes.append(len(shortlist))

            for candidate in shortlist:
                overlap = candidate.get('skills_overlap') or []
                explanation = str(candidate.get('explanation') or '')
                denom = _job_skill_denom_from_explanation(explanation)
                if denom > 0:
                    overlap_ratios.append(min(len(overlap) / denom, 1.0))

            first = shortlist[0]
            try:
                top1_scores.append(float(first.get('match_score') or 0.0))
            except Exception:
                pass

        history = trace.get('history') or []
        reached_approval = any(str(h.get('status')) == TaskStatus.awaiting_approval.value for h in history)
        if reached_approval:
            awaiting_approval += 1
            action = (trace.get('approval_action') or '').strip().lower()
            if action == 'approve':
                approved_as_is += 1
            elif action == 'edit':
                edited += 1
            elif action == 'reject':
                rejected += 1

    def _avg(values: list[float]) -> float:
        return round(sum(values) / len(values), 4) if values else 0.0

    def _rate(part: int, whole: int) -> float:
        return round(part / whole, 4) if whole else 0.0

    return EvaluationSummaryResponse(
        total_tasks_considered=len(considered),
        matching_quality=MatchingQualityMetrics(
            tasks_with_shortlist=shortlist_tasks,
            avg_shortlist_size=_avg([float(v) for v in shortlist_sizes]),
            avg_topk_skills_overlap_ratio=_avg(overlap_ratios),
            avg_top1_match_score=_avg(top1_scores),
        ),
        human_in_loop_effectiveness=ApprovalRateMetrics(
            tasks_awaiting_approval=awaiting_approval,
            approved_as_is=approved_as_is,
            edited=edited,
            rejected=rejected,
            approved_as_is_rate=_rate(approved_as_is, awaiting_approval),
            edited_rate=_rate(edited, awaiting_approval),
            rejected_rate=_rate(rejected, awaiting_approval),
        ),
    )
