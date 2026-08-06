import logging
import os
from datetime import datetime, timezone
from typing import List, Dict, Any, Optional

try:
    from supabase import create_client, Client
    _SUPABASE_AVAILABLE = True
except ImportError:
    _SUPABASE_AVAILABLE = False
    Client = Any

from ..config import settings
from ..security.crypto import crypto_manager

logger = logging.getLogger(__name__)

# Global client singleton
_supabase_client: Optional[Client] = None

def get_supabase() -> Optional[Client]:
    global _supabase_client
    if not _SUPABASE_AVAILABLE:
        return None
    if not settings.supabase_enabled:
        return None
    if _supabase_client is None:
        url = settings.supabase_url or os.environ.get("SUPABASE_URL")
        key = settings.supabase_key or os.environ.get("SUPABASE_KEY")
        if url and key:
            _supabase_client = create_client(url, key)
            logger.info("Supabase: Client initialized ✓")
        else:
            logger.warning("Supabase: URL or Key not found in config.")
    return _supabase_client


class SupabaseChatStore:
    def __init__(self):
        self.client = get_supabase()

    def add_message(self, role: str, content: str, conversation_id: Optional[str] = None, step_index: Optional[int] = None, tool_calls: Optional[List[Dict[str, Any]]] = None, title: Optional[str] = None):
        if not self.client:
            return
        try:
            enc_content = crypto_manager.encrypt(content)
            
            if conversation_id:
                try:
                    c_title = title or (content.strip()[:48] + "..." if len(content) > 48 else content.strip()) or "Untitled Session"
                    self.client.table("conversations").upsert({
                        "id": conversation_id,
                        "title": c_title,
                        "updated_at": datetime.now(timezone.utc).isoformat()
                    }).execute()
                except Exception as ex:
                    logger.debug(f"Conversations table upsert debug: {ex}")

            data = {"role": role, "content": enc_content}
            if conversation_id:
                data["conversation_id"] = conversation_id
            if step_index is not None:
                data["step_index"] = step_index
            if tool_calls is not None:
                data["tool_calls"] = tool_calls

            self.client.table("messages").insert(data).execute()
        except Exception as e:
            logger.error(f"SupabaseChatStore.add_message error: {e}")

    def list_conversations(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.client:
            return []
        try:
            # Try fetching from conversations table
            res = self.client.table("conversations").select("id, title, message_count, updated_at").order("updated_at", desc=True).limit(limit).execute()
            if res.data and len(res.data) > 0:
                results = []
                for row in res.data:
                    results.append({
                        "id": row.get("id"),
                        "title": row.get("title") or "Untitled Session",
                        "count": row.get("message_count") or 1
                    })
                return results

            # Fallback: query messages table grouped by conversation_id
            res_msg = self.client.table("messages").select("conversation_id, role, content, timestamp").order("id", desc=True).limit(limit * 10).execute()
            seen = {}
            for row in res_msg.data:
                cid = row.get("conversation_id") or "default"
                if cid not in seen:
                    raw_c = row.get("content", "")
                    try:
                        raw_c = crypto_manager.decrypt(raw_c)
                    except Exception:
                        pass
                    title = raw_c.strip()[:48] + "..." if len(raw_c) > 48 else raw_c.strip() or "Untitled Session"
                    seen[cid] = {"id": cid, "title": title, "count": 1}
                else:
                    seen[cid]["count"] += 1
            return list(seen.values())[:limit]
        except Exception as e:
            logger.error(f"SupabaseChatStore.list_conversations error: {e}")
            return []

    def get_conversation_messages(self, conversation_id: str) -> List[Dict[str, Any]]:
        if not self.client:
            return []
        try:
            res = self.client.table("messages").select("id, conversation_id, role, content, step_index, timestamp, tool_calls").eq("conversation_id", conversation_id).order("id", desc=False).execute()
            results = []
            for row in res.data:
                raw_c = row.get("content", "")
                try:
                    content_str = crypto_manager.decrypt(raw_c)
                except Exception:
                    content_str = raw_c
                
                results.append({
                    "step_index": row.get("step_index", 0),
                    "source": row.get("role", "user"),
                    "role": row.get("role", "user"),
                    "type": "USER_INPUT" if row.get("role") == "user" else "PLANNER_RESPONSE",
                    "content": content_str,
                    "tool_calls": row.get("tool_calls"),
                    "timestamp": row.get("timestamp")
                })
            return results
        except Exception as e:
            logger.error(f"SupabaseChatStore.get_conversation_messages error: {e}")
            return []

    def get_recent_messages(self, limit: int = 50) -> List[Dict[str, Any]]:
        if not self.client:
            return []
        try:
            res = self.client.table("messages").select("role, content, timestamp").order("id", desc=True).limit(limit).execute()
            results = []
            for row in reversed(res.data):
                d = dict(row)
                try:
                    d['content'] = crypto_manager.decrypt(d['content'])
                except Exception:
                    pass
                results.append(d)
            return results
        except Exception as e:
            logger.error(f"SupabaseChatStore.get_recent_messages error: {e}")
            return []

    def get_recent_messages_formatted(self, limit: int = 20) -> List[Dict[str, str]]:
        raw = self.get_recent_messages(limit=limit)
        formatted = []
        for msg in raw:
            role = msg["role"]
            if role == "jarvis":
                role = "assistant"
            formatted.append({"role": role, "content": msg["content"]})
        return formatted

    def clear_history(self):
        if not self.client:
            return
        try:
            self.client.table("messages").delete().neq("id", 0).execute()
            self.client.table("conversations").delete().neq("id", "0").execute()
        except Exception as e:
            logger.error(f"SupabaseChatStore.clear_history error: {e}")


class SupabaseVectorStore:
    EMBED_MODEL = "all-MiniLM-L6-v2"
    
    def __init__(self):
        self._enabled = False
        self._embedder = None
        self.client = get_supabase()

        if not self.client:
            return
            
        try:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer(self.EMBED_MODEL)
            self._enabled = True
            logger.info("SupabaseVectorStore: initialized pgvector store ✓")
        except ImportError:
            logger.warning("SupabaseVectorStore: sentence-transformers not installed.")
        except Exception as exc:
            logger.error(f"SupabaseVectorStore init failed: {exc}")

    def add(self, role: str, content: str, doc_id: Optional[str] = None) -> None:
        if not self._enabled or not self.client or not content.strip():
            return
        try:
            import uuid
            uid = doc_id or str(uuid.uuid4())
            embedding = self._embedder.encode(content).tolist()
            self.client.table("jarvis_memory").insert({
                "id": uid,
                "role": role,
                "content": content,
                "embedding": embedding
            }).execute()
        except Exception as exc:
            logger.error(f"SupabaseVectorStore.add error: {exc}")

    def search(self, query: str, n: int = 5) -> List[Dict[str, str]]:
        if not self._enabled or not self.client or not query.strip():
            return []
        try:
            embedding = self._embedder.encode(query).tolist()
            # Call the match_jarvis_memory RPC function
            res = self.client.rpc("match_jarvis_memory", {
                "query_embedding": embedding,
                "match_threshold": 0.3, # Equivalent to distance < 0.7
                "match_count": n
            }).execute()
            
            items = []
            if res.data:
                for row in res.data:
                    items.append({"role": row.get("role", "user"), "content": row.get("content")})
            return items
        except Exception as exc:
            logger.error(f"SupabaseVectorStore.search error: {exc}")
            return []

    def format_context(self, results: List[Dict[str, str]]) -> str:
        if not results:
            return ""
        lines = ["[Relevant past context retrieved from long-term memory:]"]
        for r in results:
            label = "You said" if r["role"] == "user" else "JARVIS replied"
            lines.append(f"  • {label}: {r['content'][:200]}")
        return "\n".join(lines)

    @property
    def enabled(self) -> bool:
        return self._enabled

