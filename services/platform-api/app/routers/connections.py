import aiomysql
import pymysql.err
from fastapi import APIRouter, Header, HTTPException

from app.common import jsonable_row, make_event_idempotency_key, trace_id, uuid4_str
from app.deps import MysqlPoolDep
from app.kafka_bus import publish_event

router = APIRouter(prefix="/connections", tags=["connections"])


def normalize_pair(a: str, b: str):
    return tuple(sorted([a, b]))


async def resolve_user_row(pool, uid: str) -> dict | None:
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                """SELECT member_id AS id, first_name, last_name, email, city, state, country, headline,
                'member' AS user_type
             FROM members WHERE member_id=%s AND is_deleted=0""",
                [uid],
            )
            mr = await cur.fetchone()
            if mr:
                return mr
            await cur.execute(
                """SELECT recruiter_id AS id, first_name, last_name, email,
                NULL AS city, NULL AS state, NULL AS country,
                COALESCE(NULLIF(company_name, ''), company_industry, 'Recruiter') AS headline,
                'recruiter' AS user_type
             FROM recruiters WHERE recruiter_id=%s AND (is_deleted IS NULL OR is_deleted=0)""",
                [uid],
            )
            return await cur.fetchone()


async def has_existing_connection(connmysql, ua: str, ub: str) -> bool:
    a, b = normalize_pair(ua, ub)
    async with connmysql.cursor(aiomysql.DictCursor) as cur:
        await cur.execute(
            "SELECT id FROM connections WHERE member_a=%s AND member_b=%s LIMIT 1",
            [a, b],
        )
        return bool(await cur.fetchone())


@router.post("/request")
async def request_conn(
    body: dict,
    pool: MysqlPoolDep,
    x_trace_id: str | None = Header(None, alias="x-trace-id"),
    x_idempotency_key: str | None = Header(None, alias="x-idempotency-key"),
):
    rid = body.get("requester_id")
    recv = body.get("receiver_id")
    msg = body.get("message")
    ikey = body.get("idempotency_key") or uuid4_str()

    if not rid or not recv:
        raise HTTPException(status_code=400, detail="requester_id and receiver_id required")
    if rid == recv:
        raise HTTPException(status_code=400, detail="Cannot connect to yourself")

    if not await resolve_user_row(pool, rid) or not await resolve_user_row(pool, recv):
        raise HTTPException(status_code=404, detail="One or both users not found")

    rid_new: str | None = None

    async with pool.acquire() as conn:
        await conn.begin()
        try:
            if await has_existing_connection(conn, rid, recv):
                await conn.rollback()
                raise HTTPException(status_code=409, detail="Members are already connected")

            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """SELECT request_id, requester_id, receiver_id, status FROM connection_requests
                   WHERE (requester_id=%s AND receiver_id=%s) OR (requester_id=%s AND receiver_id=%s)
                   ORDER BY created_at DESC""",
                    [rid, recv, recv, rid],
                )
                existing_requests = await cur.fetchall()

            pending_reverse = next(
                (
                    r
                    for r in existing_requests
                    if r["requester_id"] == recv and r["receiver_id"] == rid and r["status"] == "pending"
                ),
                None,
            )
            if pending_reverse:
                await conn.rollback()
                raise HTTPException(
                    status_code=409,
                    detail={
                        "error": "A pending request from the other user already exists",
                        "existing_request_id": pending_reverse["request_id"],
                    },
                )

            forwards = [r for r in existing_requests if r["requester_id"] == rid and r["receiver_id"] == recv]
            existing_forward = forwards[0] if forwards else None
            if existing_forward:
                await conn.rollback()
                if existing_forward["status"] == "pending":
                    raise HTTPException(
                        status_code=409,
                        detail={
                            "error": "Connection request already exists",
                            "request_id": existing_forward["request_id"],
                        },
                    )
                if existing_forward["status"] == "accepted":
                    raise HTTPException(status_code=409, detail="Members are already connected")

            rid_new = uuid4_str()
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute(
                    """INSERT INTO connection_requests
                   (request_id, requester_id, receiver_id, message, idempotency_key)
                   VALUES (%s,%s,%s,%s,%s)""",
                    [rid_new, rid, recv, msg, ikey],
                )
            await conn.commit()
        except HTTPException:
            await conn.rollback()
            raise
        except pymysql.err.IntegrityError as e:
            await conn.rollback()
            if e.args[0] == 1062:
                raise HTTPException(status_code=409, detail="Connection request already exists")
            raise
        except Exception:
            await conn.rollback()
            raise

    assert rid_new is not None

    publish_event(
        topic="connection.requested",
        event_type="connection.requested",
        actor_id=str(rid),
        entity_type="connection",
        entity_id=rid_new,
        payload={"requester_id": rid, "receiver_id": recv, "message": msg},
        trace_id=trace_id(body, x_trace_id),
        idempotency_key=make_event_idempotency_key(body, x_idempotency_key, "connection.requested", rid_new),
    )
    return {"request_id": rid_new}


