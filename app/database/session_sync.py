from sqlalchemy import create_engine
from sqlalchemy.orm  import Session,sessionmaker

from app.config import db_settings

engine = create_engine(
    url=db_settings.SYNC_DB_URL,
    pool_pre_ping=True,pool_size=5,
    max_overflow=10,
    
)

sessionLocal = sessionmaker(
    bind=engine,expire_on_commit=False,class_=Session
)

def get_sync_session():
    return sessionLocal()