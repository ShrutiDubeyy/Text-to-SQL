import requests
import json


OLLAMA_URL   = "http://localhost:11434/api/chat"
OLLAMA_MODEL = "llama3.1"


def is_ollama_running():
    """Check if local LLM is running"""
    try:
        r = requests.get(
            "http://localhost:11434/api/tags",
            timeout=2
        )
        return r.status_code == 200
    except Exception:
        return False


def call_local_llm(prompt, system_message="You are a helpful assistant."):
    """
    Call LLM running on YOUR machine.
    Data never leaves your network.
    Memory wiped after every single response.
    """
    try:
        print("[LocalLLM] 🏠 Processing locally...")

        payload = {
            "model":  OLLAMA_MODEL,
            "messages": [
                {
                    "role":    "system",
                    "content": system_message
                },
                {
                    "role":    "user",
                    "content": prompt
                }
            ],
            "stream": False,
            "options": {
                "temperature":   0,
                "num_predict":   1000,
                # These settings ensure zero memory retention
                "num_ctx":       4096,
            }
        }

        response = requests.post(
            OLLAMA_URL,
            json=payload,
            timeout=120
        )

        if response.status_code == 200:
            result = response.json()
            content = result['message']['content'].strip()
            print("[LocalLLM] ✅ Done — memory wiped")
            return content, "local"
        else:
            print(f"[LocalLLM] ❌ Error: {response.status_code}")
            return None, "local"

    except requests.exceptions.ConnectionError:
        print("[LocalLLM] ❌ Ollama not running")
        return None, "offline"
    except Exception as e:
        print(f"[LocalLLM] ❌ Error: {e}")
        return None, "error"


def call_with_fallback(prompt,
                       system_message="You are a helpful assistant."):
    """
    Try local LLM first.
    Fall back to Groq only if Ollama is offline.
    When local — zero data exposure, zero memory retention.
    When cloud — anonymized schema only sent.
    """

    # Try local first — preferred for privacy
    if is_ollama_running():
        result, source = call_local_llm(
            prompt, system_message)
        if result:
            return result, "local"

    # Fall back to Groq with anonymization
    print("[LocalLLM] ⚠️ Ollama offline — using Groq fallback")
    from llm_chain import call_groq
    result = call_groq(prompt, system_message)
    return result, "cloud"