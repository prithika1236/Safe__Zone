import pytest
import pytest_asyncio
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.pool import StaticPool
from sqlalchemy.ext.compiler import compiles
from geoalchemy2 import Geometry
import geoalchemy2.admin
from fastapi.testclient import TestClient
from httpx import AsyncClient, ASGITransport

from geoalchemy2.functions import (
    ST_GeomFromEWKT,
    ST_GeomFromText,
    ST_AsEWKB,
    ST_AsEWKT,
    ST_AsText,
    ST_AsBinary,
    ST_AsGeoJSON,
    GenericFunction,
)

# Allow SQLite in-memory test database to compile PostGIS Geometry columns as BLOB
class SQLiteTestSpatialDialect:
    def after_create(self, table, bind, **kw): pass
    def before_drop(self, table, bind, **kw): pass
    def before_create(self, table, bind, **kw): pass
    def after_drop(self, table, bind, **kw): pass

_orig_select = geoalchemy2.admin.select_dialect
geoalchemy2.admin.select_dialect = lambda name: SQLiteTestSpatialDialect() if name == "sqlite" else _orig_select(name)

@compiles(Geometry, "sqlite")
def compile_geometry_sqlite(type_, compiler, **kw):
    return "BLOB"

@compiles(ST_GeomFromEWKT, "sqlite")
@compiles(ST_GeomFromText, "sqlite")
def compile_geom_from_text_sqlite(element, compiler, **kw):
    clauses = list(element.clauses)
    return compiler.process(clauses[0], **kw) if clauses else "NULL"

@compiles(ST_AsEWKB, "sqlite")
@compiles(ST_AsEWKT, "sqlite")
@compiles(ST_AsText, "sqlite")
@compiles(ST_AsBinary, "sqlite")
@compiles(ST_AsGeoJSON, "sqlite")
def compile_geom_as_text_sqlite(element, compiler, **kw):
    clauses = list(element.clauses)
    return compiler.process(clauses[0], **kw) if clauses else "NULL"

from app.database.base import Base
from app.database.session import get_async_db
from app.main import app as fastapi_app
import app.models  # Ensure all models are registered

# In-memory SQLite async engine with StaticPool
TEST_DATABASE_URL = "sqlite+aiosqlite:///:memory:"

test_async_engine = create_async_engine(
    TEST_DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)

TestAsyncSessionLocal = async_sessionmaker(
    bind=test_async_engine,
    autocommit=False,
    autoflush=False,
    expire_on_commit=False,
    class_=AsyncSession,
)


@pytest_asyncio.fixture(scope="session", autouse=True)
async def init_test_db():
    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_async_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture(scope="function", autouse=True)
async def clean_db_tables():
    yield
    # Clean up tables between test cases for complete isolation
    async with test_async_engine.begin() as conn:
        for table in reversed(Base.metadata.sorted_tables):
            await conn.execute(table.delete())


async def override_get_async_db() -> AsyncGenerator[AsyncSession, None]:
    async with TestAsyncSessionLocal() as session:
        try:
            yield session
        finally:
            await session.close()


fastapi_app.dependency_overrides[get_async_db] = override_get_async_db


@pytest.fixture
def client():
    return TestClient(fastapi_app)


@pytest_asyncio.fixture
async def async_client():
    transport = ASGITransport(app=fastapi_app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
