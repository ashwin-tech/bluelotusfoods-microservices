from contextlib import contextmanager
import psycopg2
from psycopg2 import pool
from app.core.settings import settings

db_pool = None

def init_db_pool():
    global db_pool
    if db_pool is None:
        db_pool = pool.SimpleConnectionPool(
            minconn=1,
            maxconn=10,
            dbname=settings.db_name,
            user=settings.db_user,
            password=settings.db_password,
            host=settings.db_host,
            port=settings.db_port
        )
    return db_pool

def close_db_pool():
    global db_pool
    if db_pool:
        db_pool.closeall()
        db_pool = None

def get_connection():
    return db_pool.getconn()

def release_connection(conn):
    db_pool.putconn(conn)

@contextmanager
def get_conn():
    conn = db_pool.getconn()
    # Validate connection — replace if stale (e.g. after Cloud Run idle period)
    if conn.closed != 0:
        db_pool.putconn(conn, close=True)
        conn = db_pool.getconn()
    else:
        try:
            conn.cursor().execute("SELECT 1")
            conn.rollback()
        except psycopg2.Error:
            db_pool.putconn(conn, close=True)
            conn = db_pool.getconn()
    try:
        yield conn
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
        raise
    finally:
        db_pool.putconn(conn)
