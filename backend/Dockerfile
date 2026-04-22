FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY etl /app/etl
COPY db /app/db

RUN chmod +x /app/backend/start.sh

EXPOSE 8000

CMD ["/app/backend/start.sh"]
