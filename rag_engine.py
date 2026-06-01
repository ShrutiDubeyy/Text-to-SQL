import json
import re
from db import get_connection


class RAGEngine:
    """
    Simple RAG for SQL generation.
    Stores successful Q+SQL pairs.
    Finds similar examples for new questions.
    No vector database needed — pure Python.
    """

    def __init__(self):
        self._ensure_table()

    def _ensure_table(self):
        """Create query examples table"""
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS
                _query_examples (
                    id          INT AUTO_INCREMENT
                                PRIMARY KEY,
                    question    TEXT NOT NULL,
                    sql_query   TEXT NOT NULL,
                    keywords    TEXT,
                    use_count   INT DEFAULT 0,
                    success_rate FLOAT DEFAULT 1.0,
                    created_at  TIMESTAMP DEFAULT
                                CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"[RAG] Table error: {e}")

    def save_example(self, question, sql_query):
        """
        Save a successful Q+SQL pair.
        Called after every successful query.
        """
        try:
            keywords = self._extract_keywords(
                question)
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO _query_examples
                (question, sql_query, keywords)
                VALUES (%s, %s, %s)
            """, (question, sql_query,
                  json.dumps(keywords)))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"[RAG] Save error: {e}")

    def find_similar(self, question, top_k=3):
        """
        Find similar past questions.
        Returns list of (question, sql) pairs.
        Uses keyword overlap scoring.
        """
        try:
            conn   = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT question, sql_query,
                       keywords, use_count
                FROM _query_examples
                ORDER BY use_count DESC
                LIMIT 50
            """)
            examples = cursor.fetchall()
            cursor.close()
            conn.close()

        except Exception as e:
            print(f"[RAG] Find error: {e}")
            return []

        if not examples:
            return []

        # Score each example
        q_keywords = set(
            self._extract_keywords(question))
        scored = []

        for ex in examples:
            try:
                ex_keywords = set(
                    json.loads(ex['keywords'] or '[]'))
                overlap = len(
                    q_keywords & ex_keywords)
                if overlap > 0:
                    scored.append({
                        'question':  ex['question'],
                        'sql':       ex['sql_query'],
                        'score':     overlap,
                        'use_count': ex['use_count']
                    })
            except Exception:
                pass

        # Sort by score then use_count
        scored.sort(
            key=lambda x: (x['score'],
                           x['use_count']),
            reverse=True
        )

        return scored[:top_k]

    def _extract_keywords(self, text):
        """Extract meaningful keywords"""
        # Remove common words
        stop_words = {
            'what', 'is', 'the', 'a', 'an',
            'of', 'for', 'in', 'by', 'how',
            'many', 'much', 'show', 'me',
            'give', 'tell', 'find', 'get',
            'list', 'all', 'total', 'and',
            'or', 'to', 'from', 'with', 'my',
            'our', 'this', 'that', 'are', 'were'
        }
        words = re.findall(r'\b\w+\b',
                           text.lower())
        return [w for w in words
                if w not in stop_words
                and len(w) > 2]

    def format_examples_for_prompt(
            self, examples):
        """
        Format examples as few-shot context
        for LLM prompt.
        """
        if not examples:
            return ""

        lines = [
            "SIMILAR PAST QUERIES "
            "(use these as reference):"]

        for ex in examples:
            lines.append(
                f"\nQ: {ex['question']}\n"
                f"SQL: {ex['sql']}"
            )

        return '\n'.join(lines)

    def increment_use_count(self, question):
        """Mark example as used successfully"""
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE _query_examples
                SET use_count = use_count + 1
                WHERE question = %s
                LIMIT 1
            """, (question,))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"[RAG] Count error: {e}")

    def get_stats(self):
        """Get RAG system stats"""
        try:
            conn   = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT
                    COUNT(*) as total_examples,
                    SUM(use_count) as total_uses,
                    AVG(success_rate) as avg_success
                FROM _query_examples
            """)
            stats = cursor.fetchone()
            cursor.close()
            conn.close()
            return stats
        except Exception:
            return {}

    def seed_examples(self):
        """
        Pre-load common business queries.
        So RAG works from day one.
        """
        examples = [
            (
                "What is the total revenue?",
                "SELECT SUM(line_total) as total_revenue FROM sales_order"
            ),
            (
                "How many orders were placed?",
                "SELECT COUNT(*) as total_orders FROM sales_order"
            ),
            (
                "What is revenue by channel?",
                "SELECT channel, SUM(line_total) as revenue FROM sales_order GROUP BY channel ORDER BY revenue DESC"
            ),
            (
                "Who are the top 5 customers?",
                "SELECT customer_name_index, SUM(line_total) as total_revenue FROM sales_order GROUP BY customer_name_index ORDER BY total_revenue DESC LIMIT 5"
            ),
            (
                "What are the top products by revenue?",
                "SELECT product_description_index, SUM(line_total) as revenue FROM sales_order GROUP BY product_description_index ORDER BY revenue DESC LIMIT 10"
            ),
            (
                "What is the monthly revenue trend?",
                "SELECT DATE_FORMAT(orderdate, '%Y-%m') as month, SUM(line_total) as revenue FROM sales_order GROUP BY month ORDER BY month ASC"
            ),
            (
                "What is the average order value?",
                "SELECT ROUND(AVG(line_total), 2) as avg_order_value FROM sales_order"
            ),
            (
                "Which warehouse has the most orders?",
                "SELECT warehouse_code, COUNT(*) as orders FROM sales_order GROUP BY warehouse_code ORDER BY orders DESC"
            ),
        ]

        print("[RAG] Seeding examples...")
        for question, sql in examples:
            self.save_example(question, sql)
        print(f"[RAG] ✅ Seeded "
              f"{len(examples)} examples")


rag = RAGEngine()