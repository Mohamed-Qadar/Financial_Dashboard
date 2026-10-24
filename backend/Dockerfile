FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install dependencies first so code changes do not invalidate this layer.
# Use REQUIREMENTS=requirements/base.txt for production images.
ARG REQUIREMENTS=requirements/dev.txt
COPY requirements/ requirements/
RUN pip install -r ${REQUIREMENTS}

RUN useradd --create-home --uid 1000 app
COPY --chown=app:app . .
USER app

EXPOSE 8000

# Production-style default; docker-compose.yml overrides this for development.
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3"]
