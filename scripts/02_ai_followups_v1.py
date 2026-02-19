import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (bulletproof)
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

def is_online() -> bool:
    return os.getenv("ONLINE", "0").strip() in ("1", "true", "TRUE", "yes", "YES")

def model_name() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-5.2-codex").strip()

def mock_followups(name: str, vehicle: str, stage: str, tone: str) -> str:
    # You can improve these anytime. The point is: pipeline works without API quota.
    return f"""SMS:
Hey {name} — quick check-in on the {vehicle}. Want to set a time today or tomorrow to take a look? -Andre

EMAIL:
Subject: Quick follow-up on the {vehicle}
Body: Hi {name}, just following up on the {vehicle}. If you’re still interested, I can confirm availability and have it ready. What day/time works best for a quick call or visit? Thanks, Andre

VOICEMAIL:
Hey {name}, this is Andre. Just following up on the {vehicle}. If you’d like, I can confirm availability and set a quick time for you to stop by. Call me back when you can — thanks, Andre.
"""

def build_prompt(name: str, vehicle: str, stage: str, tone: str) -> str:
    return f"""
Create 3 follow-ups for a car sales lead. Use the info below.

Customer: {name}
Vehicle: {vehicle}
Stage: {stage}
Tone: {tone}

Rules:
- Human, concise, clear
- No pressure, no gimmicks
- Avoid promising pricing/availability unless explicitly confirmed
- End SMS with a yes/no question

Output exactly in this format:

SMS:
<2-3 sentences, end with a yes/no question, sign -Andre>

EMAIL:
Subject: <short subject>
Body: <4-7 sentences, professional, 1 clear CTA, sign Andre>

VOICEMAIL:
<15-25 seconds spoken script, includes callback ask, sign Andre>
""".strip()

def main():
    online = is_online()
    model = model_name()

    print("Starting follow-up generator...")
    print("ONLINE mode:", online)
    print("Model:", model)

    name = input("Customer name: ").strip()
    vehicle = input("Vehicle of interest: ").strip()
    stage = input("Stage (new lead / no appointment / numbers sent / waiting on inventory): ").strip()
    tone = input("Tone (friendly/professional/urgent-calm): ").strip() or "professional"

    prompt = build_prompt(name, vehicle, stage, tone)

    if not online:
        print("\n--- AI FOLLOW-UPS (OFFLINE MOCK) ---\n")
        print(mock_followups(name, vehicle, stage, tone))
        print("\nTip: Set ONLINE=1 in .env to use OpenAI when billing/quota is enabled.\n")
        return

    # Online mode
    try:
        from openai import OpenAI
        client = OpenAI()

        print("\nCalling OpenAI...\n")
        resp = client.responses.create(
            model=model,
            input=prompt
        )

        print("\n--- AI FOLLOW-UPS (LIVE) ---\n")
        print(resp.output_text)

    except Exception as e:
        print("\n--- ONLINE MODE FAILED ---")
        print("Falling back to OFFLINE mock.\n")
        print("Error:", repr(e))
        print("\n--- AI FOLLOW-UPS (OFFLINE MOCK) ---\n")
        print(mock_followups(name, vehicle, stage, tone))

if __name__ == "__main__":
    main()