@router.post("/accept")
async def accept(
    body: dict,
    pool: MysqlPoolDep,
    x_trace_id: str | None = Header(None, alias="x-trace-id"),
    x_idempotency_key: str | None = Header(None, alias="x-idempotency-key"),
):
    rid = body.get("request_id")
    if not rid:
        raise HTTPException(status_code=400, detail="request_id required")

    async with pool.acquire() as conn:
        await conn.begin()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT * FROM connection_requests WHERE request_id=%s FOR UPDATE", [rid])
                rows = await cur.fetchall()
            if not rows:
                await conn.rollback()
                raise HTTPException(status_code=404, detail="Request not found")
            row = rows[0]
            requester_id = row["requester_id"]
            receiver_id = row["receiver_id"]
            status = row["status"]
            if status == "accepted":
                await conn.rollback()
                return {"success": True, "already_accepted": True}
            if status == "rejected":
                await conn.rollback()
                raise HTTPException(status_code=409, detail="Rejected requests cannot be accepted")

            ma, mb = normalize_pair(requester_id, receiver_id)
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("UPDATE connection_requests SET status='accepted' WHERE request_id=%s", [rid])
                await cur.execute(
                    "INSERT IGNORE INTO connections (member_a, member_b) VALUES (%s,%s)",
                    [ma, mb],
                )
                await cur.execute(
                    "UPDATE members SET connections_count = connections_count + 1 WHERE member_id=%s",
                    [requester_id],
                )
                await cur.execute(
                    "UPDATE members SET connections_count = connections_count + 1 WHERE member_id=%s",
                    [receiver_id],
                )
            await conn.commit()
        except HTTPException:
            await conn.rollback()
            raise
        except Exception:
            await conn.rollback()
            raise

    publish_event(
        topic="connection.accepted",
        event_type="connection.accepted",
        actor_id=str(receiver_id),
        entity_type="connection",
        entity_id=rid,
        payload={"requester_id": requester_id, "receiver_id": receiver_id},
        trace_id=trace_id(body, x_trace_id),
        idempotency_key=make_event_idempotency_key(body, x_idempotency_key, "connection.accepted", rid),
    )
    return {"success": True}


@router.post("/reject")
async def reject(
    body: dict,
    pool: MysqlPoolDep,
    x_trace_id: str | None = Header(None, alias="x-trace-id"),
    x_idempotency_key: str | None = Header(None, alias="x-idempotency-key"),
):
    rid = body.get("request_id")
    if not rid:
        raise HTTPException(status_code=400, detail="request_id required")

    async with pool.acquire() as conn:
        await conn.begin()
        try:
            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("SELECT * FROM connection_requests WHERE request_id=%s FOR UPDATE", [rid])
                rows = await cur.fetchall()
            if not rows:
                await conn.rollback()
                raise HTTPException(status_code=404, detail="Request not found")
            row = rows[0]
            if row["status"] == "accepted":
                await conn.rollback()
                raise HTTPException(status_code=409, detail="Accepted requests cannot be rejected")
            if row["status"] == "rejected":
                await conn.rollback()
                return {"success": True, "already_rejected": True}

            receiver_id = row["receiver_id"]
            requester_id = row["requester_id"]

            async with conn.cursor(aiomysql.DictCursor) as cur:
                await cur.execute("UPDATE connection_requests SET status='rejected' WHERE request_id=%s", [rid])
            await conn.commit()
        except HTTPException:
            await conn.rollback()
            raise
        except Exception:
            await conn.rollback()
            raise

    publish_event(
        topic="connection.rejected",
        event_type="connection.rejected",
        actor_id=str(receiver_id),
        entity_type="connection",
        entity_id=rid,
        payload={"requester_id": requester_id, "receiver_id": receiver_id},
        trace_id=trace_id(body, x_trace_id),
        idempotency_key=make_event_idempotency_key(body, x_idempotency_key, "connection.rejected", rid),
    )
    return {"success": True}


