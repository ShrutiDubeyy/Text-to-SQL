import hashlib
import time
import json
from db import get_connection


def _ensure_cache_table():
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS _query_cache (
                cache_key  VARCHAR(64)  PRIMARY KEY,
                question   TEXT,
                sql_query  TEXT,
                answer     TEXT,
                row_count  INT,
                followups  TEXT,
                expires_at BIGINT,
                hit_count  INT DEFAULT 0
            )
        """)
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[Cache] Setup error: {e}")


def cache_get(question):
    try:
        _ensure_cache_table()
        key    = hashlib.md5(
            question.lower().strip().encode()
        ).hexdigest()
        now    = int(time.time())
        conn   = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT * FROM _query_cache
            WHERE cache_key = %s AND expires_at > %s
        """, (key, now))
        result = cursor.fetchone()
        if result:
            cursor.execute("""
                UPDATE _query_cache
                SET hit_count = hit_count + 1
                WHERE cache_key = %s
            """, (key,))
            conn.commit()
            print(f"[Cache] HIT: {question[:40]}")
        cursor.close()
        conn.close()
        return result
    except Exception as e:
        print(f"[Cache] Get error: {e}")
        return None


def cache_set(question, sql_query, answer,
              row_count, followups_json="[]", ttl=3600):
    try:
        _ensure_cache_table()
        key        = hashlib.md5(
            question.lower().strip().encode()
        ).hexdigest()
        expires_at = int(time.time()) + ttl
        conn       = get_connection()
        cursor     = conn.cursor()
        cursor.execute("""
            INSERT INTO _query_cache
            (cache_key, question, sql_query,
             answer, row_count, followups, expires_at)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                sql_query  = VALUES(sql_query),
                answer     = VALUES(answer),
                row_count  = VALUES(row_count),
                followups  = VALUES(followups),
                expires_at = VALUES(expires_at),
                hit_count  = 0
        """, (key, question, sql_query,
              answer, row_count, followups_json, expires_at))
        conn.commit()
        cursor.close()
        conn.close()
        print(f"[Cache] SAVED: {question[:40]}")
    except Exception as e:
        print(f"[Cache] Set error: {e}")


def cache_clear():
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute("DELETE FROM _query_cache")
        conn.commit()
        cursor.close()
        conn.close()
        print("[Cache] Cleared")
    except Exception as e:
        print(f"[Cache] Clear error: {e}")


def format_simple_result(question, results, columns):
    """
    Format simple single-value results without LLM.
    Returns None for complex results so LLM handles them.
    """
    if not results:
        return "No data found for your query."

    if len(results) == 1 and len(columns) == 1:
        val = results[0][0]
        col = columns[0].lower()
        try:
            num = float(val)
            if any(w in col for w in
                   ['revenue', 'sales', 'total',
                    'amount', 'cost', 'budget']):
                formatted = f"${num:,.2f}"
                if num >= 1_000_000_000:
                    formatted += f" ({num/1_000_000_000:.1f}B)"
                elif num >= 1_000_000:
                    formatted += f" ({num/1_000_000:.1f}M)"
                return f"The total is **{formatted}**."
            if any(w in col for w in
                   ['count', 'orders', 'number', 'total_orders']):
                return f"There are **{int(num):,}** in total."
            if any(w in col for w in ['avg', 'average', 'mean']):
                return f"The average value is **${num:,.2f}**."
            return f"The result is **{num:,.2f}**."
        except (ValueError, TypeError):
            return f"Result: **{val}**"

    return None