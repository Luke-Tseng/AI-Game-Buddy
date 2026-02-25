# Use Python 3.10 for compatibility
FROM python:3.10-slim-bookworm

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_SYSTEM_PYTHON=1

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Create non-root user
RUN adduser --uid 5678 --disabled-password --gecos "" --no-create-home appuser

# Set working directory
WORKDIR /app

# Copy dependency files first (better layer caching)
COPY --chown=appuser:appuser pyproject.toml uv.lock* ./

# Install dependencies using uv
RUN uv pip install --no-cache -r pyproject.toml

# Copy application code
COPY --chown=appuser:appuser backend/ .

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Run application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]