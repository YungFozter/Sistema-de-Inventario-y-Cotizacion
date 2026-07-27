import os
import urllib.parse
import sqlite3

def get_db_connection(timeout=30):
    database_url = os.environ.get('DATABASE_URL')
    if database_url and database_url.startswith('postgres'):
        import psycopg2
        from psycopg2.extras import DictCursor
        return PostgresConnectionWrapper(database_url)
    else:
        # Fallback a sqlite3
        conn = sqlite3.connect('database/db.sqlite3', timeout=timeout)
        conn.row_factory = sqlite3.Row
        return conn

class PostgresConnectionWrapper:
    def __init__(self, url):
        import psycopg2
        self.conn = psycopg2.connect(url)
        from psycopg2.extras import DictCursor
        self.cursor_factory = DictCursor

    @property
    def row_factory(self):
        return None

    @row_factory.setter
    def row_factory(self, value):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if exc_type:
            self.rollback()
        else:
            self.commit()
        self.close()

    def cursor(self):
        return PostgresCursorWrapper(self.conn.cursor(cursor_factory=self.cursor_factory))

    def commit(self):
        self.conn.commit()

    def rollback(self):
        self.conn.rollback()

    def close(self):
        self.conn.close()

class PostgresCursorWrapper:
    def __init__(self, cursor):
        self._cursor = cursor
        self.lastrowid = None
        self.rowcount = -1

    def execute(self, query, params=None):
        # Reemplazar ? por %s de manera segura
        if params is not None:
            query = query.replace('?', '%s')
        
        # Ejecutar
        if params is not None:
            self._cursor.execute(query, params)
        else:
            self._cursor.execute(query)
            
        self.rowcount = self._cursor.rowcount
        
        # Para lastrowid, necesitamos capturarlo si la query tiene RETURNING id
        if "RETURNING id" in query.upper():
            try:
                res = self._cursor.fetchone()
                if res:
                    self.lastrowid = res[0]
            except Exception as e:
                pass
        return self

    def fetchone(self):
        return self._cursor.fetchone()

    def fetchall(self):
        return self._cursor.fetchall()

    @property
    def description(self):
        return self._cursor.description
