import os

from src.database.connection import ConectToDataBase

class ProjectInfoTool:
    def __init__(self, name: str, path: str):
        self.name = name
        self.path = path
        self.DB_HOST = os.getenv('DB_HOST')
        self.DB_NAME = os.getenv('DB_NAME')
        self.DB_USER = os.getenv('DB_USER')
        self.DB_PASSW = os.getenv('DB_PASSW')
        db = ConectToDataBase(self.DB_HOST, self.DB_PASSW, self.DB_NAME, self.DB_USER)
        self.conn = db.create_connection()

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
                """, (self.name,))

                total, last_commit, last_update = cur.fetchone()

            self.conn.close()

            return (
                f"📊 Estatísticas do projeto: {self.name}\n"
                f"   Total de chunks: {total}\n"
                f"   Último commit: {last_commit or 'N/A'}\n"
                f"   Última atualização: {last_update or 'N/A'}"
            )

        except Exception as e:
            return f"Erro: {str(e)}"