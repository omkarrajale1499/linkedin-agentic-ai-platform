from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from pymongo.errors import DuplicateKeyError

from app.common import jsonable_row
from app.deps import MongoDep

analytics_router = APIRouter(prefix="/analytics", tags=["analytics"])
events_router = APIRouter(prefix="/events", tags=["events"])


def parse_window_days(value: Any, fallback: int = 30) -> int:
    try:
        n = int(value)
        return n if n > 0 else fallback
    except (TypeError, ValueError):
        return fallback


def since_dt(window_days: int) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=window_days)


async def compute_ai_metrics(db, window_days: int, recruiter_id: str | None = None):
    since = since_dt(window_days)
    match: dict[str, Any] = {"event_type": "ai.results", "timestamp": {"$gte": since}}
    if recruiter_id:
        match["actor_id"] = recruiter_id

    coll = db["event_logs"]

    approval_counts_raw = await coll.aggregate(
        [
            {"$match": match},
            {"$match": {"payload.approval_action": {"$in": ["approve", "edit", "reject"]}}},
            {"$group": {"_id": "$payload.approval_action", "count": {"$sum": 1}}},
        ]
    ).to_list(length=None)

    quality_rows = await coll.aggregate(
        [
            {"$match": match},
            {"$unwind": {"path": "$payload.shortlist", "preserveNullAndEmptyArrays": False}},
            {
                "$group": {
                    "_id": None,
                    "avg_match_score": {"$avg": "$payload.shortlist.match_score"},
                    "evaluated_candidates": {"$sum": 1},
                    "avg_skills_overlap": {
                        "$avg": {"$size": {"$ifNull": ["$payload.shortlist.skills_overlap", []]}}
                    },
                }
            },
        ]
    ).to_list(length=None)

    counts = {row["_id"]: row["count"] for row in approval_counts_raw}
    total_ap = (counts.get("approve", 0) + counts.get("edit", 0) + counts.get("reject", 0))
    q_row = quality_rows[0] if quality_rows else {}

    return {
        "approval_counts": {
            "approved_as_is": counts.get("approve", 0),
            "edited_then_approved": counts.get("edit", 0),
            "rejected": counts.get("reject", 0),
            "total_reviewed": total_ap,
        },
        "approval_rate": round(((counts.get("approve", 0) + counts.get("edit", 0)) / total_ap), 3) if total_ap else 0,
        "average_match_score": round(q_row["avg_match_score"], 3) if q_row.get("avg_match_score") else 0,
        "average_skills_overlap": round(q_row["avg_skills_overlap"], 2)
        if q_row.get("avg_skills_overlap")
        else 0,
        "evaluated_candidates": int(q_row.get("evaluated_candidates") or 0),
    }


@events_router.post("/ingest")
async def ingest(body: dict, mongo: MongoDep):
    if not body.get("event_type"):
        raise HTTPException(status_code=400, detail="event_type required")

    ts = body.get("timestamp") or datetime.now(timezone.utc).isoformat()
    if isinstance(ts, str):
        try:
            ts_parsed = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        except ValueError:
            ts_parsed = datetime.now(timezone.utc)
    else:
        ts_parsed = ts

    doc = {**body, "timestamp": ts_parsed}
    try:
        await mongo["event_logs"].insert_one(doc)
        return JSONResponse({"success": True}, status_code=201)
    except DuplicateKeyError:
        return JSONResponse({"success": True, "duplicate": True}, status_code=200)


