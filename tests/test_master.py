import os
# Configura o ambiente para usar SQLite em memória antes de qualquer import do DB
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient

from api.main import app
from crm.database import Base, engine

MASTER_KEY = "optima_master_secret_key"
HEADERS = {"X-Master-Key": MASTER_KEY}

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

def test_master_stats(client):
    # Test without auth
    response = client.get("/api/master/stats")
    assert response.status_code == 422 or response.status_code == 403

    # Test with invalid auth
    response = client.get("/api/master/stats", headers={"X-Master-Key": "wrong"})
    assert response.status_code == 403

    # Test with valid auth
    response = client.get("/api/master/stats", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert "total_tenants" in data
    assert "active_tenants" in data

def test_master_tenants_crud(client):
    # Create tenant
    payload = {
        "slug": "test-slug-master",
        "name": "Test Master",
        "plan": "pro",
        "is_active": True
    }
    response = client.post("/api/master/tenants", json=payload, headers=HEADERS)
    assert response.status_code == 200
    tenant = response.json()
    assert tenant["slug"] == "test-slug-master"
    tenant_id = tenant["id"]

    # List tenants
    response = client.get("/api/master/tenants", headers=HEADERS)
    assert response.status_code == 200
    tenants = response.json()
    assert any(t["id"] == tenant_id for t in tenants)

    # Update tenant
    update_payload = {"name": "Test Master Updated", "is_active": False}
    response = client.patch(f"/api/master/tenants/{tenant_id}", json=update_payload, headers=HEADERS)
    assert response.status_code == 200

    # Get Agent Config
    response = client.get(f"/api/master/tenants/{tenant_id}/agent-config", headers=HEADERS)
    assert response.status_code == 200
    config = response.json()
    assert "llm_model" in config

    # Update Agent Config
    config_payload = {"llm_model": "gpt-4"}
    response = client.patch(f"/api/master/tenants/{tenant_id}/agent-config", json=config_payload, headers=HEADERS)
    assert response.status_code == 200
    
    # Get again to check
    response = client.get(f"/api/master/tenants/{tenant_id}/agent-config", headers=HEADERS)
    config = response.json()
    assert config["llm_model"] == "gpt-4"

def test_master_agents_summary(client):
    # Create a tenant first
    payload = {
        "slug": "test-agent-summary",
        "name": "Test Agent Summary",
        "plan": "pro"
    }
    client.post("/api/master/tenants", json=payload, headers=HEADERS)
    
    # Get agents summary
    response = client.get("/api/master/agents-summary", headers=HEADERS)
    assert response.status_code == 200
    agents = response.json()
    assert len(agents) > 0
    assert any(a["tenant_name"] == "Test Agent Summary" for a in agents)

def test_master_analytics_usage(client):
    response = client.get("/api/master/analytics/usage", headers=HEADERS)
    assert response.status_code == 200
    data = response.json()
    assert "avg_latency" in data
    assert "conversion_rate" in data
    assert "usage_ranking" in data

def test_master_settings_change_key(client):
    # Change key
    new_key = "brand_new_secret_key"
    response = client.post("/api/master/settings/change-key", json={"new_key": new_key}, headers=HEADERS)
    assert response.status_code == 200
    
    # Try calling endpoint with old key (should fail)
    response = client.get("/api/master/stats", headers=HEADERS)
    assert response.status_code == 403
    
    # Try calling endpoint with new key (should pass)
    response = client.get("/api/master/stats", headers={"X-Master-Key": new_key})
    assert response.status_code == 200
    
    # Restore key for subsequent tests
    client.post("/api/master/settings/change-key", json={"new_key": MASTER_KEY}, headers={"X-Master-Key": new_key})
