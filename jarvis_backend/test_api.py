from fastapi.testclient import TestClient
from src.main import app
import pytest

client = TestClient(app)

def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_security_status():
    response = client.get("/security/status")
    assert response.status_code == 200
    assert "quantum_crypto" in response.json()

def test_quantum_keys():
    response = client.post("/api/v1/auth/quantum-keys")
    assert response.status_code == 200
    assert "public_key_hex" in response.json()

def test_digital_twin():
    response = client.post(
        "/api/v1/auth/digital-twin",
        json={"user_id": "test_user_123", "twin_type": "Test"}
    )
    assert response.status_code == 200
    assert "digital_twin_id" in response.json()

def test_summarize_notes():
    response = client.post(
        "/api/v1/study/summarize-notes",
        json={"content": "This is a test note for summarization.", "user_id": 1}
    )
    assert response.status_code == 200
    assert "summary" in response.json()

def test_swarm_spawn():
    response = client.post(
        "/api/v1/agents/swarm/spawn",
        json={"objective": "Write a test suite", "roles": ["QA Engineer", "Developer"]}
    )
    assert response.status_code == 200
    assert "swarm_id" in response.json()

def test_upi_shield():
    response = client.post(
        "/api/v1/india/upi/shield",
        json={
            "transaction_id": "TXN987654",
            "amount": 500.0,
            "is_new_payee": False,
            "payee_vpa": "test@upi"
        }
    )
    assert response.status_code == 200
    assert "risk_score" in response.json()

def test_audit_log():
    response = client.post(
        "/api/v1/enterprise/audit/log",
        json={
            "action": "SYSTEM_TEST",
            "data_payload": {"test": True}
        }
    )
    assert response.status_code == 200
    assert "tx_hash" in response.json()
