import aiomysql
import pymysql.err
from fastapi import APIRouter, Header, HTTPException

from app.common import jsonable_row, make_event_idempotency_key, trace_id, uuid4_str
from app.deps import MysqlPoolDep
from app.kafka_bus import publish_event


def page_limit(body: dict):
    page = max(int(body.get("page") or 1), 1)
    limit = min(max(int(body.get("limit") or 20), 1), 100)
    offset = (page - 1) * limit
    return page, limit, offset


def build_location(member: dict) -> str:
    parts = [member.get("city"), member.get("state"), member.get("country")]
    return ", ".join(p for p in parts if p)


router = APIRouter(prefix="/applications", tags=["applications"])


@router.post("/submit")
async def submit_application(
    body: dict,
    pool: MysqlPoolDep,
    x_trace_id: str | None = Header(None, alias="x-trace-id"),
    x_idempotency_key: str | None = Header(None, alias="x-idempotency-key"),
):
    job_id = body.get("job_id")
    member_id = body.get("member_id")
    if not job_id or not member_id:
        raise HTTPException(status_code=400, detail="job_id and member_id required")

    aid = uuid4_str()
    ikey = body.get("idempotency_key") or uuid4_str()
    jr = None
    mr = None

    async with pool.acquire() as conn:
        await conn.begin()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT job_id, recruiter_id, status FROM jobs WHERE job_id=%s",
                    [job_id],
                )
                job_rows = await cur.fetchall()
                await cur.execute(
                    "SELECT member_id, city, state, country FROM members WHERE member_id=%s AND is_deleted=0",
                    [member_id],
                )
                member_rows = await cur.fetchall()
                if not job_rows:
                    await conn.rollback()
                    raise HTTPException(status_code=404, detail="Job not found")
                if not member_rows:
                    await conn.rollback()
                    raise HTTPException(status_code=404, detail="Member not found")
                if job_rows[0]["status"] != "open":
                    await conn.rollback()
                    raise HTTPException(status_code=409, detail="Cannot apply to a closed job")
                jr = job_rows[0]
                mr = member_rows[0]
                await cur.execute(
                    """INSERT INTO applications
               (application_id, job_id, member_id, resume_url, resume_text, cover_letter, answers, idempotency_key)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s)""",
                    [
                        aid,
                        job_id,
                        member_id,
                        body.get("resume_url"),
                        body.get("resume_text"),
                        body.get("cover_letter"),
                        body.get("answers"),
                        ikey,
                    ],
                )
                await cur.execute(
                    "UPDATE jobs SET applicants_count = applicants_count + 1 WHERE job_id=%s",
                    [job_id],
                )
            await conn.commit()
        except pymysql.err.IntegrityError as e:
            await conn.rollback()
            if e.args[0] == 1062:
                raise HTTPException(status_code=409, detail="Already applied to this job")
            raise

    assert jr is not None and mr is not None

    tid = trace_id(body, x_trace_id)
    publish_event(
        topic="application.submitted",
        event_type="application.submitted",
        actor_id=str(member_id),
        entity_type="application",
        entity_id=aid,
        payload={
            "application_id": aid,
            "job_id": job_id,
            "member_id": member_id,
            "recruiter_id": jr["recruiter_id"],
            "location": build_location(mr),
            "city": mr.get("city"),
            "state": mr.get("state"),
            "country": mr.get("country"),
            "status": "submitted",
        },
        trace_id=tid,
        idempotency_key=make_event_idempotency_key(body, x_idempotency_key, "application.submitted", aid),
    )

    return {"application_id": aid}


@router.post("/get")
async def get_application(body: dict, pool: MysqlPoolDep):
    aid = body.get("application_id")
    if not aid:
        raise HTTPException(status_code=400, detail="application_id required")
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM applications WHERE application_id=%s", [aid])
            rows = await cur.fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="Application not found")
    row = rows[0]
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM application_notes WHERE application_id=%s ORDER BY created_at DESC",
                [aid],
            )
            notes = await cur.fetchall()
            await cur.execute(
                "SELECT * FROM application_status_history WHERE application_id=%s ORDER BY changed_at DESC",
                [aid],
            )
            history = await cur.fetchall()

    out = dict(row)
    out["notes"] = jsonable_row(notes)
    out["history"] = jsonable_row(history)
    return jsonable_row(out)


