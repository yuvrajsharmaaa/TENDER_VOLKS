import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv(".env.dev")
api_key = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=api_key)

try:
    print("Listing available models...")
    for m in genai.list_models():
        if 'generateContent' in m.supported_generation_methods:
            print("Model name:", m.name)
except Exception as e:
    print("Error listing models:", type(e).__name__, "-", e)