@analytics_router.post("/jobs/top")
async def jobs_top(body: dict, mongo: MongoDep):
    metric = body.get("metric") or "applications"
    window_days = parse_window_days(body.get("window_days"), 30)
    limit = max(int(body.get("limit") or 10), 1)
    since = since_dt(window_days)

    if metric == "applications":
        match = {"event_type": "application.submitted", "timestamp": {"$gte": since}}
        project_job_id = "$payload.job_id"
    elif metric == "saves":
        match = {"event_type": "job.saved", "timestamp": {"$gte": since}}
        project_job_id = "$entity.entity_id"
    else:
        match = {"event_type": "job.viewed", "timestamp": {"$gte": since}}
        project_job_id = "$entity.entity_id"

    coll = mongo["event_logs"]
    results = (
        await coll.aggregate(
            [
                {"$match": match},
                {"$project": {"job_id": project_job_id}},
                {"$match": {"job_id": {"$ne": None}}},
                {"$group": {"_id": "$job_id", "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$limit": limit},
                {"$project": {"job_id": "$_id", "count": 1, "_id": 0}},
            ]
        ).to_list(length=None)
    )

    return {"metric": metric, "window_days": window_days, "results": results}


@analytics_router.post("/funnel")
async def funnel(body: dict, mongo: MongoDep):
    job_id = body.get("job_id")
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id required")
    window_days = parse_window_days(body.get("window_days"), 30)
    since = since_dt(window_days)
    coll = mongo["event_logs"]

    async def cnt(filters: dict) -> int:
        return await coll.count_documents({**filters, "timestamp": {"$gte": since}})

    views = await cnt({"event_type": "job.viewed", "entity.entity_id": job_id})
    saves = await cnt({"event_type": "job.saved", "entity.entity_id": job_id})
    apply_starts = await cnt({"event_type": "application.started", "payload.job_id": job_id})
    apps = await cnt({"event_type": "application.submitted", "payload.job_id": job_id})

    return {
        "job_id": job_id,
        "funnel": {"views": views, "saves": saves, "apply_start": apply_starts, "submissions": apps},
        "window_days": window_days,
    }


@analytics_router.post("/geo")
async def geo(body: dict, mongo: MongoDep):
    job_id = body.get("job_id")
    if not job_id:
        raise HTTPException(status_code=400, detail="job_id required")
    window_days = parse_window_days(body.get("window_days"), 30)
    since = since_dt(window_days)
    coll = mongo["event_logs"]
    geo_results = (
        await coll.aggregate(
            [
                {
                    "$match": {
                        "event_type": "application.submitted",
                        "payload.job_id": job_id,
                        "timestamp": {"$gte": since},
                    }
                },
                {
                    "$project": {
                        "city": {"$ifNull": ["$payload.city", "Unknown"]},
                        "state": {"$ifNull": ["$payload.state", "Unknown"]},
                    }
                },
                {"$group": {"_id": {"city": "$city", "state": "$state"}, "count": {"$sum": 1}}},
                {"$sort": {"count": -1}},
                {"$project": {"_id": 0, "city": "$_id.city", "state": "$_id.state", "count": 1}},
            ]
        ).to_list(length=None)
    )

    return {"job_id": job_id, "geo": geo_results, "window_days": window_days}


@analytics_router.post("/member/dashboard")
async def member_dashboard(body: dict, mongo: MongoDep):
    member_id = body.get("member_id")
    if not member_id:
        raise HTTPException(status_code=400, detail="member_id required")
    window_days = parse_window_days(body.get("window_days"), 30)
    since = since_dt(window_days)
    coll = mongo["event_logs"]

    profile_views = (
        await coll.aggregate(
            [
                {"$match": {"event_type": "profile.viewed", "entity.entity_id": member_id, "timestamp": {"$gte": since}}},
                {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}}, "views": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
                {"$project": {"_id": 0, "day": "$_id", "views": 1}},
            ]
        ).to_list(length=None)
    )

    app_breakdown = (
        await coll.aggregate(
            [
                {
                    "$match": {
                        "event_type": {"$in": ["application.submitted", "application.status.changed"]},
                        "payload.member_id": member_id,
                        "timestamp": {"$gte": since},
                    }
                },
                {"$sort": {"timestamp": -1}},
                {
                    "$project": {
                        "application_id": {"$ifNull": ["$payload.application_id", "$entity.entity_id"]},
                        "current_status": {
                            "$cond": [
                                {"$eq": ["$event_type", "application.status.changed"]},
                                "$payload.new_status",
                                {"$ifNull": ["$payload.status", "submitted"]},
                            ]
                        },
                    }
                },
                {"$group": {"_id": "$application_id", "current_status": {"$first": "$current_status"}}},
                {"$group": {"_id": "$current_status", "count": {"$sum": 1}}},
                {"$project": {"_id": 0, "status": "$_id", "count": 1}},
            ]
        ).to_list(length=None)
    )

    return {
        "member_id": member_id,
        "profile_views": profile_views,
        "application_status_breakdown": app_breakdown,
        "window_days": window_days,
    }


