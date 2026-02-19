import os
from dotenv import load_dotenv

load_dotenv()

key = os.getenv("OPENAI_API_KEY", "")
print("Key loaded:", "YES" if key.startswith("sk-") else "NO")
print("Key length:", len(key))
