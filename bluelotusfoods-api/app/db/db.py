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
