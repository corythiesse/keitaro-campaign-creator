# ruff: noqa: E402
import atexit
import os
import shutil
import sys
import tempfile
from pathlib import Path

# Configure the app before importing it: settings are read once at import time.
_TEST_DB_DIR = tempfile.mkdtemp(prefix="keitaro-tests-")
TEST_DB_PATH = Path(_TEST_DB_DIR) / "test.db"
atexit.register(shutil.rmtree, _TEST_DB_DIR, ignore_errors=True)
os.environ["KEITARO_BASE_URL"] = "https://keitaro.test"
os.environ["KEITARO_API_KEY"] = "test-key"
os.environ["KEITARO_TIMEOUT"] = "5"
os.environ["KEITARO_DOMAIN_NAME"] = "example.com"
os.environ["KEITARO_GROUP_NAME"] = "FORTESTS"
os.environ["KEITARO_TRAFFIC_SOURCE_NAME"] = "FORTESTS"
os.environ["KEITARO_STREAM_ACTION_TYPE"] = "http"
os.environ["KEITARO_OFFERS_CACHE_TTL"] = "0"
os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB_PATH}"
os.environ["CORS_ORIGINS"] = "http://localhost:5173"
os.environ["CAMPAIGN_NAME_PREFIX"] = "test_"
os.environ["API_AUTH_TOKEN"] = ""

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import httpx
import pytest
import pytest_asyncio

from app import main as main_module
from app.database import Base, SessionLocal, engine
from app.main import app

KEITARO = "https://keitaro.test/admin_api/v1"


@pytest_asyncio.fixture(autouse=True)
async def clean_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest_asyncio.fixture
async def session():
    async with SessionLocal() as db:
        yield db


@pytest_asyncio.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as test_client:
        yield test_client


@pytest.fixture
def main_app():
    return main_module


def mock_keitaro_context(respx_mock, *, offer_id: int = 42, campaign_id: int = 123):
    """Register the GET endpoints required by create_campaign()."""
    respx_mock.get(f"{KEITARO}/offers/{offer_id}").mock(
        return_value=httpx.Response(200, json={"id": offer_id, "name": "Offer A", "state": "active"})
    )
    respx_mock.get(f"{KEITARO}/domains").mock(
        return_value=httpx.Response(200, json=[{"id": 5, "name": "example.com"}])
    )
    respx_mock.get(f"{KEITARO}/groups").mock(
        return_value=httpx.Response(200, json=[{"id": 7, "name": "FORTESTS"}])
    )
    respx_mock.get(f"{KEITARO}/traffic_sources").mock(
        return_value=httpx.Response(200, json=[{"id": 8, "name": "FORTESTS"}])
    )
    respx_mock.get(f"{KEITARO}/streams_actions").mock(
        return_value=httpx.Response(200, json=[{"key": "http"}, {"key": "blank"}])
    )
    respx_mock.post(f"{KEITARO}/campaigns").mock(
        return_value=httpx.Response(200, json={"id": campaign_id})
    )
