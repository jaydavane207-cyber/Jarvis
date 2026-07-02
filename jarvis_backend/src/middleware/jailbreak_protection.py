import logging
from fastapi import Request, HTTPException
from typing import Callable

class AIJailbreakProtection:
    """
    Middleware and utility class to detect adversarial prompts, role-playing tricks,
    and prompt injection attacks using heuristic and simulated AI logic.
    """
    
    # Simple heuristics for immediate flagging
    SUSPICIOUS_KEYWORDS = [
        "ignore previous instructions",
        "system prompt",
        "you are now",
        "act as a",
        "jailbreak",
        "bypass",
        "override"
    ]

    def analyze_intent(self, text: str) -> float:
        """
        Analyzes text and returns a risk score between 0.0 (safe) and 1.0 (malicious).
        In production, this would pass through an ensemble of 7 specialized small LLMs.
        """
        text_lower = text.lower()
        score = 0.0
        
        for keyword in self.SUSPICIOUS_KEYWORDS:
            if keyword in text_lower:
                score += 0.3
                
        # Simulate transformer-based semantic anomaly detection
        if len(text) > 1000 and "forget" in text_lower:
            score += 0.4
            
        return min(score, 1.0)

    async def middleware(self, request: Request, call_next: Callable):
        """
        FastAPI middleware to intercept requests and scan payloads for jailbreaks.
        """
        # Only scan POST/PUT requests that might contain prompts
        if request.method in ["POST", "PUT"]:
            # Need to consume body carefully in FastAPI middleware
            # This is a simplified approach. In prod, use request.stream() safely.
            body = await request.body()
            body_text = body.decode('utf-8', errors='ignore')
            
            if body_text:
                risk_score = self.analyze_intent(body_text)
                if risk_score > 0.8:
                    logging.critical(f"JAILBREAK ATTEMPT DETECTED! Risk Score: {risk_score}")
                    raise HTTPException(
                        status_code=403, 
                        detail="Constitutional AI Violation: Request blocked by Intent Analysis Engine."
                    )
        
        response = await call_next(request)
        return response

jailbreak_protector = AIJailbreakProtection()
