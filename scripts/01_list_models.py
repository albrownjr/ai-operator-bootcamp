from pathlib import Path

from dotenv import load_dotenv
from openai import OpenAI

ROOT = Path(__file__).resolve().parents[1]
env_path = ROOT / ".env"
load_dotenv(env_path)

print("Loaded .env from:", env_path)

client = OpenAI()

try:
    models = client.models.list()
    print("Number of models returned:", len(models.data))

    for m in models.data[:25]:
        print(m.id)

except Exception as e:
    print("ERROR calling models.list():")
    print(repr(e))
