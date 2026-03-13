FROM python:3.11-slim
WORKDIR /app
COPY services/graph-builder/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY shared/ /app/shared/
COPY services/graph-builder/src/ /app/src/
CMD ["python", "-m", "src.main"]