@router.post("/byJob")
async def by_job(body: dict, pool: MysqlPoolDep):
    jid = body.get("job_id")
    if not jid:
        raise HTTPException(status_code=400, detail="job_id required")
    recruiter_id = body.get("recruiter_id")
    page, limit, offset = page_limit(body)

    if recruiter_id:
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "SELECT recruiter_id FROM jobs WHERE job_id=%s",
                    [jid],
                )
                jr = await cur.fetchone()
        if not jr:
            raise HTTPException(status_code=404, detail="Job not found")
        if jr["recruiter_id"] != recruiter_id:
            raise HTTPException(status_code=403, detail="Only the owning recruiter can view applications for this job")

    q = f"""SELECT a.*, m.first_name, m.last_name, m.headline, m.city, m.state, m.country
       FROM applications a
       LEFT JOIN members m ON m.member_id = a.member_id
       WHERE a.job_id=%s ORDER BY a.applied_at DESC LIMIT {limit} OFFSET {offset}"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(q, [jid])
            rows = await cur.fetchall()

    return {"results": jsonable_row(rows), "page": page, "limit": limit}


@router.post("/byMember")
async def by_member(body: dict, pool: MysqlPoolDep):
    mid = body.get("member_id")
    if not mid:
        raise HTTPException(status_code=400, detail="member_id required")
    page, limit, offset = page_limit(body)
    q = f"""SELECT a.*, j.title, j.city, j.state, j.country, j.work_mode, j.employment_type, j.seniority_level,
       r.company_name
       FROM applications a
       LEFT JOIN jobs j ON j.job_id = a.job_id
       LEFT JOIN recruiters r ON r.recruiter_id = j.recruiter_id
       WHERE a.member_id=%s ORDER BY a.applied_at DESC LIMIT {limit} OFFSET {offset}"""

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(q, [mid])
            rows = await cur.fetchall()

    return {"results": jsonable_row(rows), "page": page, "limit": limit}


@router.post("/updateStatus")
async def update_status(
    body: dict,
    pool: MysqlPoolDep,
    x_trace_id: str | None = Header(None, alias="x-trace-id"),
    x_idempotency_key: str | None = Header(None, alias="x-idempotency-key"),
):
    aid = body.get("application_id")
    status = body.get("status")
    recruiter_id = body.get("recruiter_id")
    valid = {"submitted", "reviewing", "interview", "offer", "rejected"}

    if not aid or status not in valid:
        raise HTTPException(status_code=400, detail="application_id and valid status required")

    old_status: str | None = None
    current_row: dict | None = None

    async with pool.acquire() as conn:
        await conn.begin()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """SELECT a.application_id, a.status, a.member_id, a.job_id, j.recruiter_id
                   FROM applications a JOIN jobs j ON j.job_id = a.job_id
                   WHERE a.application_id=%s""",
                    [aid],
                )
                fetched = await cur.fetchall()
                if not fetched:
                    await conn.rollback()
                    raise HTTPException(status_code=404, detail="Application not found")
                current_row = fetched[0]
                if recruiter_id and current_row["recruiter_id"] != recruiter_id:
                    await conn.rollback()
                    raise HTTPException(status_code=403, detail="Only the owning recruiter can update this application")

                old_status = current_row["status"]
                await cur.execute(
                    "UPDATE applications SET status=%s WHERE application_id=%s",
                    [status, aid],
                )
                await cur.execute(
                    """INSERT INTO application_status_history
                   (application_id, old_status, new_status, changed_by)
                   VALUES (%s,%s,%s,%s)""",
                    [aid, old_status, status, recruiter_id or current_row["recruiter_id"]],
                )
            await conn.commit()
        except HTTPException:
            await conn.rollback()
            raise
        except Exception:
            await conn.rollback()
            raise

    assert old_status is not None and current_row is not None

    tid = trace_id(body, x_trace_id)
    publish_event(
        topic="application.status.changed",
        event_type="application.status.changed",
        actor_id=str(recruiter_id or current_row["recruiter_id"]),
        entity_type="application",
        entity_id=aid,
        payload={
            "application_id": aid,
            "job_id": current_row["job_id"],
            "member_id": current_row["member_id"],
            "recruiter_id": current_row["recruiter_id"],
            "old_status": old_status,
            "new_status": status,
        },
        trace_id=tid,
        idempotency_key=make_event_idempotency_key(body, x_idempotency_key, "application.status.changed", aid),
    )

    return {"success": True, "old_status": old_status, "new_status": status}


@router.post("/addNote", status_code=201)
async def add_note(body: dict, pool: MysqlPoolDep):
    aid = body.get("application_id")
    note = body.get("note")
    recruiter_id = body.get("recruiter_id")
    if not aid or not note:
        raise HTTPException(status_code=400, detail="application_id and note required")

    if recruiter_id:
        async with pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """SELECT j.recruiter_id FROM applications a JOIN jobs j ON j.job_id = a.job_id
                   WHERE a.application_id=%s""",
                    [aid],
                )
                rrows = await cur.fetchall()
        if not rrows:
            raise HTTPException(status_code=404, detail="Application not found")
        if rrows[0]["recruiter_id"] != recruiter_id:
            raise HTTPException(status_code=403, detail="Only the owning recruiter can add a note")

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "INSERT INTO application_notes (application_id, recruiter_id, note) VALUES (%s,%s,%s)",
                [aid, recruiter_id or None, note],
            )

    return {"success": True}
