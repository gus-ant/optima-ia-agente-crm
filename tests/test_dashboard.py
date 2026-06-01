"""
tests/test_dashboard.py
-----------------------
Testes para os endpoints do Dashboard.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api.main import app


@pytest.fixture
def client():
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
