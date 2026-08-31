import os
import json
import urllib.request
from dotenv import load_dotenv

load_dotenv(".env.dev")

api_key = os.getenv("GROQ_API_KEY")
url = "https://api.groq.com/openai/v1/chat/completions"
headers = {
    "Content-Type": "application/json",
    "Authorization": f"Bearer {api_key}",
    "User-Agent": "TenderVolks/1.0"
}
payload = {
    "model": "llama-3.3-70b-versatile",
    "messages": [
        {"role": "system", "content": "You are a helpful assistant. Output valid JSON."},
        {"role": "user", "content": "Ping test. Return a json object with status=ok and model name."}
    ],
    "temperature": 0.1,
    "response_format": {"type": "json_object"}
}

req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
try:
    with urllib.request.urlopen(req, timeout=15) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        print("GROQ API SUCCESS!")
        print("Response:", res["choices"][0]["message"]["content"])
except Exception as e:
    print("GROQ API FAILED:", e)
