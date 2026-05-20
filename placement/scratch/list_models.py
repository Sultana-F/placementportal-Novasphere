import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv('GEMINI_API_KEY'))

print("Available Models:")
try:
    for m in client.models.list():
        print(f" - {m}")
except Exception as e:
    print(f"Error listing models: {e}")
