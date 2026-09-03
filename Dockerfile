FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PGSSLROOTCERT=/etc/ssl/certs/timeweb-cloud-ca.crt \
    PORT=8080

WORKDIR /app

COPY requirements.txt ./
RUN apt-get update \
    && apt-get install --yes --no-install-recommends ca-certificates curl \
    && curl --fail --silent --show-error --location \
        https://st.timeweb.com/cloud-static/ca.crt \
        --output /etc/ssl/certs/timeweb-cloud-ca.crt \
    && echo "404d1f55c314a51297d9a728021424fa55a2086ceb4ed66fcf194a1af7bc6980  /etc/ssl/certs/timeweb-cloud-ca.crt" \
        | sha256sum --check --strict \
    && pip install --no-cache-dir --requirement requirements.txt \
    && apt-get purge --yes --auto-remove curl \
    && rm -rf /var/lib/apt/lists/*

COPY ke_box_calc ./ke_box_calc
COPY migrations ./migrations
COPY public ./public

RUN addgroup --system --gid 10001 app \
    && adduser --system --uid 10001 --ingroup app app

USER app

CMD ["sh", "-c", "exec uvicorn ke_box_calc.main:app --host 0.0.0.0 --port ${PORT}"]
