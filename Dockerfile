FROM python:3.11-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    HEADLESS=true \
    SLOW_MO=0

WORKDIR /app

# Instalar dependências Python e o Chromium do Playwright (com todas as libs de sistema)
COPY requirements.txt .
RUN pip install -r requirements.txt \
 && playwright install chromium --with-deps \
 && rm -rf /var/lib/apt/lists/*

COPY app/ ./app/

# data/ é montado como volume em tempo de execução — não é copiado para a imagem
VOLUME ["/app/data"]

CMD ["python", "-m", "app.main"]
