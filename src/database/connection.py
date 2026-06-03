import psycopg2
from pgvector.psycopg2 import register_vector


class ConectToDataBase:
    def __init__(self, host, password, db_name, user):
        self.user = user
        self.password = password
        self.host = host
        self.db_name = db_name

    def create_connection(self):
        conn = psycopg2.connect(
            host=self.host,
            dbname=self.db_name,
            user=self.user,
            password=self.password,
        )

        register_vector(conn)
        return conn
