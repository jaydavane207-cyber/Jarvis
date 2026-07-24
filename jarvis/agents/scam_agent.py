"""
ScamAgent — fraud and scam detection agent for JARVIS.

Capabilities:
  1. Text/message analysis — detect phishing, social engineering, UPI fraud
  2. Image analysis via ImageAgent — screenshot of suspicious emails
  3. Real-time link/QR scanning — checks URL reputation before tapping
  4. Learning Pattern Library — confirmed scams fed back as labeled embeddings
     in a dedicated ChromaDB collection ('scam_patterns') so detection improves
     over time

Powered by:
  • LLM reasoning (pattern matching + context understanding)
  • PhishTank / VirusTotal API (optional, if VIRUSTOTAL_API_KEY is set)
  • Local scam_patterns ChromaDB collection for semantic similarity search
"""
from __future__ import annotations
import logging
import os
import re
from typing import Optional, Dict, Any

from ..models.ollama_client import OllamaClient
from .planner import get_jarvis_system_prompt
from ..safety.audit_log import audit_log
from ..config import settings

logger = logging.getLogger(__name__)

try:
    import requests as _req
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False

try:
    import chromadb
    from chromadb.config import Settings as ChromaSettings
    from sentence_transformers import SentenceTransformer
    _CHROMA_AVAILABLE = True
except ImportError:
    _CHROMA_AVAILABLE = False

SKILL_CONTEXT = (
    "\n\nFor this request, you are in SCAM DETECTION MODE. "
    "Analyse the provided message, link, or screenshot for signs of fraud. "
    "Check for:\n"
    "1. Phishing indicators (fake domains, urgent language, threat/reward pressure)\n"
    "2. UPI / payment fraud patterns\n"
    "3. KYC / OTP social engineering\n"
    "4. Job / investment scams common in India\n"
    "5. Suspicious links or QR codes\n\n"
    "Be direct: say 'SCAM', 'SUSPICIOUS', or 'LIKELY LEGITIMATE' at the top. "
    "Explain your reasoning clearly. Recommend action to Jay."
)


