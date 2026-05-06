import json
import re
from pydantic import ValidationError

from .schemas import CareerCoachResponse
from shared.llm_client import chat_complete, has_llm
from shared.ai_prompts import career_coach_system, career_coach_user_payload


def _coerce_string_list(val, max_items: int) -> list[str]:
    if not isinstance(val, list):
        return []
    out: list[str] = []
    for x in val:
        s = str(x).strip()
        if s and s not in out:
            out.append(s)
        if len(out) >= max_items:
            break
    return out


def _extract_json_obj(text: str) -> dict | None:
    if not text or not text.strip():
        return None
    try:
        return json.loads(text)
    except Exception:
        pass
    cleaned = text.strip()
    if cleaned.startswith('```'):
        cleaned = re.sub(r'^```(?:json)?\s*', '', cleaned, flags=re.IGNORECASE)
        cleaned = re.sub(r'\s*```$', '', cleaned).strip()
    try:
        return json.loads(cleaned)
    except Exception:
        pass
    match = re.search(r'\{[\s\S]*\}', cleaned)
    if not match:
        return None
    try:
        return json.loads(match.group())
    except Exception:
        return None


def merge_with_heuristic(heuristic: CareerCoachResponse, raw: dict | None) -> CareerCoachResponse:
    """Prefer LLM fields; pad with heuristic when thin or invalid."""
    if not raw:
        return heuristic

    headline = str(raw.get('headline_suggestion') or '').strip()
    if len(headline) > 240:
        headline = headline[:237] + '...'
    if not headline:
        headline = heuristic.headline_suggestion

    improvements = _coerce_string_list(raw.get('resume_improvements'), 10)
    if len(improvements) < 4:
        merged = improvements + [x for x in heuristic.resume_improvements if x not in improvements]
        improvements = merged[:8]

    skills = _coerce_string_list(raw.get('skills_to_add'), 12)
    if len(skills) < 3:
        merged = skills + [x for x in heuristic.skills_to_add if x not in skills]
        skills = merged[:10]

    cover = _coerce_string_list(raw.get('cover_letter_tips'), 10)
    if len(cover) < 4:
        merged = cover + [x for x in heuristic.cover_letter_tips if x not in cover]
        cover = merged[:8]

    try:
        return CareerCoachResponse(
            headline_suggestion=headline,
            resume_improvements=improvements,
            skills_to_add=skills,
            cover_letter_tips=cover,
        )
    except ValidationError:
        return heuristic


async def run_career_coach_llm(
    member: dict,
    job: dict,
    resume_text: str,
    heuristic: CareerCoachResponse,
    job_skills: list[str],
    resume_skills: list[str],
) -> CareerCoachResponse:
    if not has_llm():
        return heuristic

    excerpt = (resume_text or '')[:4500]
    user_content = career_coach_user_payload(job, member, excerpt, job_skills, resume_skills)
    messages = [
        {'role': 'system', 'content': career_coach_system()},
        {'role': 'user', 'content': user_content},
    ]

    content = ''
    try:
        content = await chat_complete(
            messages,
            temperature=0.32,
            max_tokens=1536,
            response_format_json=True,
        )
    except Exception:
        try:
            content = await chat_complete(
                messages,
                temperature=0.32,
                max_tokens=1536,
                response_format_json=False,
            )
        except Exception:
            return heuristic

    data = _extract_json_obj(content)
    return merge_with_heuristic(heuristic, data)
