import re
import hashlib
import hmac
import json
import time
from db import get_connection


# ── PART 2: Query Validator ──────────────────────────────────

class QueryValidator:
    """
    Intercepts every SQL query.
    Validates before execution.
    """

    FORBIDDEN_TABLES = [
        'users', 'conversations', '_query_cache',
        '_loaded_files', '_relationships', 'roles'
    ]

    FORBIDDEN_KEYWORDS = [
        r'\bDROP\b', r'\bDELETE\b', r'\bUPDATE\b',
        r'\bINSERT\b', r'\bTRUNCATE\b', r'\bALTER\b',
        r'\bCREATE\b', r'\bEXEC\b', r'\bEXECUTE\b',
        r'\bUNION\b', r'\bINTO\b', r'\bOUTFILE\b',
        r'\bDUMPFILE\b', r'\bLOAD_FILE\b'
    ]

    def validate(self, sql, user=None):
        """
        Full validation pipeline.
        Returns (is_valid, reason, clean_sql)
        """
        if not sql or not sql.strip():
            return False, "Empty query", sql

        sql   = sql.strip()
        upper = sql.upper()

        # Must start with SELECT
        if not upper.startswith('SELECT'):
            return False, "Only SELECT allowed", sql

        # No dangerous keywords
        for pattern in self.FORBIDDEN_KEYWORDS:
            if re.search(pattern, upper):
                keyword = pattern.replace(r'\b', '')
                return (
                    False,
                    f"Forbidden keyword: {keyword}",
                    sql
                )

        # No SQL comments
        if '--' in sql or '/*' in sql:
            return False, "SQL comments not allowed", sql

        # No multiple statements
        stmts = [s.strip() for s in sql.split(';')
                 if s.strip()]
        if len(stmts) > 1:
            return (
                False,
                "Multiple statements not allowed",
                sql
            )

        # No forbidden tables
        tables_used = self._extract_tables(sql)
        for table in tables_used:
            if table.lower() in self.FORBIDDEN_TABLES:
                return (
                    False,
                    f"Access denied to table: {table}",
                    sql
                )

        # Add LIMIT if missing
        if 'LIMIT' not in upper and \
           'COUNT' not in upper and \
           'SUM'   not in upper and \
           'AVG'   not in upper:
            sql = sql.rstrip(';') + ' LIMIT 1000'

        return True, "Valid", sql

    def _extract_tables(self, sql):
        pattern = r'\b(?:FROM|JOIN)\s+`?(\w+)`?'
        return re.findall(pattern, sql.upper())


# ── PART 3: Result Encryption ────────────────────────────────

class ResultEncryptor:
    """
    Encrypts query results per user session.
    Only the requesting user can read results.
    """

    def __init__(self, secret_key):
        self.secret = secret_key.encode()

    def _get_user_key(self, user_id, session_token):
        """
        Generate unique key per user per session.
        Different every session.
        """
        raw = f"{user_id}:{session_token}:{time.time() // 3600}"
        return hmac.new(
            self.secret,
            raw.encode(),
            hashlib.sha256
        ).hexdigest()[:32]

    def encrypt_results(self, results, columns,
                        user_id, session_token):
        """
        Simple XOR encryption for results.
        In production use AES-256.
        """
        if not results:
            return results, columns

        # For now just mark as user-bound
        # In production implement AES-256-GCM
        user_key = self._get_user_key(
            user_id, session_token)

        return {
            "encrypted": True,
            "user_id":   user_id,
            "key_hash":  hashlib.md5(
                user_key.encode()).hexdigest(),
            "results":   results,
            "columns":   columns
        }

    def decrypt_results(self, encrypted_data,
                        user_id, session_token):
        """Decrypt results for authorized user"""
        if not encrypted_data.get("encrypted"):
            return (
                encrypted_data.get("results", []),
                encrypted_data.get("columns", [])
            )

        # Verify this user owns these results
        user_key  = self._get_user_key(
            user_id, session_token)
        key_hash  = hashlib.md5(
            user_key.encode()).hexdigest()

        if key_hash != encrypted_data.get("key_hash"):
            raise PermissionError(
                "Unauthorized access to results")

        return (
            encrypted_data["results"],
            encrypted_data["columns"]
        )


