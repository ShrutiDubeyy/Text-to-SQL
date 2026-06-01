from groq import Groq
from dotenv import load_dotenv
import os
import time
import json

load_dotenv()

client = Groq(api_key=os.getenv("GROQ_API_KEY"))

MODELS_TO_TRY = [
    "llama-3.3-70b-versatile",
    "llama-3.1-8b-instant",
    "gemma2-9b-it",
]


def call_groq(prompt, system_message="You are a helpful assistant."):
    for model in MODELS_TO_TRY:
        for attempt in range(3):
            try:
                print(f"[LLM] Model: {model} attempt {attempt + 1}")
                response = client.chat.completions.create(
                    model=model,
                    messages=[
                        {"role": "system", "content": system_message},
                        {"role": "user",   "content": prompt}
                    ],
                    temperature=0,
                    max_tokens=1000,
                )
                result = response.choices[0].message.content.strip()
                print(f"[LLM] Success: {model}")
                return result

            except Exception as e:
                error = str(e)
                if "429" in error or "rate_limit" in error.lower():
                    wait = 10 * (attempt + 1)
                    print(f"[LLM] Rate limited. Waiting {wait}s...")
                    time.sleep(wait)
                elif "503" in error or "unavailable" in error.lower():
                    print(f"[LLM] {model} unavailable. Trying next...")
                    break
                elif "model_not_found" in error.lower() or "404" in error:
                    print(f"[LLM] {model} not found. Trying next...")
                    break
                else:
                    print(f"[LLM] Unexpected error: {error}")
                    raise e

    raise Exception("All models failed. Check your Groq API key.")


def _format_history(chat_history):
    """Format chat history for LLM prompt"""
    if not chat_history:
        return "No previous conversation."

    lines = []
    for msg in chat_history[-6:]:
        role = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role}: {msg['content'][:200]}")

    return "\n".join(lines)


def process_question_complete(user_question, schema,
                               chat_history=None):
    from local_llm import (call_with_fallback,
                            is_ollama_running)
    from data_shield import shield
    from rag_engine import rag

    history_str = _format_history(chat_history or [])

    # ── RAG: Find similar past queries ───────────────
    similar = rag.find_similar(user_question, top_k=3)
    rag_context = rag.format_examples_for_prompt(
        similar)

    print(f"[RAG] Found {len(similar)} "
          f"similar examples")

    if is_ollama_running():
        safe_schema = schema
    else:
        safe_schema = shield.anonymize_schema(schema)

    prompt = f"""You are an expert AI data analyst.

Database schema:
{safe_schema}

{rag_context}

Previous conversation:
{history_str}

User message: "{user_question}"

Respond with ONLY a JSON object:
{{
    "intent": "DATA_QUESTION or CASUAL_CHAT or HELP_REQUEST or SCHEMA_REQUEST or OUT_OF_SCOPE",
    "sql": "SELECT query or null",
    "casual_response": "response or null",
    "followups": ["q1", "q2", "q3"]
}}

Use the similar past queries as reference
for SQL style and patterns.
Return ONLY JSON:"""

    result, source = call_with_fallback(prompt)

    del prompt
    del safe_schema
    import gc
    gc.collect()

    if not result:
        return {
            "intent":          "DATA_QUESTION",
            "sql":             None,
            "casual_response": None,
            "followups":       [],
            "source":          source
        }

    result = result.replace(
        "```json", "").replace("```", "").strip()

    start = result.find('{')
    end   = result.rfind('}') + 1
    if start != -1 and end > start:
        result = result[start:end]

    try:
        parsed         = json.loads(result)
        parsed['source'] = source
        return parsed
    except Exception as e:
        print(f"[LLM] Parse error: {e}")
        return {
            "intent":          "DATA_QUESTION",
            "sql":             None,
            "casual_response": None,
            "source":          source,
            "followups":       []
        }
    

