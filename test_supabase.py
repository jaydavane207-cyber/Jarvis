import os
import sys
from dotenv import load_dotenv

# Load env variables for local testing
load_dotenv()

# Set config envs before importing jarvis modules
os.environ["SUPABASE_ENABLED"] = "true"

from jarvis.config import settings
from jarvis.memory.supabase_store import SupabaseChatStore, SupabaseVectorStore

def test_supabase_stores():
    print(f"Supabase Enabled in Settings: {settings.supabase_enabled}")
    
    # 1. Test Chat Store
    print("\n--- Testing Chat Store ---")
    chat_store = SupabaseChatStore()
    
    print("Adding a test message...")
    chat_store.add_message("user", "Hello Supabase, this is a test message!")
    
    print("Retrieving recent messages...")
    messages = chat_store.get_recent_messages(limit=5)
    found = False
    for msg in messages:
        print(f"[{msg.get('role')}]: {msg.get('content')}")
        if msg.get("content") == "Hello Supabase, this is a test message!":
            found = True
            
    if found:
        print("[SUCCESS] Chat Store: Insert and retrieve working perfectly.")
    else:
        print("[FAILED] Chat Store: Failed to retrieve the test message.")

    # 2. Test Vector Store
    print("\n--- Testing Vector Store ---")
    vector_store = SupabaseVectorStore()
    
    if not vector_store.enabled:
        print("[FAILED] Vector Store is not enabled (maybe sentence-transformers is missing).")
        return
        
    print("Adding a test embedding...")
    test_content = "The secret code is 42 and it unlocks the mainframe."
    vector_store.add("user", test_content)
    
    print("Searching for similar context...")
    results = vector_store.search("What is the secret code?", n=1)
    
    if results:
        print(f"Found best match: [{results[0]['role']}] {results[0]['content']}")
        if results[0]['content'] == test_content:
            print("[SUCCESS] Vector Store: PGVector insert and similarity search working perfectly.")
        else:
            print("[FAILED] Vector Store: Retrieved incorrect vector match.")
    else:
        print("[FAILED] Vector Store: Failed to find any matching vectors.")

if __name__ == "__main__":
    test_supabase_stores()
