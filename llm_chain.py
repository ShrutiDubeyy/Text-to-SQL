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
    """
    ONE single LLM call that does everything:
    - Detects intent
    - Generates SQL if needed
    - Generates casual response if needed
    - Generates follow-up questions
    Replaces 4 separate calls with 1.
    """
    history_str = _format_history(chat_history or [])

    prompt = f"""You are an expert AI data analyst assistant.

Database schema:
{schema}

Previous conversation:
{history_str}

User message: "{user_question}"

Respond with ONLY a JSON object in this exact format:

{{
    "intent": "DATA_QUESTION or CASUAL_CHAT or HELP_REQUEST or SCHEMA_REQUEST or OUT_OF_SCOPE",
    "sql": "SELECT query here or null if not a data question",
    "casual_response": "friendly response if casual/help/schema or null",
    "followups": ["question 1", "question 2", "question 3"]
}}

Rules for intent:
- DATA_QUESTION: wants data, numbers, insights from database
- CASUAL_CHAT: greeting, thanks, small talk, acknowledgement
- HELP_REQUEST: asking what you can do or how to use
- SCHEMA_REQUEST: asking what tables or data exists
- OUT_OF_SCOPE: completely unrelated to data

Rules for sql:
- Only for DATA_QUESTION intent
- Valid MySQL SELECT query only
- Use exact column and table names from schema
- No markdown, no backticks, no comments
- Add LIMIT 100 unless aggregating with SUM/COUNT/AVG
- null for all other intents

Rules for casual_response:
- For CASUAL_CHAT: warm friendly reply in 1-2 sentences
- For HELP_REQUEST: list 5-6 example questions they can ask
- For SCHEMA_REQUEST: explain what tables exist in simple terms
- For OUT_OF_SCOPE: politely redirect to data questions
- null for DATA_QUESTION

Rules for followups:
- Always exactly 3 short relevant follow-up questions
- Based on what was just asked
- null is not allowed here always give 3

Return ONLY the JSON. No explanation outside JSON."""

    response = call_groq(
        prompt,
        system_message="You are a data analyst. Return only valid JSON."
    )

    # Clean response
    response = response.replace(
        "```json", "").replace("```", "").strip()

    # Find JSON object
    start = response.find('{')
    end   = response.rfind('}') + 1
    if start != -1 and end > start:
        response = response[start:end]

    try:
        result = json.loads(response)
        return result
    except Exception as e:
        print(f"[LLM] JSON parse error: {e}")
        print(f"[LLM] Raw response: {response[:200]}")
        # Fallback
        return {
            "intent":          "DATA_QUESTION",
            "sql":             None,
            "casual_response": None,
            "followups":       [
                "What is the total revenue?",
                "Show top 5 products",
                "Which channel performs best?"
            ]
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