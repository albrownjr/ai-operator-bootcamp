import json
import os
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from pydantic import BaseModel

from scripts.ai_followups_v2_json import mock_json, build_prompt

# Load .env from project root
ROOT = Path(__file__).resolve().parent
load_dotenv(ROOT / ".env")

app = FastAPI(title="AI Follow-Up Service", version="0.1.0")


class LeadInput(BaseModel):
    name: str
    vehicle: str
    stage: str
    tone: str = "professional"


def is_online() -> bool:
    return os.getenv("ONLINE", "0").strip().lower() in ("1", "true", "yes")


def model_name() -> str:
    return os.getenv("OPENAI_MODEL", "gpt-5.2-codex").strip()


@app.get("/")
def home():
    return {
        "status": "AI Follow-Up Service Running",
        "docs": "http://127.0.0.1:8000/docs",
        "health": "http://127.0.0.1:8000/health",
        "generate": "POST http://127.0.0.1:8000/generate",
    }


@app.get("/health")
def health():
    return {"ok": True, "online": is_online(), "model": model_name()}


@app.post("/generate")
def generate_followups(data: LeadInput):
    # OFFLINE MODE (default)
    if not is_online():
        return mock_json(
            name=data.name,
            vehicle=data.vehicle,
            stage=data.stage,
            tone=data.tone,
        )

    # ONLINE MODE
    try:
        from openai import OpenAI

        client = OpenAI()
        prompt = build_prompt(data.name, data.vehicle, data.stage, data.tone)

        resp = client.responses.create(
            model=model_name(),
            input=prompt,
        )

        raw = (resp.output_text or "").strip()

        # Expecting strict JSON (per build_prompt rules)
        return json.loads(raw)

    except Exception as e:
        # If quota/billing fails or JSON parsing fails, fall back safely
        return {
            "error": str(e),
            "fallback": mock_json(
                name=data.name,
                vehicle=data.vehicle,
                stage=data.stage,
                tone=data.tone,
            ),
        }