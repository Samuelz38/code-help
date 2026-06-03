FROM python:3.11-slim

WORKDIR /app

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    git \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements para container Linux
COPY requirements.docker.txt /app/requirements.docker.txt
RUN pip install --no-cache-dir -r /app/requirements.docker.txt

# Copia código do projeto
COPY src /app/src
COPY .env /app/.env
COPY ./reprocess.py /app/reprocess.py
COPY ./mcp_server.py /app/mcp_server.py
COPY ./mcp_server_filesystem.py /app/mcp_server_filesystem.py
COPY ./configs.json /app/configs.json

# Cria diretório de logs
RUN mkdir -p /app/logs

ENV PYTHONUNBUFFERED=1
ENV PYTHONPATH=/app

CMD ["python", "/app/reprocess.py"]
