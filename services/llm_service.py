
import os
from google import genai


def ask_llm(prompt):
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        return "AI reasoning not available: GEMINI_API_KEY is missing"

    try:
        client = genai.Client(api_key=api_key)

        response = client.models.generate_content(
            model="gemini-3.8-flash",
            contents=prompt,
        )

        return response.text or "AI reasoning not available"

    except Exception as e:
        print("GEMINI ERROR:", str(e))
        return "AI reasoning not available"
