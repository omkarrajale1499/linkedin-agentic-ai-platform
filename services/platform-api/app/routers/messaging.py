from datetime import datetime

from fastapi import APIRouter, Header, HTTPException
from pymongo.errors import DuplicateKeyError

from app.common import jsonable_row, make_event_idempotency_key, trace_id, uuid4_str
from app.deps import MongoDep
from app.kafka_bus import publish_event

threads_router = APIRouter(prefix="/threads", tags=["threads"])
messages_router = APIRouter(prefix="/messages", tags=["messages"])


def _normalize_participants(ids: list | None):
    out = sorted({str(x).strip() for x in (ids or []) if x})
    return out


@threads_router.post("/open")
async def threads_open(body: dict, mongo: MongoDep):
    normalized = _normalize_participants(body.get("participant_ids"))
    if len(normalized) < 2:
        raise HTTPException(status_code=400, detail="At least two participant_ids are required")

    threads = mongo["threads"]
    existing_docs = (
        await threads.find({"participant_ids": {"$all": normalized, "$size": len(normalized)}})
        .sort("updated_at", -1)
        .limit(1)
        .to_list(length=1)
    )
    existing = existing_docs[0] if existing_docs else None
    if existing:
        return {"thread_id": existing["thread_id"], "existing": True}

    thread_id = uuid4_str()
    now = datetime.utcnow()
    doc = {"thread_id": thread_id, "participant_ids": normalized, "created_at": now, "updated_at": now}
    await threads.insert_one(doc)
    return {"thread_id": thread_id, "existing": False}


@threads_router.post("/get")
async def threads_get(body: dict, mongo: MongoDep):
    tid = body.get("thread_id")
    if not tid:
        raise HTTPException(status_code=400, detail="thread_id required")
    row = await mongo["threads"].find_one({"thread_id": tid})
    if not row:
        raise HTTPException(status_code=404, detail="Thread not found")
    row.pop("_id", None)
    return jsonable_row(row)


@threads_router.post("/byUser")
async def threads_by_user(body: dict, mongo: MongoDep):
    uid = body.get("user_id")
    if not uid:
        raise HTTPException(status_code=400, detail="user_id required")
    page = max(int(body.get("page") or 1), 1)
    limit = max(int(body.get("limit") or 20), 1)
    cursor = mongo["threads"].find({"participant_ids": uid}).sort("updated_at", -1).skip((page - 1) * limit).limit(limit)
    results = []
    async for r in cursor:
        r.pop("_id", None)
        results.append(r)
    return {"results": jsonable_row(results), "page": page, "limit": limit}


@messages_router.post("/send", status_code=201)
async def send_message(
    body: dict,
    mongo: MongoDep,
    x_trace_id: str | None = Header(None, alias="x-trace-id"),
    x_idempotency_key: str | None = Header(None, alias="x-idempotency-key"),
):
    tid = body.get("thread_id")
    sender_id = body.get("sender_id")
    text = body.get("message_text")
    if not tid or not sender_id or not text:
        raise HTTPException(status_code=400, detail="thread_id, sender_id, message_text required")

    thread = await mongo["threads"].find_one({"thread_id": tid})
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    if sender_id not in thread.get("participant_ids", []):
        raise HTTPException(status_code=403, detail="Sender is not a participant in this thread")

    mid = uuid4_str()
    ikey = body.get("idempotency_key") or uuid4_str()
    msgs = mongo["messages"]
    threads = mongo["threads"]

    now = datetime.utcnow()
    try:
        await msgs.insert_one(
            {
                "message_id": mid,
                "thread_id": tid,
                "sender_id": sender_id,
                "message_text": text,
                "idempotency_key": ikey,
                "sent_at": now,
            }
        )
    except DuplicateKeyError:
        raise HTTPException(status_code=409, detail="Duplicate message (idempotency)") from None

    await threads.update_one({"thread_id": tid}, {"$set": {"last_message": text, "updated_at": now}})

    publish_event(
        topic="message.sent",
        event_type="message.sent",
        actor_id=str(sender_id),
        entity_type="thread",
        entity_id=tid,
        payload={"message_id": mid, "message_text": text},
        trace_id=trace_id(body, x_trace_id),
        idempotency_key=make_event_idempotency_key(body, x_idempotency_key, "message.sent", mid),
    )

    return {"message_id": mid}


@messages_router.post("/list")
async def messages_list(body: dict, mongo: MongoDep):
    tid = body.get("thread_id")
    if not tid:
        raise HTTPException(status_code=400, detail="thread_id required")
    page = max(int(body.get("page") or 1), 1)
    limit = max(int(body.get("limit") or 50), 1)

    cursor = mongo["messages"].find({"thread_id": tid}).sort("sent_at", 1).skip((page - 1) * limit).limit(limit)
    results = []
    async for r in cursor:
        r.pop("_id", None)
        results.append(r)

    return {"results": jsonable_row(results), "page": page, "limit": limit}
