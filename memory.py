from db import get_connection

MAX_HISTORY = 6  # Last 6 messages per user


def save_message(user_id, role, message):
    """
    Save one message to MySQL.
    role = 'user' or 'assistant'
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO conversations
            (user_id, role, message)
            VALUES (%s, %s, %s)
        """, (user_id, role, message))
        conn.commit()
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"[Memory] Save error: {e}")


def get_history(user_id):
    """
    Get last N messages for a user.
    Returns list of dicts like:
    [
        {"role": "user",      "content": "what is revenue?"},
        {"role": "assistant", "content": "Revenue is $1.2B"}
    ]
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor(dictionary=True)

        # Get last MAX_HISTORY * 2 messages
        # (* 2 because each exchange = 2 rows)
        cursor.execute("""
            SELECT role, message
            FROM conversations
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s
        """, (user_id, MAX_HISTORY * 2))

        rows = cursor.fetchall()
        cursor.close()
        conn.close()

        # Reverse so oldest message is first
        rows.reverse()

        # Format for LLM prompt
        history = []
        for row in rows:
            history.append({
                "role":    row['role'],
                "content": row['message']
            })

        return history

    except Exception as e:
        print(f"[Memory] Get error: {e}")
        return []


def clear_history(user_id):
    """Clear all messages for a user"""
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            DELETE FROM conversations
            WHERE user_id = %s
        """, (user_id,))
        conn.commit()
        cursor.close()
        conn.close()
        print(f"[Memory] Cleared for user {user_id}")
    except Exception as e:
        print(f"[Memory] Clear error: {e}")


def get_all_conversations(limit=100):
    """
    Admin function — see all conversations
    across all users
    """
    try:
        conn   = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                c.id,
                c.user_id,
                u.username,
                c.role,
                c.message,
                c.created_at
            FROM conversations c
            JOIN users u ON c.user_id = u.id
            ORDER BY c.created_at DESC
            LIMIT %s
        """, (limit,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"[Memory] Admin fetch error: {e}")
        return []

def get_all_conversations(limit=100):
    try:
        conn   = get_connection()
        cursor = conn.cursor(dictionary=True)
        cursor.execute("""
            SELECT
                c.id,
                c.user_id,
                u.username,
                u.role as user_role,
                c.role,
                c.message,
                c.created_at
            FROM conversations c
            JOIN users u ON c.user_id = u.id
            ORDER BY c.created_at DESC
            LIMIT %s
        """, (limit,))
        rows = cursor.fetchall()
        cursor.close()
        conn.close()
        return rows
    except Exception as e:
        print(f"[Memory] Admin fetch error: {e}")
        return []


def get_user_conversation_count(user_id):
    """How many messages has this user sent"""
    try:
        conn   = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*) FROM conversations
            WHERE user_id = %s AND role = 'user'
        """, (user_id,))
        count = cursor.fetchone()[0]
        cursor.close()
        conn.close()
        return count
    except Exception:
        return 0