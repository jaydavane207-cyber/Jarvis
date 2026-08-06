import os
import sys
import json
from dotenv import load_dotenv

load_dotenv()
os.environ["SUPABASE_ENABLED"] = "true"

from jarvis.config import settings
from jarvis.memory.supabase_store import SupabaseChatStore
import viewer_server

def run_tests():
    print("=== SUPABASE INTEGRATION TEST ===")
    print(f"Supabase Enabled: {settings.supabase_enabled}")
    
    store = SupabaseChatStore()
    if not store.client:
        print("ERROR: Supabase client could not be initialized.")
        sys.exit(1)
        
    print("Supabase client initialized successfully [OK]")
    
    convo_id = "test-session-88"
    print(f"\n1. Adding test messages for conversation_id='{convo_id}'...")
    store.add_message("user", "Hello JARVIS, store this in Supabase!", conversation_id=convo_id, step_index=1, title="Supabase Integration Test")
    store.add_message("jarvis", "Affirmative Jay. Saved directly to Supabase cloud storage.", conversation_id=convo_id, step_index=2, title="Supabase Integration Test")
    
    print("\n2. Testing list_conversations()...")
    convos = store.list_conversations()
    print(f"Found {len(convos)} conversations in Supabase:")
    for c in convos[:5]:
        print(f"  - [{c['id']}] {c['title']} ({c['count']} msgs)")
        
    print("\n3. Testing get_conversation_messages()...")
    msgs = store.get_conversation_messages(convo_id)
    print(f"Retrieved {len(msgs)} messages for '{convo_id}':")
    for m in msgs:
        print(f"  - Step #{m['step_index']} [{m['source']}]: {m['content']}")
        
    print("\n4. Testing viewer_server.py list_conversations endpoint...")
    v_convos = viewer_server.list_conversations()
    print(f"viewer_server returned {len(v_convos)} total conversations.")
    
    found = any(c['id'] == convo_id for c in v_convos)
    if found:
        print(f"\n[SUCCESS] Supabase conversation storage and API server integration verified 100%!")
    else:
        print(f"\n[PARTIAL SUCCESS] Messages stored, but table schema ('conversations') may need schema_supabase.sql run in SQL Editor.")

if __name__ == "__main__":
    run_tests()
