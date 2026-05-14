FROM ghcr.io/astral-sh/uv:0.11.6-python3.12-trixie
ENV DOCKER=true \
    PATH="/app/.venv/bin:$PATH" \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    cmake \
    make \
    libolm-dev \
    librocksdb-dev \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

RUN uv sync --no-dev

EXPOSE 8000
RUN mkdir -p /app/data

CMD ["uv", "run", "--no-dev", "python", "-m", "src.mxuserbot"]
