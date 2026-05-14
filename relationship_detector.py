from db import get_connection
from sqlalchemy import text
import json
import os

# We'll import call_groq lazily to avoid circular imports
_groq_client = None

def _get_groq_client():
    global _groq_client
    if _groq_client is None:
        from groq import Groq
        from dotenv import load_dotenv
        load_dotenv()
        _groq_client = Groq(api_key=os.getenv("GROQ_API_KEY"))
    return _groq_client


def _call_groq_for_relationships(prompt):
    """Direct Groq call for relationship detection"""
    client = _get_groq_client()
    models = [
        "llama-3.3-70b-versatile",
        "llama-3.1-8b-instant"
    ]
    for model in models:
        try:
            response = client.chat.completions.create(
                model=model,
                messages=[
                    {
                        "role": "system",
                        "content": "You are a database expert. Return only valid JSON."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0,
                max_tokens=2000,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            print(f"[Relationship] Model {model} failed: {e}")
            continue
    return "[]"


def _ensure_relationship_table():
    """Create table to cache detected relationships"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS _relationships (
            id INT AUTO_INCREMENT PRIMARY KEY,
            from_table VARCHAR(200),
            from_col VARCHAR(200),
            to_table VARCHAR(200),
            to_col VARCHAR(200),
            description TEXT,
            confidence VARCHAR(20),
            detected_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)
    conn.commit()
    cursor.close()
    conn.close()


def get_all_table_schemas():
    """Get schema of all tables for LLM analysis"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SHOW TABLES")
    tables = [
        row[0] for row in cursor.fetchall()
        if not row[0].startswith('_')
    ]

    schemas = {}
    for table in tables:
        cursor.execute(f"DESCRIBE `{table}`")
        columns = [(row[0], row[1]) for row in cursor.fetchall()]

        cursor.execute(f"SELECT * FROM `{table}` LIMIT 3")
        samples = cursor.fetchall()

        col_names = [col[0] for col in columns]
        schemas[table] = {
            "columns": columns,
            "sample_rows": [
                dict(zip(col_names, row)) for row in samples
            ]
        }

    cursor.close()
    conn.close()
    return schemas


def detect_relationships_with_llm():
    """
    Use LLM to intelligently detect relationships
    between ALL tables — works for ANY unknown file.
    """
    print("[Relationship] 🔍 Detecting relationships with LLM...")

    schemas = get_all_table_schemas()

    if len(schemas) < 2:
        return []

    # Build schema description for LLM
    schema_desc = []
    for table, info in schemas.items():
        cols = ", ".join([f"{c[0]} ({c[1]})" for c in info["columns"]])
        samples = info["sample_rows"][:2]
        schema_desc.append(
            f"Table: {table}\n"
            f"Columns: {cols}\n"
            f"Sample data: {json.dumps(samples, default=str)}"
        )

    schema_text = "\n\n".join(schema_desc)

    prompt = f"""You are a database expert analyzing table schemas to find relationships.

Here are all the tables and their data:

{schema_text}

TASK: Find all relationships between these tables.
Look for:
1. Columns with matching names (e.g. customer_id in both tables)
2. Columns where one looks like a foreign key to another 
   (e.g. customer_name_index → customer_index)
3. Columns with matching sample values
4. Index/ID columns that reference another table

Return ONLY a JSON array. No explanation. Example format:
[
  {{
    "from_table": "sales_order",
    "from_col": "customer_name_index",
    "to_table": "customers",
    "to_col": "customer_index",
    "description": "sales_order links to customers",
    "confidence": "high"
  }}
]

If no relationships found return empty array: []

JSON array only:"""

    response = _call_groq_for_relationships(prompt)

    try:
        # Clean response
        response = response.replace("```json", "").replace("```", "").strip()
        relationships = json.loads(response)

        if isinstance(relationships, list):
            print(f"[Relationship] ✅ Found {len(relationships)} relationships")
            return relationships

    except Exception as e:
        print(f"[Relationship] ❌ Parse error: {e}")
        print(f"[Relationship] Raw response: {response[:200]}")

    return []


def save_relationships(relationships):
    """Save detected relationships to MySQL cache"""
    try:
        _ensure_relationship_table()
        conn = get_connection()
        cursor = conn.cursor()

        # Clear old relationships
        cursor.execute("DELETE FROM _relationships")

        # Save new ones
        for r in relationships:
            cursor.execute("""
                INSERT INTO _relationships
                (from_table, from_col, to_table, to_col,
                 description, confidence)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (
                r.get("from_table", ""),
                r.get("from_col", ""),
                r.get("to_table", ""),
                r.get("to_col", ""),
                r.get("description", ""),
                r.get("confidence", "medium")
            ))

        conn.commit()
        cursor.close()
        conn.close()
        print(f"[Relationship] 💾 Saved {len(relationships)} relationships")

    except Exception as e:
        print(f"[Relationship] Save error: {e}")


def load_cached_relationships():
    """Load relationships from MySQL cache"""
    try:
        _ensure_relationship_table()
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("SELECT * FROM _relationships")
        relationships = cursor.fetchall()
        cursor.close()
        conn.close()
        return relationships
    except Exception:
        return []


def get_relationships(force_refresh=False):
    """
    Main function — gets relationships.
    Uses cache if available, detects fresh if not.
    """
    if not force_refresh:
        cached = load_cached_relationships()
        if cached:
            print(f"[Relationship] 📋 Using cached "
                  f"{len(cached)} relationships")
            return cached

    # Detect fresh using LLM
    relationships = detect_relationships_with_llm()
    save_relationships(relationships)
    return relationships


def refresh_relationships():
    """Force refresh — call this when new file is uploaded"""
    print("[Relationship] 🔄 Refreshing relationships...")
    return get_relationships(force_refresh=True)


def format_relationships_for_llm(relationships):
    """Format for injecting into SQL generation prompt"""
    if not relationships:
        return "No relationships detected between tables."

    lines = ["TABLE RELATIONSHIPS (use these for JOINs):"]
    for r in relationships:
        confidence = r.get('confidence', 'medium')
        lines.append(
            f"- {r['from_table']}.{r['from_col']} = "
            f"{r['to_table']}.{r['to_col']} "
            f"[{confidence} confidence]"
        )

    lines.append("\nSAMPLE JOIN PATTERN:")
    if relationships:
        r = relationships[0]
        lines.append(
            f"SELECT * FROM {r['from_table']} "
            f"JOIN {r['to_table']} ON "
            f"{r['from_table']}.{r['from_col']} = "
            f"{r['to_table']}.{r['to_col']}"
        )

    return "\n".join(lines)