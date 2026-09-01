FROM python:3.12-slim

RUN pip install --no-cache-dir uv

WORKDIR /app

# 依存関係のみ先に解決してレイヤーキャッシュを効かせる
COPY pyproject.toml ./
RUN uv sync --no-install-project --no-dev

COPY src/ ./src/

ENV PATH="/app/.venv/bin:${PATH}"

EXPOSE 8000

# src/config.py は .dockerignore で除外されているため、実行時にボリュームマウントすること
CMD ["python", "src/server.py"]
