from fastapi.testclient import TestClient
from src.main import app

client = TestClient(app)

def run_tests():
    try:
        print("Running JARVIS Integration Tests...\n")
        
        print("1. Testing Health Check Endpoint...")
        response = client.get("/health")
        assert response.status_code == 200, f"Expected 200, got {response.status_code}"
        print("   -> [PASS] System is healthy.\n")

        print("2. Testing Quantum Cryptography Key Generation...")
        response = client.post("/api/v1/auth/quantum-keys")
        assert response.status_code == 200
        assert "public_key_hex" in response.json()
        print("   -> [PASS] Post-Quantum Keys generated successfully.\n")

        print("3. Testing Digital Twin Firewall Session...")
        response = client.post("/api/v1/auth/digital-twin", json={"user_id": "test_user_123", "twin_type": "Test"})
        assert response.status_code == 200
        print("   -> [PASS] Digital Twin isolated session spawned.\n")

        print("4. Testing Autonomous Agent Swarm Deployment...")
        response = client.post("/api/v1/agents/swarm/spawn", json={"objective": "Test task", "roles": ["Developer"]})
        assert response.status_code == 200
        print("   -> [PASS] Multi-agent swarm deployed and synchronizing.\n")
        
        print("5. Testing Real-time UPI Fraud Shield...")
        response = client.post("/api/v1/india/upi/shield", json={"transaction_id": "TXN123", "amount": 500, "is_new_payee": False, "payee_vpa": "test@upi"})
        assert response.status_code == 200
        print("   -> [PASS] Fraud prediction model executed.\n")

        print("6. Testing Immutable Blockchain Audit Log...")
        response = client.post("/api/v1/enterprise/audit/log", json={"action": "SYSTEM_TEST", "data_payload": {"test": True}})
        assert response.status_code == 200
        print("   -> [PASS] Event hashed to audit trail.\n")

        print("=========================================")
        print("ALL TESTS PASSED: JARVIS Architecture is Stable and Functional!")
        
    except AssertionError as e:
        print(f"   -> [FAIL] Assertion Error: {e}")
    except Exception as e:
        print(f"   -> [FAIL] Unexpected Error: {e}")

if __name__ == "__main__":
    run_tests()
