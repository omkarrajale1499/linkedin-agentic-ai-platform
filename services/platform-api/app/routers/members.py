import aiomysql
from datetime import datetime, timedelta

import bcrypt
import jwt
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

router = APIRouter(prefix="/members", tags=["members"])

CACHE_PREFIX = "member:"


async def redis_get_member(redis_dep, mid: str) -> dict | None:
    raw = await redis_dep.get(f"{CACHE_PREFIX}{mid}")
    if not raw:
        return None
    import json

    return json.loads(raw)


async def redis_set_member(redis_dep, mid: str, data: dict) -> None:
    await redis_dep.setex(f"{CACHE_PREFIX}{mid}", settings.cache_ttl, json_dump(jsonable_row(data)))


async def redis_del_member(redis_dep, mid: str) -> None:
    await redis_dep.delete(f"{CACHE_PREFIX}{mid}")


@router.post("/create")
async def create_member(
    body: dict,
    pool: MysqlPoolDep,
    redis: RedisDep,
    request: Request,
    x_trace_id: str | None = Header(None, alias="x-trace-id"),
    x_idempotency_key: str | None = Header(None, alias="x-idempotency-key"),
):
    first_name = body.get("first_name")
    last_name = body.get("last_name")
    email = body.get("email")
    password = body.get("password")
    if not first_name or not last_name or not email or not password:
        raise HTTPException(status_code=400, detail="first_name, last_name, email, password are required")

    member_id = uuid4_str()
    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt(rounds=10)).decode()

    async with pool.acquire() as conn:
        await conn.begin()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """INSERT INTO members
                   (member_id, first_name, last_name, email, password_hash, phone, city, state, country, headline, about, profile_photo_url, resume_url, resume_text)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    [
                        member_id,
                        first_name,
                        last_name,
                        email,
                        password_hash,
                        body.get("phone"),
                        body.get("city"),
                        body.get("state"),
                        body.get("country"),
                        body.get("headline"),
                        body.get("about"),
                        body.get("profile_photo_url"),
                        body.get("resume_url"),
                        body.get("resume_text"),
                    ],
                )
                skills = body.get("skills") or []
                if isinstance(skills, list) and skills:
                    seen = sorted({str(s).strip() for s in skills if str(s).strip()})
                    for sk in seen:
                        await cur.execute(
                            "INSERT IGNORE INTO member_skills (member_id, skill) VALUES (%s,%s)",
                            [member_id, sk],
                        )
            await conn.commit()
        except pymysql.err.IntegrityError as e:
            await conn.rollback()
            if e.args[0] == 1062:
                raise HTTPException(status_code=409, detail="Email already exists")
            raise
        except Exception:
            await conn.rollback()
            raise

    tid = trace_id(body, x_trace_id)
    publish_event(
        topic="profile.created",
        event_type="profile.created",
        actor_id=member_id,
        entity_type="member",
        entity_id=member_id,
        payload={"email": email, "city": body.get("city"), "state": body.get("state"), "country": body.get("country")},
        trace_id=tid,
        idempotency_key=make_event_idempotency_key(body, x_idempotency_key, "profile.created", member_id),
    )

    expire = datetime.utcnow() + timedelta(days=7)
    tok = jwt.encode(
        {"id": member_id, "role": "member", "exp": expire},
        settings.jwt_secret,
        algorithm="HS256",
    )
    token_str = tok if isinstance(tok, str) else (tok.decode() if isinstance(tok, bytes) else str(tok))
    return {"member_id": member_id, "token": token_str}


@router.post("/login")
async def login_member(body: dict, pool: MysqlPoolDep):
    email = body.get("email")
    password = body.get("password")
    if not email or not password:
        raise HTTPException(status_code=400, detail="email and password are required")
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM members WHERE email = %s AND is_deleted = 0", [email])
            rows = await cur.fetchall()
    if not rows:
        raise HTTPException(status_code=401, detail="Invalid email or password")
    member = rows[0]
    if not bcrypt.checkpw(password.encode(), (member.get("password_hash") or "").encode()):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    expire = datetime.utcnow() + timedelta(days=7)
    tok = jwt.encode(
        {"id": member["member_id"], "role": "member", "exp": expire},
        settings.jwt_secret,
        algorithm="HS256",
    )
    safe = {k: v for k, v in member.items() if k != "password_hash"}
    safe["token"] = tok if isinstance(tok, str) else (tok.decode() if isinstance(tok, bytes) else str(tok))
    return jsonable_row(safe)


@router.post("/get")
async def get_member(
    body: dict,
    pool: MysqlPoolDep,
    redis: RedisDep,
    request: Request,
    x_trace_id: str | None = Header(None, alias="x-trace-id"),
    x_idempotency_key: str | None = Header(None, alias="x-idempotency-key"),
):
    member_id = body.get("member_id")
    if not member_id:
        raise HTTPException(status_code=400, detail="member_id required")
    viewer_id = body.get("viewer_id") or request.headers.get("x-user-id")
    cached = await redis_get_member(redis, member_id)
    tid = trace_id(body, x_trace_id)

    if cached:
        if viewer_id and viewer_id != member_id:
            schedule_publish(
                topic="profile.viewed",
                event_type="profile.viewed",
                actor_id=str(viewer_id),
                entity_type="member",
                entity_id=member_id,
                payload={},
                trace_id=tid,
                idempotency_key=make_event_idempotency_key(body, x_idempotency_key, "profile.viewed", member_id),
            )
        return {**cached, "_cache": True}

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT * FROM members WHERE member_id = %s AND is_deleted = 0", [member_id])
            rows = await cur.fetchall()
    if not rows:
        raise HTTPException(status_code=404, detail="Member not found")
    mid = rows[0]
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT skill FROM member_skills WHERE member_id = %s ORDER BY skill ASC", [member_id]
            )
            skill_rows = await cur.fetchall()
            await cur.execute(
                """SELECT * FROM member_experience WHERE member_id = %s
               ORDER BY is_current DESC, start_date DESC""",
                [member_id],
            )
            exp = await cur.fetchall()
            await cur.execute(
                """SELECT * FROM member_education WHERE member_id = %s
               ORDER BY end_year DESC, start_year DESC""",
                [member_id],
            )
            edu = await cur.fetchall()

    member = {**mid, "skills": [s["skill"] for s in skill_rows], "experience": exp, "education": edu}
    member_js = jsonable_row(member)
    await redis_set_member(redis, member_id, member_js)

    if viewer_id and viewer_id != member_id:
        schedule_publish(
            topic="profile.viewed",
            event_type="profile.viewed",
            actor_id=str(viewer_id),
            entity_type="member",
            entity_id=member_id,
            payload={},
            trace_id=tid,
            idempotency_key=make_event_idempotency_key(body, x_idempotency_key, "profile.viewed", member_id),
        )

    return member_js


@router.post("/update")
async def update_member(
    body: dict,
    pool: MysqlPoolDep,
    redis: RedisDep,
    x_trace_id: str | None = Header(None, alias="x-trace-id"),
    x_idempotency_key: str | None = Header(None, alias="x-idempotency-key"),
):
    mid = body.get("member_id")
    if not mid:
        raise HTTPException(status_code=400, detail="member_id required")
    allowed = {
        "first_name",
        "last_name",
        "phone",
        "city",
        "state",
        "country",
        "headline",
        "about",
        "profile_photo_url",
        "resume_url",
        "resume_text",
    }
    updates = []
    for k in allowed:
        if k not in body:
            continue
        v = body[k]
        if k == "profile_photo_url" and isinstance(v, str) and v.strip() == "":
            v = None
        updates.append((k, v))
    if not updates:
        raise HTTPException(status_code=400, detail="No valid fields to update")

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT member_id FROM members WHERE member_id = %s AND is_deleted = 0", [mid])
            if not await cur.fetchall():
                raise HTTPException(status_code=404, detail="Member not found")
            clauses = ",".join(f"{k}=%s" for k, _ in updates)
            await cur.execute(
                f"UPDATE members SET {clauses} WHERE member_id=%s",
                [v for _, v in updates] + [mid],
            )

    await redis_del_member(redis, mid)

    fid = ",".join(k for k, _ in updates)
    publish_event(
        topic="profile.updated",
        event_type="profile.updated",
        actor_id=mid,
        entity_type="member",
        entity_id=mid,
        payload={k: v for k, v in updates},
        trace_id=trace_id(body, x_trace_id),
        idempotency_key=make_event_idempotency_key(body, x_idempotency_key, "profile.updated", mid),
    )

    return {"success": True, "updated_fields": [k for k, _ in updates]}


@router.post("/delete")
async def delete_member(body: dict, pool: MysqlPoolDep, redis: RedisDep):
    mid = body.get("member_id")
    if not mid:
        raise HTTPException(status_code=400, detail="member_id required")
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("SELECT member_id FROM members WHERE member_id = %s AND is_deleted = 0", [mid])
            if not await cur.fetchall():
                raise HTTPException(status_code=404, detail="Member not found")
            await cur.execute("UPDATE members SET is_deleted = 1 WHERE member_id=%s", [mid])
    await redis_del_member(redis, mid)
    return {"member_id": mid, "deleted": True}


@router.post("/search")
async def search_members(body: dict, pool: MysqlPoolDep):
    skill = body.get("skill")
    location = body.get("location")
    keyword = body.get("keyword")
    page = int(body.get("page") or 1)
    limit = int(body.get("limit") or 20)
    offset = (page - 1) * limit

    params: list = []
    q = "SELECT DISTINCT m.* FROM members m"
    if skill:
        q += " JOIN member_skills ms ON m.member_id = ms.member_id AND ms.skill LIKE %s"
        params.append(f"%{skill}%")
    q += " WHERE m.is_deleted = 0"
    if location:
        q += " AND (m.city LIKE %s OR m.state LIKE %s OR m.country LIKE %s)"
        params.extend([f"%{location}%"] * 3)
    if keyword:
        q += """ AND (
        m.email LIKE %s OR m.first_name LIKE %s OR m.last_name LIKE %s
        OR CONCAT(m.first_name, ' ', m.last_name) LIKE %s
        OR m.headline LIKE %s OR m.about LIKE %s)"""
        kw = f"%{keyword}%"
        params.extend([kw, kw, kw, kw, kw, kw])
    q += f" ORDER BY m.updated_at DESC LIMIT {limit} OFFSET {offset}"
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(q, params)
            rows = await cur.fetchall()

    return {"results": jsonable_row(rows), "page": page, "limit": limit}


@router.post("/skills/add")
async def add_skill(body: dict, pool: MysqlPoolDep, redis: RedisDep):
    mid = body.get("member_id")
    skill = body.get("skill")
    if not mid or not skill:
        raise HTTPException(status_code=400, detail="member_id and skill required")
    skill = str(skill).strip()
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("INSERT IGNORE INTO member_skills (member_id, skill) VALUES (%s,%s)", [mid, skill])
    await redis_del_member(redis, mid)
    return {"success": True, "skill": skill}


@router.post("/skills/remove")
async def remove_skill(body: dict, pool: MysqlPoolDep, redis: RedisDep):
    mid = body.get("member_id")
    skill = body.get("skill")
    if not mid or not skill:
        raise HTTPException(status_code=400, detail="member_id and skill required")
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute("DELETE FROM member_skills WHERE member_id=%s AND skill=%s", [mid, skill])
    await redis_del_member(redis, mid)
    return {"success": True}
