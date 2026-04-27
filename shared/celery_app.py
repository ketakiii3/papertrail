"""Celery app shared across services that enqueue or run tasks.

Broker + result backend = Redis (already in the stack).
Tasks live under `surveillance.tasks` (and any future task modules).
"""

from celery import Celery

from shared.config import settings

celery_app = Celery(
    "papertrail",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
    include=["surveillance.tasks"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_prefetch_multiplier=1,
    task_default_queue="surveillance",
    result_expires=3600,
)