@analytics_router.post("/recruiter/dashboard")
async def recruiter_dashboard(body: dict, mongo: MongoDep):
    recruiter_id = body.get("recruiter_id")
    selected_job_id = body.get("selected_job_id")
    window_days = parse_window_days(body.get("window_days"), 30)

    if not recruiter_id:
        raise HTTPException(status_code=400, detail="recruiter_id required")
    since = since_dt(window_days)
    coll = mongo["event_logs"]

    top_jobs = (
        await coll.aggregate(
            [
                {"$match": {"event_type": "application.submitted", "payload.recruiter_id": recruiter_id, "timestamp": {"$gte": since}}},
                {"$group": {"_id": "$payload.job_id", "applications": {"$sum": 1}}},
                {"$sort": {"applications": -1}},
                {"$limit": 10},
                {"$project": {"_id": 0, "job_id": "$_id", "applications": 1}},
            ]
        ).to_list(length=None)
    )

    top_jobs_per_month = (
        await coll.aggregate(
            [
                {"$match": {"event_type": "application.submitted", "payload.recruiter_id": recruiter_id, "timestamp": {"$gte": since}}},
                {
                    "$group": {
                        "_id": {
                            "job_id": "$payload.job_id",
                            "month": {"$dateToString": {"format": "%Y-%m", "date": "$timestamp"}},
                        },
                        "applications": {"$sum": 1},
                    }
                },
                {"$sort": {"_id.month": 1, "applications": -1}},
                {"$project": {"_id": 0, "job_id": "$_id.job_id", "month": "$_id.month", "applications": 1}},
            ]
        ).to_list(length=None)
    )

    low_traction = (
        await coll.aggregate(
            [
                {"$match": {"event_type": "application.submitted", "payload.recruiter_id": recruiter_id, "timestamp": {"$gte": since}}},
                {"$group": {"_id": "$payload.job_id", "applications": {"$sum": 1}}},
                {"$sort": {"applications": 1}},
                {"$limit": 5},
                {"$project": {"_id": 0, "job_id": "$_id", "applications": 1}},
            ]
        ).to_list(length=None)
    )

    saved_per_day = (
        await coll.aggregate(
            [
                {"$match": {"event_type": "job.saved", "payload.recruiter_id": recruiter_id, "timestamp": {"$gte": since}}},
                {"$group": {"_id": {"$dateToString": {"format": "%Y-%m-%d", "date": "$timestamp"}}, "count": {"$sum": 1}}},
                {"$sort": {"_id": 1}},
                {"$project": {"_id": 0, "day": "$_id", "count": 1}},
            ]
        ).to_list(length=None)
    )

    saved_per_week = (
        await coll.aggregate(
            [
                {"$match": {"event_type": "job.saved", "payload.recruiter_id": recruiter_id, "timestamp": {"$gte": since}}},
                {
                    "$group": {
                        "_id": {"isoWeekYear": {"$isoWeekYear": "$timestamp"}, "isoWeek": {"$isoWeek": "$timestamp"}},
                        "count": {"$sum": 1},
                    }
                },
                {"$sort": {"_id.isoWeekYear": 1, "_id.isoWeek": 1}},
                {
                    "$project": {
                        "_id": 0,
                        "week": {
                            "$concat": [{"$toString": "$_id.isoWeekYear"}, "-W", {"$toString": "$_id.isoWeek"}],
                        },
                        "count": 1,
                    }
                },
            ]
        ).to_list(length=None)
    )

    clicks_per_job = (
        await coll.aggregate(
            [
                {"$match": {"event_type": "job.viewed", "payload.recruiter_id": recruiter_id, "timestamp": {"$gte": since}}},
                {"$group": {"_id": "$entity.entity_id", "clicks": {"$sum": 1}}},
                {"$sort": {"clicks": -1}},
                {"$project": {"_id": 0, "job_id": "$_id", "clicks": 1}},
            ]
        ).to_list(length=None)
    )

    city_month = []
    if selected_job_id:
        city_month = (
            await coll.aggregate(
                [
                    {
                        "$match": {
                            "event_type": "application.submitted",
                            "payload.recruiter_id": recruiter_id,
                            "payload.job_id": selected_job_id,
                            "timestamp": {"$gte": since},
                        }
                    },
                    {
                        "$group": {
                            "_id": {
                                "city": {"$ifNull": ["$payload.city", "Unknown"]},
                                "month": {"$dateToString": {"format": "%Y-%m", "date": "$timestamp"}},
                            },
                            "applications": {"$sum": 1},
                        }
                    },
                    {"$sort": {"_id.month": 1, "applications": -1}},
                    {"$project": {"_id": 0, "city": "$_id.city", "month": "$_id.month", "applications": 1}},
                ]
            ).to_list(length=None)
        )

    ai_metrics = await compute_ai_metrics(mongo, window_days, recruiter_id)

    return {
        "recruiter_id": recruiter_id,
        "window_days": window_days,
        "selected_job_id": selected_job_id,
        "top_jobs_by_applications": top_jobs,
        "top_jobs_by_applications_per_month": top_jobs_per_month,
        "low_traction_jobs": low_traction,
        "clicks_per_job": clicks_per_job,
        "saved_jobs_per_day": saved_per_day,
        "saved_jobs_per_week": saved_per_week,
        "city_wise_applications_per_month": city_month,
        "ai_metrics": ai_metrics,
    }


@analytics_router.post("/ai/metrics")
async def ai_metrics_only(body: dict, mongo: MongoDep):
    window_days = parse_window_days(body.get("window_days"), 30)
    recruiter_id = body.get("recruiter_id")

    metrics = await compute_ai_metrics(mongo, window_days, recruiter_id)

    out = {"recruiter_id": recruiter_id, "window_days": window_days, **metrics}
    return jsonable_row(out)
