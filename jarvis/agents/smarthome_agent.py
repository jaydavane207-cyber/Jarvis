"""
SmartHomeAgent — controls Home Assistant entities via its REST API.

Requires HASS_URL and HASS_TOKEN in the environment / .env file.
Degrades gracefully when Home Assistant is not configured.

Supported domains: light, switch, climate, lock, cover, scene, input_boolean
"""
from __future__ import annotations
import re
import json
import logging
from typing import Optional, Tuple
from datetime import datetime

from ..config import settings
from ..models.ollama_client import OllamaClient
from .planner import get_jarvis_system_prompt

logger = logging.getLogger(__name__)

try:
    import requests as _req
    _REQUESTS_AVAILABLE = True
except ImportError:
    _REQUESTS_AVAILABLE = False


# ── Entity resolution maps ────────────────────────────────────────────────────

# Map common spoken names → HA entity_ids (extend as needed)
ENTITY_MAP: dict[str, str] = {
    "living room light":    "light.living_room",
    "living room":          "light.living_room",
    "bedroom light":        "light.bedroom",
    "bedroom":              "light.bedroom",
    "kitchen light":        "light.kitchen",
    "kitchen":              "light.kitchen",
    "bathroom light":       "light.bathroom",
    "office light":         "light.office",
    "all lights":           "light.all",
    "front door":           "lock.front_door",
    "back door":            "lock.back_door",
    "garage":               "cover.garage_door",
    "thermostat":           "climate.main",
    "ac":                   "climate.main",
    "air conditioning":     "climate.main",
    "fan":                  "switch.fan",
    "tv":                   "switch.tv",
    "television":           "switch.tv",
}

