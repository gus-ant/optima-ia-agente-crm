"""
tests/test_dashboard.py
-----------------------
Testes para os endpoints do Dashboard.
"""

import os
# Configura o ambiente para usar SQLite em memória antes de qualquer import do DB
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
os.environ["ENVIRONMENT"] = "development"

import pytest
from fastapi.testclient import TestClient

from api.main import app
from crm.database import Base, engine


@pytest.fixture(autouse=True)
async def setup_db():
    """Inicializa as tabelas no SQLite em memória antes de cada teste."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


@pytest.fixture
def client(setup_db):
    with TestClient(app) as c:
        yield c


def test_dashboard_index_serving(client):
    """Verifica se o root serve o arquivo index.html corretamente."""
    response = client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Óptima IA — Lara CRM Dashboard" in response.text


def test_dashboard_stats_endpoint(client):
    """Verifica o endpoint de estatísticas do dashboard."""
    response = client.get("/api/dashboard/stats")
    assert response.status_code == 200
    data = response.json()
    assert "total_contacts" in data
    assert "total_deals" in data
    assert "total_appointments" in data
    assert "stages" in data
    assert "NOVO" in data["stages"]


def test_dashboard_leads_endpoint(client):
    """Verifica se o endpoint de listagem de leads retorna 200."""
    response = client.get("/api/dashboard/leads")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


def test_dashboard_appointments_endpoint(client):
    """Verifica o endpoint de agendamentos."""
    response = client.get("/api/dashboard/appointments")
    assert response.status_code == 200
    assert isinstance(response.json(), list)
