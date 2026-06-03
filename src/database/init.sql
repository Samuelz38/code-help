-- =========================================================
-- init.sql - Inicialização do banco PostgreSQL + pgvector
-- Executado automaticamente pelo Docker na primeira subida
-- =========================================================

-- Extensão pgvector (já instalada na imagem ankane/pgvector)
CREATE EXTENSION IF NOT EXISTS vector;

-- Tabela principal para armazenar embeddings de código
CREATE TABLE IF NOT EXISTS code_vectors (
    id SERIAL PRIMARY KEY,
    content TEXT NOT NULL,
    embedding VECTOR(384),  -- dimensão do all-MiniLM-L6-v2
    metadata JSONB DEFAULT '{}',
    file_path TEXT,
    chunk_index INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    commit_hash VARCHAR(40)
);

-- Índice vetorial para busca por similaridade (IVFFlat para performance)
CREATE INDEX IF NOT EXISTS idx_code_vectors_embedding
ON code_vectors
USING ivfflat (embedding vector_cosine_ops)
WITH (lists = 100);

-- Índice GIN para busca em metadados JSONB
CREATE INDEX IF NOT EXISTS idx_code_vectors_metadata
ON code_vectors USING GIN (metadata);

-- Índice para busca por projeto
CREATE INDEX IF NOT EXISTS idx_code_vectors_project
ON code_vectors ((metadata->>'project'));

-- Índice para busca por commit
CREATE INDEX IF NOT EXISTS idx_code_vectors_commit
ON code_vectors (commit_hash);

-- Tabela de log de processamento (ETL audit trail)
CREATE TABLE IF NOT EXISTS etl_log (
    id SERIAL PRIMARY KEY,
    project_name VARCHAR(100) NOT NULL,
    commit_hash VARCHAR(40),
    commit_message TEXT,
    files_processed INTEGER DEFAULT 0,
    chunks_inserted INTEGER DEFAULT 0,
    chunks_deleted INTEGER DEFAULT 0,
    started_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    status VARCHAR(20) DEFAULT 'running',
    error_message TEXT
);

-- Tabela para versionamento de embeddings por commit
CREATE TABLE IF NOT EXISTS embedding_versions (
    id SERIAL PRIMARY KEY,
    project_name VARCHAR(100) NOT NULL,
    commit_hash VARCHAR(40) NOT NULL,
    commit_date TIMESTAMP,
    total_chunks INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(project_name, commit_hash)
);

-- Trigger para atualizar updated_at automaticamente
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';

DROP TRIGGER IF EXISTS update_code_vectors_updated_at ON code_vectors;
CREATE TRIGGER update_code_vectors_updated_at
    BEFORE UPDATE ON code_vectors
    FOR EACH ROW
    EXECUTE FUNCTION update_updated_at_column();
