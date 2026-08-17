import os
import sys
import urllib.request
import json

api_key = os.getenv("LLM_API_KEY")
print("LLM_API_KEY length:", len(api_key) if api_key else "None")
print("LLM_PROVIDER:", os.getenv("LLM_PROVIDER"))

base_url = "https://api.groq.com/openai/v1/chat/completions"
payload = {
    "model": "llama-3.3-70b-versatile",
    "messages": [
        {"role": "system", "content": "Test JSON system prompt"},
        {"role": "user", "content": "Test prompt"}
    ],
    "temperature": 0.1,
    "response_format": {"type": "json_object"}
}

req = urllib.request.Request(
    base_url,
    data=json.dumps(payload).encode("utf-8"),
    headers={
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    },
    method="POST"
)

try:
    with urllib.request.urlopen(req) as res:
        print("Success:", res.read().decode("utf-8"))
except Exception as e:
    print("Error:", e)
    if hasattr(e, "read"):
        print("Response body:", e.read().decode("utf-8"))
