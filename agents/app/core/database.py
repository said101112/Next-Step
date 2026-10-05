# ============================================================
# app/core/database.py — SQLAlchemy async
# ============================================================
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

# PostgreSQL schema owned by the agents. Profiles, applications and coaching sessions belong to
# backend modules: the agents reach them only through the backend (app.core.backend_client),
# and the backend saves the interview coach's sessions itself.
AGENTS_SCHEMA = "agents"

def get_engine():
    # Convertir l'URL postgres:// en postgresql+asyncpg://
    url = settings.DATABASE_URL.replace(
        "postgresql://", "postgresql+asyncpg://"
    ).replace(
        "postgres://", "postgresql+asyncpg://"
    )
    return create_async_engine(
        url,
        echo=False,          # True pour voir les requêtes SQL dans les logs
        pool_size=5,
        max_overflow=10,
        pool_pre_ping=True,  # Vérifie si la connexion est active avant de l'utiliser
        pool_recycle=3600,   # Recycle les connexions après 1 heure
    )

engine = get_engine()

AsyncSessionFactory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

class Base(DeclarativeBase):
    """Base commune pour tous les modèles SQLAlchemy."""
    pass

async def get_db() -> AsyncSession:  # type: ignore[override]
    """
    Dependency FastAPI — injecte une session DB dans les routes.
    Usage dans router.py :
        async def my_route(db: AsyncSession = Depends(get_db)):
    """
    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
