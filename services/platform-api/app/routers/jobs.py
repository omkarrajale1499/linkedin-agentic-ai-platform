import aiomysql
import pymysql.err
from fastapi import APIRouter, Header, HTTPException, Request

from app.common import (
    json_dump,
    jsonable_row,
    make_event_idempotency_key,
    trace_id,
    uuid4_str,
)
from app.config import settings
from app.deps import MysqlPoolDep, RedisDep
from app.kafka_bus import publish_event, schedule_publish

router = APIRouter(prefix="/jobs", tags=["jobs"])
JOB_CACHE = "job:"


async def redis_get_job(redis: RedisDep, jid: str) -> dict | None:
    raw = await redis.get(f"{JOB_CACHE}{jid}")
    if not raw:
        return None
    import json

    return json.loads(raw)


async def redis_set_job(redis: RedisDep, jid: str, data: dict) -> None:
    await redis.setex(f"{JOB_CACHE}{jid}", settings.cache_ttl, json_dump(data))


async def redis_del_job(redis: RedisDep, jid: str) -> None:
    await redis.delete(f"{JOB_CACHE}{jid}")


def page_limit(body: dict):
    page = max(int(body.get("page") or 1), 1)
    limit = min(max(int(body.get("limit") or 20), 1), 100)
    return page, limit, (page - 1) * limit


