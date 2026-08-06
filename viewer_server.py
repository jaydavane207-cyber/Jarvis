import os
import json
from fastapi import FastAPI
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

# Allow CORS if needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BRAIN_DIR = r"C:\Users\JAY\.gemini\antigravity\brain"

def extract_title(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    parsed = json.loads(line)
                    source = parsed.get("source")
                    type_ = parsed.get("type")
                    content = parsed.get("content")
                    if (source == 'USER_EXPLICIT' or type_ == 'USER_INPUT') and content:
                        text = content.strip()
                        if text.startswith('<USER_REQUEST>'):
                            # Basic extraction
                            import re
                            match = re.search(r'<USER_REQUEST>([\s\S]*?)</USER_REQUEST>', text)
                            if match:
                                text = match.group(1).strip()
                        return text[:50] + "..." if len(text) > 50 else text
                except json.JSONDecodeError:
                    continue
    except Exception:
        pass
    return "Untitled Conversation"

def count_lines(filepath):
    try:
        with open(filepath, 'r', encoding='utf-8') as f:
            return sum(1 for line in f if line.strip())
    except:
        return 0

@app.get("/", response_class=HTMLResponse)
def serve_viewer():
    html_path = "conversation_viewer.html"
    try:
        with open(html_path, "r", encoding="utf-8") as f:
            return f.read()
    except FileNotFoundError:
        return "conversation_viewer.html not found in current directory."

try:
    from jarvis.memory.supabase_store import SupabaseChatStore
    supabase_store = SupabaseChatStore()
except Exception:
    supabase_store = None

@app.get("/api/conversations")
def list_conversations():
    conversations = []

    # 1. Try pulling sessions from Supabase
    if supabase_store and supabase_store.client:
        try:
            supa_convos = supabase_store.list_conversations()
            if supa_convos:
                conversations.extend(supa_convos)
        except Exception as e:
            pass

    # 2. Add/Fallback local disk conversations
    if os.path.exists(BRAIN_DIR):
        existing_ids = {c["id"] for c in conversations}
        for item in os.listdir(BRAIN_DIR):
            if item in existing_ids:
                continue
            convo_dir = os.path.join(BRAIN_DIR, item)
            if os.path.isdir(convo_dir):
                logs_dir = os.path.join(convo_dir, ".system_generated", "logs")
                if not os.path.exists(logs_dir):
                    logs_dir = convo_dir

                transcript_path = os.path.join(logs_dir, "transcript.jsonl")
                if not os.path.exists(transcript_path):
                    transcript_path = os.path.join(logs_dir, "transcript_full.jsonl")

                if os.path.exists(transcript_path):
                    title = extract_title(transcript_path)
                    count = count_lines(transcript_path)
                    conversations.append({
                        "id": item,
                        "title": title,
                        "count": count
                    })
    
    # Sort by line count descending
    conversations.sort(key=lambda x: x.get("count", 0), reverse=True)
    return conversations

@app.get("/api/conversations/{convo_id}", response_class=PlainTextResponse)
def get_conversation(convo_id: str):
    # 1. Check Supabase first
    if supabase_store and supabase_store.client:
        try:
            msgs = supabase_store.get_conversation_messages(convo_id)
            if msgs:
                lines = [json.dumps(m) for m in msgs]
                return "\n".join(lines)
        except Exception as e:
            pass

    # 2. Fallback to local disk file
    convo_dir = os.path.join(BRAIN_DIR, convo_id)
    if not os.path.exists(convo_dir):
        return "Conversation not found."

    logs_dir = os.path.join(convo_dir, ".system_generated", "logs")
    if not os.path.exists(logs_dir):
        logs_dir = convo_dir

    transcript_path = os.path.join(logs_dir, "transcript_full.jsonl")
    if not os.path.exists(transcript_path):
         transcript_path = os.path.join(logs_dir, "transcript.jsonl")
    
    if not os.path.exists(transcript_path):
        return "Transcript not found."
    
    try:
        with open(transcript_path, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        return str(e)

if __name__ == "__main__":
    uvicorn.run("viewer_server:app", host="127.0.0.1", port=8080, reload=True)
