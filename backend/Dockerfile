FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements/base.txt requirements/base.txt
RUN pip install --default-timeout=120 --no-cache-dir -r requirements/base.txt

COPY requirements/knowledge.txt requirements/knowledge.txt
RUN pip install --default-timeout=120 --no-cache-dir -r requirements/knowledge.txt

COPY . .

EXPOSE 8000