def generate_sql(user_question, schema, chat_history=None):
    """
    Standalone SQL generator.
    Used for retries and fallback.
    """
    history_str = _format_history(chat_history or [])

    prompt = f"""You are an expert MySQL query generator.

Database schema:
{schema}

Previous conversation:
{history_str}

STRICT RULES:
- Return ONLY a valid MySQL SELECT query
- No explanation, no markdown, no backticks
- Use exact table and column names from schema
- Never use DROP, DELETE, UPDATE, INSERT
- Never use SELECT * — select specific columns
- Add LIMIT 100 unless question asks for totals or counts

Question: {user_question}

SQL only:"""

    sql = call_groq(
        prompt,
        system_message="You are an expert MySQL query generator. Return only SQL."
    )

    # Clean markdown
    sql = sql.replace("```sql", "").replace("```", "").strip()

    # Extract SQL lines
    lines     = sql.split('\n')
    sql_lines = []
    capture   = False
    for line in lines:
        line = line.strip()
        if line.upper().startswith('SELECT'):
            capture = True
        if capture and line:
            sql_lines.append(line)

    if sql_lines:
        sql = ' '.join(sql_lines)

    print(f"[LLM] Generated SQL: {sql}")
    return sql


def explain_results(user_question, sql_query,
                    results, columns, chat_history=None):
    """
    Explain SQL results in plain English.
    Called only for complex multi-row results.
    """
    history_str = _format_history(chat_history or [])

    if not results:
        result_str = "No data found."
    else:
        header = " | ".join(columns)
        rows   = "\n".join([
            " | ".join(str(v) for v in row)
            for row in results[:20]
        ])
        result_str = f"{header}\n{rows}"

    prompt = f"""You are a helpful data analyst assistant.

Previous conversation:
{history_str}

User asked: "{user_question}"

Data returned:
{result_str}

Instructions:
- Explain in 2-3 clear sentences for a non-technical user
- Be specific about numbers and insights
- Format numbers with commas and $ where appropriate
- Do NOT mention SQL or technical terms
- Reference conversation context if relevant"""

    return call_groq(
        prompt,
        system_message="You are a helpful data analyst assistant."
    )


def generate_followup_questions(user_question, answer, schema):
    """
    Generate follow-up questions.
    Separate function kept for compatibility.
    """
    prompt = f"""You are a data analyst chatbot.

User just asked: "{user_question}"
Got answer: "{answer[:200]}"

Generate exactly 3 short follow-up questions.
Return ONLY a JSON array:
["question 1", "question 2", "question 3"]

JSON array only:"""

    response = call_groq(
        prompt,
        system_message="Return only a JSON array of 3 strings."
    )

    try:
        response  = response.replace(
            "```json", "").replace("```", "").strip()
        followups = json.loads(response)
        if isinstance(followups, list):
            return followups[:3]
        return []
    except Exception:
        return [
            "What is the total revenue?",
            "Show top 5 products",
            "Which channel performs best?"
        ]


def handle_casual_chat(user_message, chat_history=None):
    """Casual conversation handler"""
    history_str = _format_history(chat_history or [])
    prompt = f"""You are a friendly data analyst chatbot.

Previous conversation:
{history_str}

User said: "{user_message}"

Respond naturally in 1-2 sentences.
Then remind them you can help with data questions."""

    return call_groq(
        prompt,
        system_message="You are a friendly data analyst chatbot."
    )


def handle_help_request(schema):
    """Help request handler"""
    prompt = f"""You are a data analyst chatbot.
User wants to know what you can help with.

Schema: {schema}

Give 5-6 specific example questions they can ask.
Be friendly. Format as numbered list."""

    return call_groq(
        prompt,
        system_message="You are a helpful data analyst chatbot."
    )


def handle_schema_request(schema):
    """Schema explanation handler"""
    prompt = f"""You are a data analyst chatbot.
User wants to know what data is available.

Schema: {schema}

Explain in simple non-technical terms.
What tables exist and what questions can they ask."""

    return call_groq(
        prompt,
        system_message="You are a helpful data analyst chatbot."
    )


def handle_out_of_scope(user_message):
    """Out of scope handler"""
    return (
        "I'm specialized in analyzing your business data. "
        "I can help with revenue, orders, products, customers, "
        "and more. What would you like to know about your data?"
    )