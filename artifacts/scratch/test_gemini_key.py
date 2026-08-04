import os
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv(".env.dev")
api_key = os.getenv("GEMINI_API_KEY")

genai.configure(api_key=api_key)

for model_name in ["gemini-2.0-flash", "gemini-2.5-flash", "gemini-flash-latest"]:
    try:
        model = genai.GenerativeModel(model_name)
        response = model.generate_content("Hello, reply with 'Gemini is working'")
        print(f"Success with {model_name}: {response.text.strip()}")
        break
    except Exception as e:
        print(f"Error with {model_name}: {type(e).__name__} - {e}")
