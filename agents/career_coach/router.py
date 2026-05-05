import re
from io import BytesIO
from fastapi import APIRouter, HTTPException, Request, UploadFile, File, Form
from pydantic import ValidationError
from docx import Document
from pypdf import PdfReader
from .schemas import CareerCoachRequest, CareerCoachResponse
from shared.service_client import get_member, get_job
from config import CAREER_COACH_USE_LLM
from .coach_llm import run_career_coach_llm

router = APIRouter(prefix='/agents/career-coach', tags=['agents'])

KNOWN_SKILLS = [
    'python', 'javascript', 'typescript', 'java', 'go', 'rust', 'c++', 'react', 'node.js', 'node',
    'vue', 'angular', 'next.js', 'mysql', 'postgresql', 'mongodb', 'redis', 'elasticsearch', 'kafka',
    'docker', 'kubernetes', 'aws', 'gcp', 'azure', 'machine learning', 'tensorflow', 'pytorch',
    'spark', 'scala', 'graphql', 'rest', 'grpc', 'microservices', 'linux', 'git', 'terraform', 'sql',
]


def _normalize_skill(value: str) -> str:
    token = (value or '').strip().lower()
    aliases = {
        'node': 'node.js',
        'react.js': 'react',
        'js': 'javascript',
        'ts': 'typescript',
    }
    return aliases.get(token, token)


def _pretty_skill(value: str) -> str:
    return value.upper() if value in {'aws', 'gcp', 'sql'} else value.title().replace('Node.Js', 'Node.js')


def _extract_job_skills(job: dict) -> list[str]:
    explicit = [_normalize_skill(str(s)) for s in (job.get('skills') or []) if str(s).strip()]
    text = f"{job.get('title', '')} {job.get('description', '')}".lower()
    inferred = [_normalize_skill(s) for s in KNOWN_SKILLS if s in text]
    merged = []
    for skill in explicit + inferred:
        if skill and skill not in merged:
            merged.append(skill)
    return merged[:12]


def _extract_resume_skills(resume: str) -> list[str]:
    text = (resume or '').lower()
    found = []
    for skill in KNOWN_SKILLS:
        if skill in text:
            normalized = _normalize_skill(skill)
            if normalized not in found:
                found.append(normalized)
    return found[:20]


def _estimate_years_experience(resume: str) -> float | None:
    years = [int(x) for x in re.findall(r'(\d{1,2})\+?\s+years?', (resume or '').lower())]
    return float(max(years)) if years else None


def _extract_pdf_text(blob: bytes) -> str:
    reader = PdfReader(BytesIO(blob))
    text_chunks = []
    for page in reader.pages:
        extracted = page.extract_text() or ''
        if extracted.strip():
            text_chunks.append(extracted.strip())
    return '\n'.join(text_chunks).strip()


def _extract_docx_text(blob: bytes) -> str:
    doc = Document(BytesIO(blob))
    lines = [p.text.strip() for p in doc.paragraphs if p.text and p.text.strip()]
    return '\n'.join(lines).strip()


def _extract_doc_text(blob: bytes) -> str:
    # Legacy .doc parsing without external binaries: best-effort text recovery.
    decoded = blob.decode('latin-1', errors='ignore')
    cleaned = re.sub(r'[^ -~\n\r\t]', ' ', decoded)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned


async def _extract_resume_from_upload(upload: UploadFile) -> str:
    filename = (upload.filename or '').lower()
    blob = await upload.read()
    if not blob:
        raise HTTPException(status_code=400, detail='Uploaded resume file is empty.')

    if filename.endswith('.pdf'):
        text = _extract_pdf_text(blob)
    elif filename.endswith('.docx'):
        text = _extract_docx_text(blob)
    elif filename.endswith('.doc'):
        text = _extract_doc_text(blob)
    else:
        raise HTTPException(status_code=400, detail='Unsupported resume file type. Use PDF, DOC, or DOCX.')

    if not text or len(text.strip()) < 20:
        raise HTTPException(status_code=400, detail='Could not extract enough text from uploaded resume.')
    return text


def heuristic_career_coach(member: dict, job: dict, resume: str) -> CareerCoachResponse:
    job_title = job.get('title', 'Target Role')
    job_skills = _extract_job_skills(job)
    resume_skills = _extract_resume_skills(resume)
    missing_skills = [s for s in job_skills if s not in resume_skills][:5]
    matched_skills = [s for s in job_skills if s in resume_skills][:4]
    years = _estimate_years_experience(resume)

    headline_parts = [job_title]
    if matched_skills:
        headline_parts.append(', '.join(_pretty_skill(s) for s in matched_skills[:3]))
    if years is not None:
        headline_parts.append(f'{int(years)}+ yrs experience')
    else:
        headline_parts.append('Results-driven candidate')
    headline = ' | '.join(headline_parts)

    improvements = [
        'Quantify impact in each experience bullet with metrics such as latency reduced, users served, or revenue influenced.',
        f'Align your summary with the {job_title} role and explicitly mention the most important required skills.',
        'Move the most relevant projects and achievements higher in the resume so recruiters see them first.',
    ]
    if matched_skills:
        improvements.append(
            f'Emphasize your strongest overlaps early: {", ".join(_pretty_skill(s) for s in matched_skills[:3])}.'
        )
    if missing_skills:
        improvements.append(
            f'Add evidence for these missing skills if you truly have them: {", ".join(_pretty_skill(s) for s in missing_skills)}.'
        )

    cover_tips = [
        'Open with why this company and role fit your background instead of using a generic introduction.',
        'Use one short paragraph to connect your strongest project or experience to the job requirements.',
        'Close with a concrete value statement and interest in the next hiring step.',
    ]

    return CareerCoachResponse(
        headline_suggestion=headline,
        resume_improvements=improvements,
        skills_to_add=[_pretty_skill(s) for s in missing_skills],
        cover_letter_tips=cover_tips,
    )


@router.post('', response_model=CareerCoachResponse)
async def career_coach(
    request: Request,
    member_id: str | None = Form(default=None),
    job_id: str | None = Form(default=None),
    resume_text: str | None = Form(default=None),
    resume_file: UploadFile | None = File(default=None),
):
    req = None
    ctype = (request.headers.get('content-type') or '').lower()

    try:
        if 'application/json' in ctype:
            req = CareerCoachRequest(**(await request.json()))
        else:
            combined_resume = (resume_text or '').strip()
            if resume_file is not None:
                extracted = await _extract_resume_from_upload(resume_file)
                combined_resume = f"{combined_resume}\n\n{extracted}".strip() if combined_resume else extracted
            req = CareerCoachRequest(
                member_id=member_id or '',
                job_id=job_id or '',
                resume_text=combined_resume or None,
            )
    except ValidationError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    try:
        member, job = await get_member(req.member_id), await get_job(req.job_id)
        resume = req.resume_text or member.get('resume_text', '') or member.get('about', '')
        job_skills = _extract_job_skills(job)
        resume_skills = _extract_resume_skills(resume)
        heuristic = heuristic_career_coach(member, job, resume)

        if CAREER_COACH_USE_LLM:
            return await run_career_coach_llm(
                member, job, resume, heuristic, job_skills, resume_skills
            )
        return heuristic
    except Exception as exc:
        try:
            member, job = await get_member(req.member_id), await get_job(req.job_id)
            resume = req.resume_text or member.get('resume_text', '') or member.get('about', '')
            return heuristic_career_coach(member, job, resume)
        except Exception:
            raise HTTPException(status_code=500, detail=str(exc))
