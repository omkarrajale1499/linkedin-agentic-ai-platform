import asyncio
import json
import logging
import threading
import time
from datetime import datetime
from typing import Any
from uuid import uuid4

from kafka import KafkaConsumer, KafkaProducer
from kafka.errors import KafkaError
from pymongo import MongoClient
from pymongo.errors import DuplicateKeyError
import pymysql

from app.config import settings

log = logging.getLogger("platform-api.kafka")

_producer: KafkaProducer | None = None


def kafka_message(
    *,
    topic: str,
    event_type: str,
    actor_id: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
    trace_id: str,
    idempotency_key: str,
) -> bytes:
    body = {
        "event_type": event_type,
        "trace_id": trace_id or str(uuid4()),
        "timestamp": datetime.utcnow().isoformat(timespec="seconds") + "Z",
        "actor_id": actor_id,
        "entity": {"entity_type": entity_type, "entity_id": entity_id},
        "payload": payload,
        "idempotency_key": idempotency_key or str(uuid4()),
    }
    return json.dumps(body).encode()


def publish_event(
    *,
    topic: str,
    event_type: str,
    actor_id: str,
    entity_type: str,
    entity_id: str,
    payload: dict[str, Any],
    trace_id: str,
    idempotency_key: str,
) -> None:
    global _producer
    if _producer is None:
        log.warning("Kafka producer not connected — skipping %s", event_type)
        return
    raw = kafka_message(
        topic=topic,
        event_type=event_type,
        actor_id=str(actor_id),
        entity_type=entity_type,
        entity_id=str(entity_id),
        payload=payload,
        trace_id=trace_id,
        idempotency_key=idempotency_key,
    )
    try:
        _producer.send(topic, key=str(entity_id).encode(), value=raw).get(timeout=10)
    except KafkaError as e:
        log.error("Kafka publish failed %s/%s: %s", topic, event_type, e)


def schedule_publish(**kwargs: Any) -> None:
    from functools import partial

    try:
        loop = asyncio.get_running_loop()
        loop.create_task(asyncio.to_thread(partial(publish_event, **kwargs)))
    except RuntimeError:
        publish_event(**kwargs)


def ensure_producer_started() -> None:
    global _producer
    if _producer is not None:
        return
    retries = 10
    while retries > 0:
        try:
            _producer = KafkaProducer(
                bootstrap_servers=settings.kafka_broker,
                retries=10,
                request_timeout_ms=30000,
            )
            log.info("Kafka producer connected (platform-api)")
            return
        except Exception as e:
            retries -= 1
            log.warning("Kafka not ready, retrying... (%s left): %s", retries, e)
            time.sleep(3)
    log.error("Could not connect to Kafka — events will not be published")


def _mongo_uri() -> str:
    return (
        f"mongodb://{settings.mongo_user}:{settings.mongo_password}"
        f"@{settings.mongo_host}:{settings.mongo_port}/{settings.mongo_database}?authSource=admin"
    )


def _mysql_connect() -> pymysql.connections.Connection:
    return pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
        database=settings.mysql_database,
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=True,
    )


ALL_TOPICS = [
    "profile.created",
    "profile.updated",
    "profile.viewed",
    "job.posted",
    "job.viewed",
    "job.saved",
    "job.closed",
    "application.submitted",
    "application.status.changed",
    "message.sent",
    "connection.requested",
    "connection.accepted",
    "connection.rejected",
    "ai.requests",
    "ai.results",
]


def _analytics_consumer_loop() -> None:
    client = MongoClient(_mongo_uri())
    coll = client[settings.mongo_database]["event_logs"]
    retries = 10
    consumer = None
    while retries > 0:
        try:
            consumer = KafkaConsumer(
                bootstrap_servers=[settings.kafka_broker],
                group_id=settings.kafka_analytics_group,
                auto_offset_reset="latest",
            )
            consumer.subscribe(list(ALL_TOPICS))
            break
        except Exception as e:
            retries -= 1
            log.warning("[analytics-consumer] Kafka not ready (%s left): %s", retries, e)
            time.sleep(3)
    if consumer is None:
        log.error("[analytics-consumer] Could not start")
        return
    log.info("[analytics-consumer] Started — topics: %s", ", ".join(ALL_TOPICS))
    for msg in consumer:
        try:
            event = json.loads(msg.value.decode())
            ikey = event.get("idempotency_key")
            if not ikey:
                continue
            doc = {**event, "timestamp": datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00")), "_topic": msg.topic}
            try:
                coll.update_one(
                    {"idempotency_key": ikey},
                    {"$setOnInsert": doc},
                    upsert=True,
                )
            except DuplicateKeyError:
                pass
        except Exception as e:
            log.error("[analytics-consumer] Error: %s", e)


def _application_consumer_loop() -> None:
    retries = 10
    consumer = None
    while retries > 0:
        try:
            consumer = KafkaConsumer(
                "job.closed",
                bootstrap_servers=[settings.kafka_broker],
                group_id="application-service-group-fastapi",
                auto_offset_reset="latest",
            )
            break
        except Exception as e:
            retries -= 1
            log.warning("[application-consumer] retry (%s): %s", retries, e)
            time.sleep(3)
    if consumer is None:
        return
    log.info("[application-consumer] listening on job.closed")
    conn = _mysql_connect()
    try:
        for msg in consumer:
            try:
                event = json.loads(msg.value.decode())
                if event.get("event_type") == "job.closed":
                    job_id = event.get("entity", {}).get("entity_id")
                    if not job_id:
                        continue
                    with conn.cursor() as cur:
                        cur.execute(
                            "UPDATE applications SET status = 'rejected' "
                            "WHERE job_id = %s AND status IN ('submitted', 'reviewing')",
                            (job_id,),
                        )
            except Exception as e:
                log.error("[application-consumer] %s", e)
    finally:
        conn.close()


def _connection_consumer_loop() -> None:
    retries = 10
    consumer = None
    while retries > 0:
        try:
            consumer = KafkaConsumer(
                "connection.accepted",
                "connection.rejected",
                bootstrap_servers=[settings.kafka_broker],
                group_id="connection-worker-group-fastapi",
                auto_offset_reset="latest",
            )
            break
        except Exception:
            retries -= 1
            time.sleep(3)
    if consumer is None:
        return
    log.info("[connection-consumer] started")
    conn = _mysql_connect()
    try:
        for msg in consumer:
            try:
                if msg.topic != "connection.accepted":
                    continue
                event = json.loads(msg.value.decode())
                requester_id = event.get("payload", {}).get("requester_id")
                receiver_id = event.get("payload", {}).get("receiver_id")
                if not requester_id or not receiver_id:
                    continue
                with conn.cursor() as cur:
                    for mid in (requester_id, receiver_id):
                        cur.execute(
                            """
                            UPDATE members
                            SET connections_count = (
                              SELECT COUNT(*) FROM connections
                              WHERE member_a = %s OR member_b = %s
                            )
                            WHERE member_id = %s
                            """,
                            (mid, mid, mid),
                        )
            except Exception as e:
                log.error("[connection-consumer] %s", e)
    finally:
        conn.close()


def start_background_consumers() -> None:
    for target in (_analytics_consumer_loop, _application_consumer_loop, _connection_consumer_loop):
        t = threading.Thread(target=target, daemon=True, name=target.__name__)
        t.start()
