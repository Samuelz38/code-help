import os

from src.database.connection import ConectToDataBase
from src.database.etl_process import EmbeddingsETLProcess

from src.utils.system_operations_functions import get_path_root

class SearchDB:
    def __init__(self, query: str, project_name: str = None, limit: int = 5):
        self.query = query
        self.project_name = project_name
        self.limit = limit
        self.DB_HOST = os.getenv('DB_HOST')
        self.DB_NAME = os.getenv('DB_NAME')
        self.DB_USER = os.getenv('DB_USER')
        self.DB_PASSW = os.getenv('DB_PASSW')
        self.path_root = get_path_root()
        db = ConectToDataBase(self.DB_HOST, self.DB_PASSW, self.DB_NAME, self.DB_USER)
        self.conn = db.create_connection()

    def _execute(self):

        try:

            embeddings = EmbeddingsETLProcess(self.path_root)

            vector_model = embeddings.generate_embedding()
            vector = vector_model.embed_query(self.query)

            # CORREÇÃO DO BUG: parâmetros na ordem correta do SQL
            if self.project_name:
                sql = """
                    SELECT content, metadata, 1 - (embedding <=> %s::vector) AS similarity
                    FROM code_vectors
                    WHERE metadata->>'project' = %s
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s;
                """
                params = (vector, self.project_name, vector, self.limit)
            else:
                sql = """
                    SELECT content, metadata, 1 - (embedding <=> %s::vector) AS similarity
                    FROM code_vectors
                    ORDER BY embedding <=> %s::vector
                    LIMIT %s;
                """
                params = (vector, vector, self.limit)

            results_txt = []

            with self.conn.cursor() as cur:
                cur.execute(sql, params)
                rows = cur.fetchall()

                for content, metadata, sim in rows:
                    src = metadata.get('source', 'unknown')
                    results_txt.append(
                        f'FILE: {src}\n'
                        f'SIMILARITY: {sim:.4f}\n'
                        f'CODE_BLOCK: {content}\n'
                        + '-' * 60
                    )

            self.conn.close()
            return '\n'.join(results_txt) if results_txt else 'Nenhum resultado encontrado.'

        except Exception as e:
            return f"Erro na busca vetorial: {str(e)}"


    def get_project_stats(self):
        """
        Retorna estatísticas de um projeto indexado (total de chunks, último commit, etc).
        """
        try:

            with self.conn.cursor() as cur:
                cur.execute("""
                    SELECT COUNT(*), 
                        MAX(metadata->>'commit_hash') as last_commit,
                        MAX(created_at) as last_update
                    FROM code_vectors
                    WHERE metadata->>'project' = %s
                """, (self.project_name,))

                total, last_commit, last_update = cur.fetchone()

            self.conn.close()

            return (
                f"📊 Estatísticas do projeto: {self.project_name}\n"
                f"   Total de chunks: {total}\n"
                f"   Último commit: {last_commit or 'N/A'}\n"
                f"   Última atualização: {last_update or 'N/A'}"
            )

        except Exception as e:
            return f"Erro: {str(e)}"
