"""Kafka consumer for the ai.requests topic."""
import asyncio
import json
from kafka import KafkaConsumer
from config import KAFKA_BROKER
from agents.hiring_assistant.agent import run_hiring_workflow

_APP_LOOP = None


def set_app_loop(loop: asyncio.AbstractEventLoop) -> None:
    global _APP_LOOP
    _APP_LOOP = loop


def start_ai_consumer():
    consumer = KafkaConsumer(
        'ai.requests',
        bootstrap_servers=KAFKA_BROKER,
        group_id='ai-agent-group',
        value_deserializer=lambda v: json.loads(v.decode()),
        auto_offset_reset='latest',
    )
    print('AI Kafka consumer started on ai.requests')
    for msg in consumer:
        event = msg.value
        if event.get('event_type') != 'ai.requested':
            continue
        payload = event.get('payload', {})
        trace_id = event.get('trace_id')
        job_id = payload.get('job_id')
        recruiter_id = payload.get('recruiter_id') or event.get('actor_id')
        top_k = int(payload.get('top_k', 5) or 5)
        if job_id and trace_id and recruiter_id:
            try:
                if _APP_LOOP and _APP_LOOP.is_running():
                    future = asyncio.run_coroutine_threadsafe(
                        run_hiring_workflow(job_id, recruiter_id, top_k=top_k, trace_id=trace_id, source='kafka'),
                        _APP_LOOP,
                    )
                    future.result(timeout=300)
                else:
                    # Fallback for local dev: run in this thread if app loop is unavailable.
                    asyncio.run(run_hiring_workflow(job_id, recruiter_id, top_k=top_k, trace_id=trace_id, source='kafka'))
            except Exception as exc:
                print(f'AI workflow consumer error [{trace_id}]: {exc}')
