def build_prompt(name: str, vehicle: str, stage: str, tone: str) -> str:
    return f"""
Return ONLY valid JSON (no markdown, no extra text).

Fields required:
- customer_name (string)
- vehicle (string)
- stage (string)
- tone (string)
- recommended_next_action (one of: text, text_then_call, call_then_text_summary, text_update_then_offer_alternatives)
- sms (string, 2-3 sentences, ends with a yes/no question, sign -Andre)
- email_subject (string)
- email_body (string, 4-7 sentences, professional, 1 clear CTA, sign Andre)
- voicemail (string, 15-25 seconds, callback ask, sign Andre)

Context:
customer_name="{name}"
vehicle="{vehicle}"
stage="{stage}"
tone="{tone}"

Rules:
- Human, concise, clear
- No pressure, no gimmicks
- Avoid promising pricing/availability unless explicitly confirmed
- Choose recommended_next_action based on stage:
  - no appointment -> text_then_call
  - numbers sent -> call_then_text_summary
  - waiting on inventory -> text_update_then_offer_alternatives
  - otherwise -> text
""".strip()

import json
import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

def is_online() -> bool:
    return os.getenv("ONLINE", "0").strip().lower() in ("1", "true", "yes")

def model_name() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-5.2-codex").strip()

def next_action(stage: str) -> str:
    s = stage.lower()
    if "no appointment" in s:
        return "text_then_call"
    if "numbers" in s:
        return "call_then_text_summary"
    if "waiting" in s or "inventory" in s:
        return "text_update_then_offer_alternatives"
    return "text"

def mock_json(name: str, vehicle: str, stage: str, tone: str) -> dict:
    return {
        "customer_name": name,
        "vehicle": vehicle,
        "stage": stage,
        "tone": tone,
        "recommended_next_action": next_action(stage),
        "sms": f"Hey {name} — quick check-in on the {vehicle}. Want to set a time today or tomorrow to go over it? -Andre",
        "email_subject": f"Quick follow-up on the {vehicle}",
        "email_body": (
            f"Hi {name},\n\n"
            f"Just following up on the {vehicle}. If you're still interested, I can confirm next steps and answer any questions.\n"
            f"What day/time works best for a quick call or visit?\n\n"
            f"Thanks,\nAndre"
        ),
        "voicemail": (
            f"Hey {name}, this is Andre. Just following up on the {vehicle}. "
            f"If you'd like, I can confirm details and set a quick time to come by. "
            f"Call me back when you can — thanks, Andre."
        )
    }

def main():
    print("Follow-ups generator V2 (JSON)")
    online = is_online()
    model = model_name()

    name = input("Customer name: ").strip()
    vehicle = input("Vehicle of interest: ").strip()
    stage = input("Stage (new lead / no appointment / numbers sent / waiting on inventory): ").strip()
    tone = input("Tone (friendly/professional/urgent-calm): ").strip() or "professional"

    if not online:
        data = mock_json(name, vehicle, stage, tone)
        print("\n--- OUTPUT (OFFLINE JSON) ---\n")
        print(json.dumps(data, indent=2))
        return

    # Online mode: ask model to return strict JSON
    prompt = f"""
Return ONLY valid JSON (no markdown, no extra text).

Fields required:
- customer_name (string)
- vehicle (string)
- stage (string)
- tone (string)
- recommended_next_action (one of: text, text_then_call, call_then_text_summary, text_update_then_offer_alternatives)
- sms (string, 2-3 sentences, ends with a yes/no question, sign -Andre)
- email_subject (string)
- email_body (string, 4-7 sentences, professional, 1 clear CTA, sign Andre)
- voicemail (string, 15-25 seconds, callback ask, sign Andre)

Context:
customer_name="{name}"
vehicle="{vehicle}"
stage="{stage}"
tone="{tone}"

Rules:
- Human, concise, clear
- No pressure, no gimmicks
- Avoid promising pricing/availability unless explicitly confirmed
- Choose recommended_next_action based on stage:
  - no appointment -> text_then_call
  - numbers sent -> call_then_text_summary
  - waiting on inventory -> text_update_then_offer_alternatives
  - otherwise -> text
""".strip()

    try:
        from openai import OpenAI
        client = OpenAI()

        resp = client.responses.create(
            model=model,
            input=prompt
        )

        raw = (resp.output_text or "").strip()
        data = json.loads(raw)  # strict parse

        print("\n--- OUTPUT (LIVE JSON) ---\n")
        print(json.dumps(data, indent=2))

    except Exception as e:
        print("\n--- ONLINE MODE FAILED, FALLING BACK TO OFFLINE ---\n")
        print("Error:", repr(e))
        data = mock_json(name, vehicle, stage, tone)
        print(json.dumps(data, indent=2))

if __name__ == "__main__":
   main()
