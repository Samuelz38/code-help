import os
import json
import logging
from pathlib import Path
from typing import List, Dict
from datetime import datetime

from psycopg2.extras import execute_values

from src.database.connection import ConectToDataBase
from src.database.etl_process import EmbeddingsETLProcess

logger = logging.getLogger("index-project")

class IndexProjectTool:
    """
    Tool MCP para indexação (ingestão) de projetos no banco vetorial.
    Executa o pipeline ETL completo: load → chunk → embed → save.
    """
    
    def __init__(self, repo_path: str, project_name: str):
        self.repo_path = Path(repo_path).resolve()
        self.project_name = project_name
        self.db_host = os.getenv('DB_HOST')
        self.db_name = os.getenv('DB_NAME')
        self.db_user = os.getenv('DB_USER')
        self.db_password = os.getenv('DB_PASSWORD', os.getenv('DB_PASSW'))
        
    def run(self) -> str:
        """Executa ingestão completa e retorna relatório."""
        if not self.repo_path.exists():
            return f"❌ Repositório não encontrado: {self.repo_path}"
        
        # 1. ETL: Load
        logger.info(f"Carregando arquivos de {self.repo_path}")
        etl = EmbeddingsETLProcess(str(self.repo_path))
        docs = etl.load_data_path()
        
        if not docs:
            return f"⚠️ Nenhum arquivo de código encontrado em {self.repo_path}"
        
        # 2. ETL: Chunk
        logger.info(f"Chunking {len(docs)} documentos")
        chunks = etl.chunk_documents(docs)
        
        # 3. ETL: Embed
        logger.info("Gerando embeddings")
        vector_model = etl.generate_embedding()
        
        # 4. Preparar dados para o banco
        db_chunks = []
        for i, chunk in enumerate(chunks):
            chunk.metadata.update({
                'project': self.project_name,
                'file_path': chunk.metadata.get('source', 'unknown'),
                'chunk_index': i,
                'total_chunks': len(chunks),
                'indexed_at': datetime.now().isoformat()
            })
            db_chunks.append({
                'content': chunk.page_content,
                'metadata': chunk.metadata,
                'file_path': chunk.metadata.get('source', 'unknown'),
                'chunk_index': i
            })
        
        # 5. Salvar no banco
        inserted = self._save_to_db(db_chunks, vector_model)
        
        return (
            f"✅ Projeto indexado com sucesso!\n"
            f"📁 {self.project_name}\n"
            f"📄 Arquivos carregados: {len(docs)}\n"
            f"🧩 Chunks gerados: {len(chunks)}\n"
            f"💾 Chunks salvos: {inserted}"
        )
    
    def _save_to_db(self, chunks: List[Dict], vector_model) -> int:
        """Insere chunks no PostgreSQL/pgvector."""
        db = ConectToDataBase(self.db_host, self.db_password, self.db_name, self.db_user)
        conn = db.create_connection()
        
        try:
            data = []
            for chunk in chunks:
                embedding = vector_model.embed_query(chunk['content'])
                data.append((
                    chunk['content'],
                    embedding,
                    json.dumps(chunk['metadata']),
                    chunk['file_path'],
                    chunk['chunk_index'],
                    'manual-index'  # commit_hash para indexação manual
                ))
            
            cursor = conn.cursor()
            execute_values(cursor, """
                INSERT INTO code_vectors (content, embedding, metadata, file_path, chunk_index, commit_hash)
                VALUES %s
            """, data, template="(%s, %s::vector, %s, %s, %s, %s)")
            
            inserted = cursor.rowcount
            conn.commit()
            cursor.close()
            return inserted
            
        finally:
            conn.close()