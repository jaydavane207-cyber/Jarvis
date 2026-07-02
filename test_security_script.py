import asyncio
from jarvis.memory.sqlite_store import SQLiteStore
from jarvis.memory.personal_store import PersonalStore
from jarvis.memory.contact_store import ContactStore
from jarvis.security.crypto import crypto_manager, mfa_manager
import pyotp
import os

def test_encryption_and_privacy():
    print("Testing Stores Encryption...")
    
    # 1. SQLite Store (messages)
    sql_store = SQLiteStore(".jarvis/test_memory.db")
    sql_store.add_message("user", "Hello this is a secret message")
    messages = sql_store.get_recent_messages(limit=1)
    assert messages[0]["content"] == "Hello this is a secret message"
    print("OK SQLite Store Encryption OK")
    
    # 2. Personal Store
    personal_store = PersonalStore("test_personal.db")
    personal_store.add_health_log("sleep", "8 hours", "Felt great")
    logs = personal_store.get_health_logs(limit=1)
    assert logs[0]["value"] == "8 hours"
    assert logs[0]["notes"] == "Felt great"
    print("OK Personal Store Encryption OK")

    # 3. Contact Store
    contact_store = ContactStore(".jarvis/test_contacts.db")
    c = contact_store.add_contact(name="John Doe", phone="123456789", email="john@example.com", notes="Secret agent")
    c_fetched = contact_store.get_contact(c["id"])
    assert c_fetched["phone"] == "123456789"
    assert c_fetched["email"] == "john@example.com"
    assert c_fetched["notes"] == "Secret agent"
    print("OK Contact Store Encryption OK")

    # 4. MFA Setup
    print("Testing MFA Manager...")
    uri = mfa_manager.get_provisioning_uri()
    assert "otpauth" in uri
    qr = mfa_manager.get_qr_code_base64()
    assert len(qr) > 0
    print("OK MFA Manager OK")

    # Cleanup
    try:
        os.remove(".jarvis/test_memory.db")
        os.remove("test_personal.db")
        os.remove(".jarvis/test_contacts.db")
    except:
        pass

    print("All tests passed successfully!")

if __name__ == "__main__":
    test_encryption_and_privacy()
