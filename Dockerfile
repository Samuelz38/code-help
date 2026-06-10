FROM python:3.11-slim

WORKDIR /app

# Instala dependências do sistema
RUN apt-get update && apt-get install -y \
    git \
    libpq-dev \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copia requirements e instala dependências Python
COPY requirements.docker.txt .
RUN pip install --no-cache-dir -r requirements.docker.txt

# Pré-baixa o modelo de embeddings durante o build
# Isso evita download em runtime e garante que o modelo esteja no container
RUN python -c "from sentence_transformers import SentenceTransformer; SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')"

# Copia o código da aplicação
COPY . .

# Variáveis de ambiente padrão
ENV PYTHONUNBUFFERED=1
ENV HF_HUB_CACHE=/app/.cache/huggingface

CMD ["python", "reprocess.py"]