class SmartHomeAgent:
    """Translates natural language home commands into Home Assistant REST calls using LLM."""

    def __init__(self):
        self._hass_url   = (settings.hass_url or "").rstrip("/")
        self._hass_token = settings.hass_token or ""
        self._enabled    = bool(self._hass_url and self._hass_token and _REQUESTS_AVAILABLE)
        if self._enabled:
            logger.info(f"SmartHomeAgent: connected to {self._hass_url}")
        else:
            logger.info("SmartHomeAgent: Home Assistant not configured (graceful no-op).")

    def get_skill_context(self) -> str:
        entities = ", ".join([f"{k} ({v})" for k, v in ENTITY_MAP.items()])
        return (
            "\n\nFor this request, you are the IoT Controller agent.\n"
            "Your job:\n"
            "- Control smart home devices through approved APIs and integrations.\n"
            "- Understand natural language commands for lights, fans, AC, scenes, sensors, and routines.\n"
            "- Convert user intent into safe, exact device actions.\n"
            "- Confirm risky or irreversible actions (like unlocking doors or opening garage) before executing them.\n\n"
            "Rules:\n"
            "- Use only allowed devices and approved commands.\n"
            "- Never guess device state; query current state first when needed.\n"
            "- If a device is offline or ambiguous, report it clearly.\n"
            "- Ask for confirmation before dangerous actions. If you ask for confirmation, DO NOT execute the action yet.\n"
            "- Log every action with timestamp, device, and result.\n"
            "- If a command is incomplete, ask one short clarifying question.\n"
            "- Output style: Clear, short, and action-oriented. Mention what changed, what failed, and what remains pending.\n\n"
            "AVAILABLE ENTITIES:\n"
            f"{entities}\n\n"
            "To query a device state, output ONLY this exact JSON format and nothing else:\n"
            "{\"tool\": \"query_state\", \"entity_id\": \"<entity_id>\"}\n\n"
            "To execute an action, output ONLY this exact JSON format and nothing else:\n"
            "{\"tool\": \"execute_action\", \"domain\": \"<domain>\", \"service\": \"<service>\", \"entity_id\": \"<entity_id>\"}\n\n"
            "If you do not need to use a tool, just reply normally to the user."
        )

    async def handle_stream(self, message: str, llm: OllamaClient, history: list, semantic: str = "", voice_mode: str = "calm_male"):
        """Conversational ReAct loop using JSON tool calls for IoT Control."""
        logger.info("SmartHomeAgent building prompt")
        semantic_block = f"\n\n{semantic}" if semantic else ""
        system = get_jarvis_system_prompt(voice_mode) + semantic_block + self.get_skill_context()
        
        messages = [{"role": "system", "content": system}] + history + [{"role": "user", "content": message}]
        
        # Max 5 internal tool iterations
        for i in range(5):
            response_text = llm.chat(messages)
            
            # Try parsing as JSON tool call using regex
            tool_call = None
            # Find JSON-like object {"tool": ...}
            match = re.search(r'(\{[\s\S]*?"tool"[\s\S]*?\})', response_text)
            if match:
                try:
                    tool_call = json.loads(match.group(1))
                except json.JSONDecodeError:
                    pass

            if tool_call and "tool" in tool_call:
                tool_name = tool_call["tool"]
                
                if tool_name == "query_state":
                    entity_id = tool_call.get("entity_id")
                    state = self._query_hass(entity_id)
                    messages.append({"role": "assistant", "content": response_text})
                    messages.append({"role": "user", "content": f"Tool Result: {state}"})
                    continue
                    
                elif tool_name == "execute_action":
                    domain = tool_call.get("domain")
                    service = tool_call.get("service")
                    entity_id = tool_call.get("entity_id")
                    success, error = self._call_hass(domain, service, entity_id)
                    
                    # Log the action
                    self._log_action(tool_call, success, error)
                    
                    res = "Success" if success else f"Error: {error}"
                    messages.append({"role": "assistant", "content": response_text})
                    messages.append({"role": "user", "content": f"Tool Result: {res}"})
                    continue
            
            # If no valid tool call, yield final conversational text
            yield response_text
            return

        yield "I'm sorry, I had trouble processing that device command."

    def handle(self, message: str) -> str:
        """Legacy synchronous handler for fallback."""
        return "The IoT Controller mode requires the async streaming interface."

    # ── HA REST API ───────────────────────────────────────────────────────────

    def _query_hass(self, entity_id: str) -> str:
        if not self._enabled:
            return "Simulation Mode: Device state is OFF (Home Assistant not configured)."
        url = f"{self._hass_url}/api/states/{entity_id}"
        headers = {
            "Authorization": f"Bearer {self._hass_token}",
            "Content-Type": "application/json",
        }
        try:
            resp = _req.get(url, headers=headers, timeout=5)
            if resp.status_code == 200:
                data = resp.json()
                # Exclude noisy attributes for the LLM
                state = data.get('state', 'unknown')
                friendly_name = data.get('attributes', {}).get('friendly_name', entity_id)
                return f"State for {friendly_name}: {state}"
            elif resp.status_code == 404:
                return f"Entity {entity_id} not found."
            return f"Error HTTP {resp.status_code}: {resp.text[:100]}"
        except Exception as exc:
            return f"Error querying state: {str(exc)}"

    def _call_hass(
        self,
        domain: str,
        service: str,
        entity_id: str,
        extra: Optional[dict] = None,
    ) -> Tuple[bool, str]:
        """POST to Home Assistant services endpoint."""
        if not self._enabled:
            return True, "Simulated success (Home Assistant not configured)."
            
        url = f"{self._hass_url}/api/services/{domain}/{service}"
        headers = {
            "Authorization": f"Bearer {self._hass_token}",
            "Content-Type": "application/json",
        }
        body = extra or {"entity_id": entity_id}
        try:
            resp = _req.post(url, json=body, headers=headers, timeout=10)
            if resp.status_code in (200, 201):
                return True, ""
            return False, f"HTTP {resp.status_code}: {resp.text[:100]}"
        except Exception as exc:
            return False, str(exc)

    def _log_action(self, tool_call: dict, success: bool, error: str):
        timestamp = datetime.now().isoformat()
        entity_id = tool_call.get('entity_id', 'unknown')
        action = f"{tool_call.get('domain')}.{tool_call.get('service')}"
        result = "Success" if success else f"Failed ({error})"
        log_msg = f"IoT Action Log - [{timestamp}] Device: {entity_id} | Action: {action} | Result: {result}"
        logger.info(log_msg)
        # We could also append to an explicit log file if needed, but logging to standard logger is good.