class ScamAgent:
    """Multi-modal fraud and scam detection agent."""

    _EMBED_MODEL = "all-MiniLM-L6-v2"
    _CHROMA_DIR = ".jarvis/scam_patterns"

    def __init__(self):
        self._vt_key: Optional[str] = getattr(settings, "virustotal_api_key", None)
        self._pattern_db = self._init_pattern_db()

    # ── Pattern library init ───────────────────────────────────────────────────

    def _init_pattern_db(self):
        """Initialise ChromaDB collection for scam pattern library."""
        if not _CHROMA_AVAILABLE:
            return None
        try:
            os.makedirs(self._CHROMA_DIR, exist_ok=True)
            client = chromadb.PersistentClient(
                path=self._CHROMA_DIR,
                settings=ChromaSettings(anonymized_telemetry=False),
            )
            collection = client.get_or_create_collection(
                name="scam_patterns",
                metadata={"hnsw:space": "cosine"},
            )
            logger.info(
                f"ScamAgent: pattern library ready ({collection.count()} patterns)"
            )
            return collection
        except Exception as exc:
            logger.error(f"ScamAgent._init_pattern_db error: {exc}")
            return None

    # ── Public API ─────────────────────────────────────────────────────────────

    async def handle_stream(
        self,
        message: str,
        llm: OllamaClient,
        history: list,
        semantic: str = "",
        voice_mode: str = "calm_male",
        file_content: Optional[str] = None,
    ):
        """Handle scam detection query."""
        logger.info("ScamAgent handling query")

        # Check for URL/link in message
        url = self._extract_url(message)
        url_report = ""
        if url:
            url_report = await self._check_url(url)

        # Semantic similarity to known scam patterns
        pattern_match = self._search_patterns(message)

        context = self._build_context(message, url, url_report, pattern_match, file_content)
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + SKILL_CONTEXT

        messages = (
            [{"role": "system", "content": system}]
            + history
            + [{"role": "user", "content": context}]
        )

        audit_log.record(
            agent="ScamAgent",
            action_type="scam_detection",
            details=f"Query: {message[:100]} | URL: {url or 'none'}",
            reasoning="User requested scam/fraud analysis",
            tier="read_only",
            approved=0,
        )

        async for chunk in llm.chat_stream(messages):
            yield chunk

    def handle(
        self,
        message: str,
        llm: OllamaClient,
        history: list,
        semantic: str = "",
        voice_mode: str = "calm_male",
        file_content: Optional[str] = None,
    ) -> str:
        import asyncio
        url = self._extract_url(message)
        url_report = ""
        pattern_match = self._search_patterns(message)
        context = self._build_context(message, url, url_report, pattern_match, file_content)
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + SKILL_CONTEXT
        messages = (
            [{"role": "system", "content": system}]
            + history
            + [{"role": "user", "content": context}]
        )
        return llm.chat(messages)

    def add_confirmed_scam(self, text: str, scam_type: str = "general") -> str:
        """
        Feed a confirmed scam back into the pattern library.
        Improves future detection via semantic similarity.
        """
        if not _CHROMA_AVAILABLE or self._pattern_db is None:
            return "Pattern library unavailable — chromadb not installed."
        try:
            import uuid
            embedder = SentenceTransformer(self._EMBED_MODEL)
            embedding = embedder.encode(text).tolist()
            self._pattern_db.upsert(
                documents=[text],
                embeddings=[embedding],
                metadatas=[{"scam_type": scam_type}],
                ids=[str(uuid.uuid4())],
            )
            logger.info(f"ScamAgent: pattern added | type={scam_type}")
            return f"✅ Scam pattern added to library (type: {scam_type}). Detection improved."
        except Exception as exc:
            logger.error(f"ScamAgent.add_confirmed_scam error: {exc}")
            return f"❌ Failed to add pattern: {exc}"

    # ── Link/URL checking ──────────────────────────────────────────────────────

    async def _check_url(self, url: str) -> str:
        """Check URL reputation via VirusTotal or basic heuristics."""
        # Basic heuristic checks first (no API needed)
        heuristics = self._heuristic_url_check(url)
        if heuristics:
            return heuristics

        # VirusTotal API (if key available)
        if self._vt_key and _REQUESTS_AVAILABLE:
            return self._virustotal_check(url)

        return f"URL noted: {url} — no external reputation check available (VirusTotal API key not set)."

    def _heuristic_url_check(self, url: str) -> Optional[str]:
        """Basic heuristic checks for suspicious URLs."""
        suspicious_patterns = [
            (r"bit\.ly|tinyurl|t\.co|goo\.gl|rb\.gy", "Shortened URL — destination unknown"),
            (r"\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}", "Raw IP address instead of domain name — highly suspicious"),
            (r"paypal|paytm|upi|bank|kyc|verify|account|secure|update", "Contains financial/identity keywords"),
            (r"\.xyz|\.top|\.buzz|\.click|\.tk", "Unusual TLD commonly used in phishing"),
            (r"login|signin|confirm|verify|validate", "Contains action-urgency keywords"),
        ]
        flags = []
        url_lower = url.lower()
        for pattern, reason in suspicious_patterns:
            if re.search(pattern, url_lower):
                flags.append(reason)
        if flags:
            return f"⚠️ URL Heuristic Flags:\n" + "\n".join(f"  • {f}" for f in flags)
        return None

    def _virustotal_check(self, url: str) -> str:
        """Check URL against VirusTotal API."""
        try:
            import base64
            url_id = base64.urlsafe_b64encode(url.encode()).rstrip(b"=").decode()
            resp = _req.get(
                f"https://www.virustotal.com/api/v3/urls/{url_id}",
                headers={"x-apikey": self._vt_key},
                timeout=10,
            )
            if resp.status_code == 200:
                stats = resp.json().get("data", {}).get("attributes", {}).get("last_analysis_stats", {})
                malicious = stats.get("malicious", 0)
                suspicious = stats.get("suspicious", 0)
                if malicious > 0:
                    return f"🚨 VirusTotal: {malicious} engines flagged as MALICIOUS"
                elif suspicious > 0:
                    return f"⚠️ VirusTotal: {suspicious} engines flagged as suspicious"
                return "✅ VirusTotal: No threats detected"
            return f"VirusTotal check returned status {resp.status_code}"
        except Exception as exc:
            return f"VirusTotal check failed: {exc}"

    # ── Pattern search ─────────────────────────────────────────────────────────

    def _search_patterns(self, message: str) -> str:
        """Semantic search against known scam patterns."""
        if not _CHROMA_AVAILABLE or self._pattern_db is None:
            return ""
        try:
            count = self._pattern_db.count()
            if count == 0:
                return ""
            embedder = SentenceTransformer(self._EMBED_MODEL)
            embedding = embedder.encode(message).tolist()
            results = self._pattern_db.query(
                query_embeddings=[embedding],
                n_results=min(3, count),
                include=["documents", "metadatas", "distances"],
            )
            docs = results.get("documents", [[]])[0]
            dists = results.get("distances", [[]])[0]
            metas = results.get("metadatas", [[]])[0]
            matches = []
            for doc, dist, meta in zip(docs, dists, metas):
                if dist < 0.4:  # high similarity threshold for scam patterns
                    matches.append(
                        f"⚠️ Similar to known {meta.get('scam_type', 'scam')} pattern: {doc[:100]}"
                    )
            return "\n".join(matches) if matches else ""
        except Exception as exc:
            logger.error(f"ScamAgent._search_patterns error: {exc}")
            return ""

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _extract_url(message: str) -> Optional[str]:
        match = re.search(r"https?://\S+", message)
        return match.group(0) if match else None

    def _build_context(
        self,
        message: str,
        url: Optional[str],
        url_report: str,
        pattern_match: str,
        file_content: Optional[str],
    ) -> str:
        lines = [f"User query: {message}\n"]
        if url_report:
            lines.append(f"URL Reputation Report:\n{url_report}\n")
        if pattern_match:
            lines.append(f"Pattern Library Match:\n{pattern_match}\n")
        if file_content:
            lines.append(f"Screenshot/Document Content:\n{file_content[:3000]}\n")
        lines.append("Please analyse this for scam/fraud indicators.")
        return "\n".join(lines)