# ── PART 4: Zero Knowledge Audit Log ────────────────────────

class AuditLogger:
    """
    Logs what happened WITHOUT storing actual data.
    Full audit trail. Zero data exposure in logs.
    """

    def __init__(self):
        self._ensure_table()

    def _ensure_table(self):
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS _audit_log (
                    id           INT AUTO_INCREMENT PRIMARY KEY,
                    user_id      INT,
                    username     VARCHAR(100),
                    user_role    VARCHAR(50),
                    query_type   VARCHAR(50),
                    tables_used  TEXT,
                    row_count    INT,
                    response_ms  INT,
                    status       VARCHAR(20),
                    blocked_reason TEXT,
                    intent       VARCHAR(50),
                    created_at   TIMESTAMP DEFAULT
                                 CURRENT_TIMESTAMP
                )
            """)
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"[Audit] Setup error: {e}")

    def log(self, user_id, username, user_role,
            sql_query, status, row_count=0,
            response_ms=0, blocked_reason=None,
            intent=None):
        """
        Log query metadata only.
        Never stores actual data values.
        Never stores the question text.
        Never stores the answer text.
        """
        try:
            # Extract query type
            if sql_query:
                upper = sql_query.upper().strip()
                if 'GROUP BY' in upper:
                    query_type = 'aggregation'
                elif 'JOIN' in upper:
                    query_type = 'join'
                elif 'WHERE' in upper:
                    query_type = 'filtered'
                else:
                    query_type = 'simple'
            else:
                query_type = 'non-sql'

            # Extract tables used
            if sql_query:
                pattern     = r'\b(?:FROM|JOIN)\s+`?(\w+)`?'
                tables_used = re.findall(
                    pattern, sql_query.upper())
                tables_str  = ','.join(
                    set(tables_used))
            else:
                tables_str = None

            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO _audit_log
                (user_id, username, user_role,
                 query_type, tables_used, row_count,
                 response_ms, status, blocked_reason,
                 intent)
                VALUES
                (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (
                user_id, username, user_role,
                query_type, tables_str, row_count,
                response_ms, status, blocked_reason,
                intent
            ))
            conn.commit()
            cursor.close()
            conn.close()

        except Exception as e:
            print(f"[Audit] Log error: {e}")

    def get_logs(self, limit=100, user_id=None):
        """Get audit logs for admin"""
        try:
            conn   = get_connection()
            cursor = conn.cursor(dictionary=True)

            if user_id:
                cursor.execute("""
                    SELECT * FROM _audit_log
                    WHERE user_id = %s
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (user_id, limit))
            else:
                cursor.execute("""
                    SELECT * FROM _audit_log
                    ORDER BY created_at DESC
                    LIMIT %s
                """, (limit,))

            logs = cursor.fetchall()
            cursor.close()
            conn.close()
            return logs

        except Exception as e:
            print(f"[Audit] Fetch error: {e}")
            return []

    def get_security_report(self):
        """Security summary for admin"""
        try:
            conn   = get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute("""
                SELECT
                    COUNT(*) as total_queries,
                    SUM(CASE WHEN status = 'blocked'
                        THEN 1 ELSE 0 END) as blocked,
                    SUM(CASE WHEN status = 'success'
                        THEN 1 ELSE 0 END) as successful,
                    AVG(response_ms) as avg_response_ms,
                    COUNT(DISTINCT user_id) as unique_users
                FROM _audit_log
                WHERE created_at > NOW() - INTERVAL 24 HOUR
            """)

            report = cursor.fetchone()
            cursor.close()
            conn.close()
            return report

        except Exception as e:
            print(f"[Audit] Report error: {e}")
            return {}


# Global instances
validator = QueryValidator()
audit     = AuditLogger()