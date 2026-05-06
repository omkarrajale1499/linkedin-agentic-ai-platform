from .schemas import MatchRequest, MatchResult

SKILL_ALIASES = {
    'react.js': 'react',
    'reactjs': 'react',
    'react js': 'react',
    'node': 'node.js',
    'nodejs': 'node.js',
    'node js': 'node.js',
    'js': 'javascript',
    'ts': 'typescript',
    'rest apis': 'rest',
    'rest api': 'rest',
    'nlp': 'natural language processing',
    'ml': 'machine learning',
    'k8s': 'kubernetes',
    'postgres': 'postgresql',
    'postgres sql': 'postgresql',
    'scikit learn': 'machine learning',
    'sklearn': 'machine learning',
    'pyspark': 'spark',
    'amazon web services': 'aws',
    'google cloud platform': 'gcp',
    'power bi': 'tableau',
    'ci cd': 'ci/cd',
}


def _normalize_token(value: str) -> str:
    token = (value or '').strip().lower()
    token = token.replace('&', 'and').replace('/', ' ')
    token = ' '.join(token.split())
    return SKILL_ALIASES.get(token, token)


def _normalize_set(values: list[str]) -> set[str]:
    normalized = set()
    for value in values or []:
        raw = (value or '').strip()
        if not raw:
            continue
        candidates = [raw]
        # Split composite skills like "Python/SQL" or "Python, SQL"
        if any(sep in raw for sep in [',', '/', '|']):
            for sep in [',', '/', '|']:
                raw = raw.replace(sep, ',')
            candidates.extend([part.strip() for part in raw.split(',') if part.strip()])
        for candidate in candidates:
            token = _normalize_token(candidate)
            if token:
                normalized.add(token)
    return normalized


def _location_score(job_location: str | None, member_location: str | None) -> float:
    if not job_location or not member_location:
        return 0.0
    job_tokens = set(_normalize_token(job_location).replace(',', ' ').split())
    member_tokens = set(_normalize_token(member_location).replace(',', ' ').split())
    if not job_tokens or not member_tokens:
        return 0.0
    overlap = len(job_tokens & member_tokens)
    if overlap >= 2:
        return 0.2
    if overlap == 1:
        return 0.1
    return 0.0


def compute_match(req: MatchRequest) -> MatchResult:
    """Rule-based + skills overlap match score."""
    job_set = _normalize_set(req.job_skills)
    member_set = _normalize_set(req.resume_skills)
    overlap    = job_set & member_set

    # Skills score (0-0.6 weight)
    skills_score = len(overlap) / max(len(job_set), 1) * 0.6

    # Location score (0-0.2 weight)
    location_score = _location_score(req.job_location, req.member_location)

    # Experience score (0-0.2 weight)
    exp_score = 0.0
    if req.required_experience is not None and req.member_experience is not None:
        ratio = req.member_experience / max(req.required_experience, 0.5)
        exp_score = min(ratio, 1.0) * 0.2

    match_score = round(skills_score + location_score + exp_score, 3)
    overlap_display = sorted(list(overlap))[:5]
    exp_note = ''
    if req.required_experience is not None and req.member_experience is not None:
        if req.member_experience + 1e-6 < req.required_experience * 0.7:
            exp_note = ' (candidate may be junior for stated seniority).'
        elif req.member_experience > req.required_experience * 1.4:
            exp_note = ' (candidate may exceed typical tenure expectation).'

    explanation = (
        f"Skills: {len(overlap)}/{len(job_set)} job skills matched "
        f"({', '.join(overlap_display) if overlap_display else 'none surfaced'}); "
        f"location aligned: {'yes' if location_score > 0 else 'weak/no'}; "
        f"experience band: {req.member_experience or 'unknown'} yrs vs role hint "
        f"{req.required_experience or 'any'} yrs{exp_note}"
    )
    return MatchResult(
        member_id=req.member_id,
        job_id=req.job_id,
        match_score=match_score,
        skills_overlap=list(overlap),
        explanation=explanation,
    )