@router.post("/create")
async def create_job(
    body: dict,
    pool: MysqlPoolDep,
    x_trace_id: str | None = Header(None, alias="x-trace-id"),
    x_idempotency_key: str | None = Header(None, alias="x-idempotency-key"),
):
    rid = body.get("recruiter_id")
    title = body.get("title")
    if not rid or not title:
        raise HTTPException(status_code=400, detail="recruiter_id and title required")

    job_id = uuid4_str()
    effective_company_id: str | None = None

    async with pool.acquire() as conn:
        await conn.begin()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                effective_company_id = body.get("company_id")
                if not effective_company_id:
                    await cur.execute(
                        "SELECT company_id FROM recruiters WHERE recruiter_id = %s LIMIT 1",
                        [rid],
                    )
                    rr = await cur.fetchone()
                    effective_company_id = rr["company_id"] if rr else None
                if not effective_company_id:
                    raise HTTPException(status_code=400, detail="company_id missing for recruiter")

                await cur.execute(
                    """INSERT INTO jobs
               (job_id, company_id, recruiter_id, title, description, seniority_level, employment_type,
                city, state, country, work_mode, salary_min, salary_max, industry)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    [
                        job_id,
                        effective_company_id,
                        rid,
                        title,
                        body.get("description"),
                        body.get("seniority_level"),
                        body.get("employment_type"),
                        body.get("city"),
                        body.get("state"),
                        body.get("country"),
                        body.get("work_mode"),
                        body.get("salary_min"),
                        body.get("salary_max"),
                        body.get("industry"),
                    ],
                )

                skills = body.get("skills") or []
                if isinstance(skills, list):
                    normalized = sorted({str(s).strip() for s in skills if str(s).strip()})
                    for sk in normalized:
                        await cur.execute(
                            "INSERT INTO job_skills (job_id, skill) VALUES (%s,%s)", [job_id, sk]
                        )
            await conn.commit()
        except HTTPException:
            await conn.rollback()
            raise
        except Exception:
            await conn.rollback()
            raise

    tid = trace_id(body, x_trace_id)
    publish_event(
        topic="job.posted",
        event_type="job.posted",
        actor_id=str(rid),
        entity_type="job",
        entity_id=job_id,
        payload={
            "title": title,
            "recruiter_id": rid,
            "company_id": effective_company_id,
            "city": body.get("city"),
            "state": body.get("state"),
            "country": body.get("country"),
        },
        trace_id=tid,
        idempotency_key=make_event_idempotency_key(body, x_idempotency_key, "job.posted", job_id),
    )

    return {"job_id": job_id}


@router.post("/get")
async def get_job(
    body: dict,
    pool: MysqlPoolDep,
    redis: RedisDep,
    request: Request,
    x_trace_id: str | None = Header(None, alias="x-trace-id"),
    x_idempotency_key: str | None = Header(None, alias="x-idempotency-key"),
):
    jid = body.get("job_id")
    if not jid:
        raise HTTPException(status_code=400, detail="job_id required")

    viewer = request.headers.get("x-user-id") or body.get("member_id") or "anonymous"
    cached_row = await redis_get_job(redis, jid)

    tid = trace_id(body, x_trace_id)

    if cached_row:
        schedule_publish(
            topic="job.viewed",
            event_type="job.viewed",
            actor_id=str(viewer),
            entity_type="job",
            entity_id=jid,
            payload={"recruiter_id": cached_row.get("recruiter_id")},
            trace_id=tid,
            idempotency_key=make_event_idempotency_key(body, x_idempotency_key, "job.viewed", jid),
        )

        async with pool.acquire() as conn:
            async with conn.cursor() as cur:
                await cur.execute("UPDATE jobs SET views_count = views_count + 1 WHERE job_id=%s", [jid])
        return {**cached_row, "_cache": True}

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """SELECT j.*, r.company_name, r.company_industry FROM jobs j
               JOIN recruiters r ON r.recruiter_id = j.recruiter_id WHERE j.job_id = %s""",
                [jid],
            )
            rows = await cur.fetchall()

    if not rows:
        raise HTTPException(status_code=404, detail="Job not found")

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT skill FROM job_skills WHERE job_id = %s ORDER BY skill ASC", [jid]
            )
            ski = await cur.fetchall()

    job = {**rows[0], "skills": [s["skill"] for s in ski]}
    job_js = jsonable_row(job)
    await redis_set_job(redis, jid, job_js)

    async with pool.acquire() as conn:
        async with conn.cursor() as cur:
            await cur.execute("UPDATE jobs SET views_count = views_count + 1 WHERE job_id=%s", [jid])

    publish_event(
        topic="job.viewed",
        event_type="job.viewed",
        actor_id=str(viewer),
        entity_type="job",
        entity_id=jid,
        payload={"recruiter_id": job_js.get("recruiter_id")},
        trace_id=tid,
        idempotency_key=make_event_idempotency_key(body, x_idempotency_key, "job.viewed", jid),
    )

    return job_js


@router.post("/update")
async def update_job(body: dict, pool: MysqlPoolDep, redis: RedisDep):
    jid = body.get("job_id")
    if not jid:
        raise HTTPException(status_code=400, detail="job_id required")
    allowed = {
        "title",
        "description",
        "seniority_level",
        "employment_type",
        "city",
        "state",
        "country",
        "work_mode",
        "salary_min",
        "salary_max",
        "industry",
        "status",
    }
    updates = [(k, body[k]) for k in allowed if k in body]
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT recruiter_id FROM jobs WHERE job_id=%s", [jid])
            r = await cur.fetchone()
            if not r:
                raise HTTPException(status_code=404, detail="Job not found")
            if body.get("recruiter_id") and r["recruiter_id"] != body["recruiter_id"]:
                raise HTTPException(status_code=403, detail="Only the owning recruiter can update this job")
            clauses = ",".join(f"{k}=%s" for k, _ in updates)
            await cur.execute(
                f"UPDATE jobs SET {clauses} WHERE job_id=%s",
                [v for _, v in updates] + [jid],
            )

    await redis_del_job(redis, jid)
    return {"success": True, "updated_fields": [k for k, _ in updates]}


@router.post("/search")
async def search_jobs(body: dict, pool: MysqlPoolDep):
    page, limit, offset = page_limit(body)
    keyword = body.get("keyword")
    location = body.get("location")
    employment_type = body.get("employment_type") or body.get("job_type")
    industry = body.get("industry")
    work_mode = body.get("work_mode")
    seniority = body.get("seniority_level")

    q = """SELECT DISTINCT j.*, r.company_name, r.company_industry FROM jobs j
       JOIN recruiters r ON r.recruiter_id = j.recruiter_id
       LEFT JOIN job_skills js ON js.job_id = j.job_id
       WHERE j.status = 'open'"""
    params: list = []
    if keyword:
        q += " AND (j.title LIKE %s OR js.skill LIKE %s OR r.company_name LIKE %s)"
        kw = f"%{keyword}%"
        params.extend([kw, kw, kw])
    if location:
        q += " AND (j.city LIKE %s OR j.state LIKE %s OR j.country LIKE %s)"
        loc = f"%{location}%"
        params.extend([loc, loc, loc])
    if employment_type:
        q += " AND j.employment_type = %s"
        params.append(employment_type)
    if seniority:
        q += " AND j.seniority_level = %s"
        params.append(seniority)
    if industry:
        q += " AND j.industry LIKE %s"
        params.append(f"%{industry}%")
    if work_mode:
        q += " AND j.work_mode = %s"
        params.append(work_mode)
    count_q = q.replace(
        "SELECT DISTINCT j.*, r.company_name, r.company_industry FROM jobs j",
        "SELECT COUNT(DISTINCT j.job_id) AS total FROM jobs j",
    )
    q += f" ORDER BY j.posted_at DESC LIMIT {limit} OFFSET {offset}"
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(count_q, params)
            total = (await cur.fetchone() or {}).get("total", 0)
            await cur.execute(q, params)
            rows = await cur.fetchall()

    return {"results": jsonable_row(rows), "page": page, "limit": limit, "total": total}


@router.post("/close")
async def close_job(
    body: dict,
    pool: MysqlPoolDep,
    redis: RedisDep,
    x_trace_id: str | None = Header(None, alias="x-trace-id"),
    x_idempotency_key: str | None = Header(None, alias="x-idempotency-key"),
):
    jid = body.get("job_id")
    recruiter_id = body.get("recruiter_id")
    if not jid:
        raise HTTPException(status_code=400, detail="job_id required")

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT recruiter_id FROM jobs WHERE job_id=%s", [jid])
            r = await cur.fetchone()
            if not r:
                raise HTTPException(status_code=404, detail="Job not found")
            if recruiter_id and r["recruiter_id"] != recruiter_id:
                raise HTTPException(status_code=403, detail="Only the owning recruiter can close this job")
            await cur.execute(
                'UPDATE jobs SET status = "closed", closed_at = NOW() WHERE job_id=%s',
                [jid],
            )

    await redis_del_job(redis, jid)

    actor = recruiter_id or r["recruiter_id"]
    publish_event(
        topic="job.closed",
        event_type="job.closed",
        actor_id=str(actor),
        entity_type="job",
        entity_id=jid,
        payload={"recruiter_id": r["recruiter_id"]},
        trace_id=trace_id(body, x_trace_id),
        idempotency_key=make_event_idempotency_key(body, x_idempotency_key, "job.closed", jid),
    )
    return {"success": True}


@router.post("/byRecruiter")
async def by_recruiter(body: dict, pool: MysqlPoolDep):
    rid = body.get("recruiter_id")
    if not rid:
        raise HTTPException(status_code=400, detail="recruiter_id required")
    page, limit, offset = page_limit(body)
    q = f"""SELECT j.*, r.company_name, r.company_industry FROM jobs j
       JOIN recruiters r ON r.recruiter_id = j.recruiter_id WHERE j.recruiter_id=%s
       ORDER BY j.posted_at DESC LIMIT {limit} OFFSET {offset}"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(q, [rid])
            rows = await cur.fetchall()

    return {"results": jsonable_row(rows), "page": page, "limit": limit}


@router.post("/save")
async def save_job(
    body: dict,
    pool: MysqlPoolDep,
    x_trace_id: str | None = Header(None, alias="x-trace-id"),
    x_idempotency_key: str | None = Header(None, alias="x-idempotency-key"),
):
    mid, jid = body.get("member_id"), body.get("job_id")
    if not mid or not jid:
        raise HTTPException(status_code=400, detail="member_id and job_id required")

    async with pool.acquire() as conn:
        await conn.begin()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT recruiter_id, status FROM jobs WHERE job_id=%s", [jid])
                jr = await cur.fetchone()
                if not jr:
                    await conn.rollback()
                    raise HTTPException(status_code=404, detail="Job not found")
                await cur.execute(
                    "INSERT INTO saved_jobs (member_id, job_id, saved_at) VALUES (%s,%s,NOW())",
                    [mid, jid],
                )
                await cur.execute(
                    "UPDATE jobs SET saves_count = saves_count + 1 WHERE job_id=%s", [jid]
                )
            await conn.commit()
        except pymysql.err.IntegrityError as e:
            await conn.rollback()
            if e.args[0] == 1062:
                raise HTTPException(status_code=409, detail="Job already saved")
            raise

    publish_event(
        topic="job.saved",
        event_type="job.saved",
        actor_id=str(mid),
        entity_type="job",
        entity_id=jid,
        payload={"recruiter_id": jr["recruiter_id"]},
        trace_id=trace_id(body, x_trace_id),
        idempotency_key=make_event_idempotency_key(body, x_idempotency_key, "job.saved", jid),
    )
    return {"member_id": mid, "job_id": jid, "saved": True}


@router.post("/unsave")
async def unsave_job(body: dict, pool: MysqlPoolDep):
    mid, jid = body.get("member_id"), body.get("job_id")
    if not mid or not jid:
        raise HTTPException(status_code=400, detail="member_id and job_id required")

    async with pool.acquire() as conn:
        await conn.begin()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    "DELETE FROM saved_jobs WHERE member_id=%s AND job_id=%s", [mid, jid]
                )
                affected = cur.rowcount
                if affected == 0:
                    await conn.rollback()
                    raise HTTPException(status_code=404, detail="Saved job not found")
                await cur.execute(
                    "UPDATE jobs SET saves_count = GREATEST(saves_count - 1, 0) WHERE job_id=%s",
                    [jid],
                )
            await conn.commit()
        except HTTPException:
            await conn.rollback()
            raise
        except Exception:
            await conn.rollback()
            raise

    return {"member_id": mid, "job_id": jid, "removed": True}


@router.post("/saved")
async def saved(body: dict, pool: MysqlPoolDep):
    mid = body.get("member_id")
    if not mid:
        raise HTTPException(status_code=400, detail="member_id required")
    q = """SELECT j.*, r.company_name, r.company_industry FROM jobs j
       JOIN saved_jobs s ON j.job_id = s.job_id
       JOIN recruiters r ON r.recruiter_id = j.recruiter_id
       WHERE s.member_id=%s ORDER BY s.saved_at DESC"""

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(q, [mid])
            rows = await cur.fetchall()

    return {"results": jsonable_row(rows)}
