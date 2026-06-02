FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev libfreetype6-dev && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Непривілейований користувач рантайму. MPLCONFIGDIR — щоб matplotlib
# (графіки в боті) міг писати кеш у каталог, доступний appuser.
RUN useradd --create-home --uid 10001 appuser \
    && mkdir -p /tmp/mpl && chown appuser:appuser /tmp/mpl
ENV MPLCONFIGDIR=/tmp/mpl
USER appuser

CMD ["sh", "-c", "if [ \"$RUN_MODE\" = 'bot' ]; then python bot.py; else uvicorn main:app --host 0.0.0.0 --port 8000; fi"]
