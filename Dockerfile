FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

COPY ke_box_calc ./ke_box_calc
COPY migrations ./migrations
COPY public ./public

RUN addgroup --system --gid 10001 app \
    && adduser --system --uid 10001 --ingroup app app

USER app

CMD ["sh", "-c", "exec uvicorn ke_box_calc.main:app --host 0.0.0.0 --port ${PORT}"]
