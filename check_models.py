# check_models.py
import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))

print("Embedding-capable models available to your key:\n")
for model in client.models.list():
    if "embed" in model.name.lower():
        print(f"  {model.name}")