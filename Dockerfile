FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 TZ=Europe/Madrid
RUN apt-get update && apt-get install -y --no-install-recommends tzdata \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot.py config.yaml ./
COPY ofertas ./ofertas

VOLUME /app/datos
CMD ["python", "bot.py"]