@router.post("/list")
async def list_conn(body: dict, pool: MysqlPoolDep):
    uid = body.get("user_id")
    if not uid:
        raise HTTPException(status_code=400, detail="user_id required")
    page = max(int(body.get("page") or 1), 1)
    limit = max(int(body.get("limit") or 20), 1)
    offset = (page - 1) * limit

    q = f"""SELECT CASE WHEN c.member_a=%s THEN c.member_b ELSE c.member_a END AS other_id, c.connected_at
       FROM connections c WHERE c.member_a=%s OR c.member_b=%s
       ORDER BY c.connected_at DESC LIMIT {limit} OFFSET {offset}"""

    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(q, [uid, uid, uid])
            conn_rows = await cur.fetchall()

    results = []
    for crow in conn_rows:
        profile = await resolve_user_row(pool, crow["other_id"])
        if not profile:
            continue
        results.append(
            {
                "member_id": profile["id"],
                "user_type": profile["user_type"],
                "first_name": profile["first_name"],
                "last_name": profile["last_name"],
                "email": profile["email"],
                "city": profile["city"],
                "state": profile["state"],
                "country": profile["country"],
                "headline": profile["headline"],
                "connected_at": crow["connected_at"],
            }
        )

    return {"results": jsonable_row(results), "page": page, "limit": limit}


@router.post("/pending")
async def pending(body: dict, pool: MysqlPoolDep):
    uid = body.get("user_id")
    if not uid:
        raise HTTPException(status_code=400, detail="user_id required")
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM connection_requests WHERE receiver_id=%s AND status='pending' ORDER BY created_at DESC",
                [uid],
            )
            rows = await cur.fetchall()
    return {"results": jsonable_row(rows)}


@router.post("/sent")
async def sent(body: dict, pool: MysqlPoolDep):
    uid = body.get("user_id")
    if not uid:
        raise HTTPException(status_code=400, detail="user_id required")
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(
                "SELECT * FROM connection_requests WHERE requester_id=%s AND status='pending' ORDER BY created_at DESC",
                [uid],
            )
            rows = await cur.fetchall()
    return {"results": jsonable_row(rows)}


@router.post("/mutual")
async def mutual(body: dict, pool: MysqlPoolDep):
    ua = body.get("user_id")
    ub = body.get("other_id")
    if not ua or not ub:
        raise HTTPException(status_code=400, detail="user_id and other_id required")
    sql = """SELECT DISTINCT m.member_id, m.first_name, m.last_name, m.email, m.city, m.state, m.country, m.headline
       FROM connections c1
       JOIN connections c2 ON IF(c1.member_a=%s, c1.member_b, c1.member_a)=IF(c2.member_a=%s, c2.member_b, c2.member_a)
       JOIN members m ON m.member_id=IF(c1.member_a=%s, c1.member_b, c1.member_a)
       WHERE (c1.member_a=%s OR c1.member_b=%s) AND (c2.member_a=%s OR c2.member_b=%s) AND m.is_deleted=0"""
    async with pool.acquire() as conn:
        async with conn.cursor(aiomysql.DictCursor) as cur:
            await cur.execute(sql, [ua, ub, ua, ua, ua, ub, ub])
            rows = await cur.fetchall()

    return {"results": jsonable_row(rows)}
