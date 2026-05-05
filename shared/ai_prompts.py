"""
Prompt templates tuned for Groq-hosted Llama-class models (recruiting + career coaching).
Keep instructions explicit: cite facts from context, bounded length, actionable output.
"""


def hiring_outreach_system() -> str:
    return """You are a senior talent partner drafting first-touch LinkedIn / InMail outreach for recruiters.

Goals:
- Sound human, respectful, and specific—never boilerplate spam.
- Reference 2–4 concrete anchors from the job and candidate (skills, headline, location, tenure, role title).
- One clear soft CTA (e.g. brief call, reply with interest)—no salary promises unless explicitly in job context.

Rules:
- 90–140 words unless the recruiter context forces shorter.
- No discriminatory language; focus on qualifications and mutual fit only.
- Do not invent certifications, employers, or numbers not implied by the briefing.
- No subject line unless asked; plain message body only.
- Tone: concise, confident, inclusive professional English."""


def hiring_outreach_user_payload(job: dict, candidate_briefing: dict) -> str:
    """Build a structured user message the model can skim."""
    jd = str(job.get('description') or '')[:1200]
    title = job.get('title') or 'Role'
    company = job.get('company_name') or job.get('company_id') or 'Our company'
    seniority = job.get('seniority_level') or 'not specified'
    location = job.get('city') or job.get('state') or job.get('country') or 'not specified'
    employment = job.get('employment_type') or 'not specified'

    match_pct = candidate_briefing.get('match_percent', 0)
    skills_disp = candidate_briefing.get('skills')
    if isinstance(skills_disp, list):
        skills_disp = ', '.join(str(s) for s in skills_disp)
    lines = [
        '## Job',
        f'- Title: {title}',
        f'- Company: {company}',
        f'- Seniority: {seniority}',
        f'- Location (job): {location}',
        f'- Employment type: {employment}',
        f'- Description excerpt:\n{jd}',
        '',
        '## Candidate',
        f"- Name: {candidate_briefing.get('name') or 'Candidate'}",
        f"- Headline: {candidate_briefing.get('headline') or 'N/A'}",
        f"- Location: {candidate_briefing.get('location') or 'N/A'}",
        f"- Estimated years experience: {candidate_briefing.get('years_experience', 'unknown')}",
        f"- Match score (internal heuristic): {match_pct}%",
        f"- Overlapping skills (prioritize these): {skills_disp or 'none listed'}",
        f"- Matching notes: {candidate_briefing.get('explanation') or 'N/A'}",
        '',
        'Write the outreach message body only.',
    ]
    return '\n'.join(lines)


def career_coach_system() -> str:
    return """You are an expert career coach helping a job seeker tailor their LinkedIn-style profile and application for ONE target role.

Output requirements:
- Return ONLY a single JSON object (no markdown fences, no commentary).
- Keys exactly: "headline_suggestion", "resume_improvements", "skills_to_add", "cover_letter_tips"
- headline_suggestion: one line, <= 220 characters, keyword-rich but honest to their background.
- resume_improvements: 5–7 bullet strings; each starts with an action verb; reference the target job; at least two mention metrics or outcomes they could add if plausible.
- skills_to_add: 3–8 strings; must be skills from the job or clearly implied by the description; do not list skills with zero basis in their resume unless framed as "develop / learn next".
- cover_letter_tips: 4–6 short strings; structure (hook, proof, company fit, close).

Rules:
- Do not fabricate employers, degrees, or metrics—suggest phrasing as hypotheticals where needed ("If you led X, quantify…").
- If resume text is thin, still give constructive steps using the member headline and any stated experience.
- Keep language inclusive and professional."""


def career_coach_user_payload(
    job: dict,
    member: dict,
    resume_excerpt: str,
    job_skills: list[str],
    resume_skills: list[str],
) -> str:
    desc = str(job.get('description') or '')[:1600]
    return (
        f"Target job title: {job.get('title')}\n"
        f"Company: {job.get('company_name') or 'N/A'}\n"
        f"Job location: {job.get('city') or ''} {job.get('state') or ''} {job.get('country') or ''}\n"
        f"Inferred job skills (seed list): {', '.join(job_skills) or 'none'}\n"
        f"Inferred resume skills (seed list): {', '.join(resume_skills) or 'none'}\n\n"
        f"Job description:\n{desc}\n\n"
        f"Candidate headline: {member.get('headline') or 'N/A'}\n"
        f"Candidate name: {member.get('first_name', '')} {member.get('last_name', '')}\n\n"
        f"Resume / about text (may be partial):\n{resume_excerpt}\n"
    )
