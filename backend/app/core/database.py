import os
from sqlmodel import SQLModel, create_engine, Session
from app.core.config import settings

# Đảm bảo thư mục chứa file SQLite tồn tại
db_dir = os.path.dirname(settings.DATABASE_URL.replace("sqlite:///", ""))
if db_dir and not os.path.exists(db_dir):
    os.makedirs(db_dir, exist_ok=True)

from sqlalchemy import event

connect_args = {
    "check_same_thread": False,
    "timeout": 30.0,
} if "sqlite" in settings.DATABASE_URL else {}

engine = create_engine(
    settings.DATABASE_URL,
    echo=False,
    connect_args=connect_args,
    pool_pre_ping=True,
)

if "sqlite" in settings.DATABASE_URL:
    @event.listens_for(engine, "connect")
    def set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL;")
        cursor.execute("PRAGMA synchronous=NORMAL;")
        cursor.execute("PRAGMA busy_timeout=30000;")
        cursor.close()


def init_db():
    SQLModel.metadata.create_all(engine)



def get_session():
    with Session(engine) as session:
        yield session
