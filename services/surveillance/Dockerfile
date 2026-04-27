FROM python:3.11-slim

WORKDIR /app

COPY services/surveillance/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY shared/ /app/shared/
COPY services/surveillance/src/ /app/surveillance/

ENV PYTHONPATH=/app

CMD ["celery", "-A", "shared.celery_app", "worker", "-l", "info", "-Q", "surveillance"]
