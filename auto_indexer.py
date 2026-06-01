import re
from db import get_connection


class AutoIndexer:
    """
    Automatically analyzes tables and creates
    indexes on the right columns.
    Zero manual work needed.
    Works on ANY new dataset.
    """

    DATE_PATTERNS = [
        'date', 'time', 'created', 'updated',
        'timestamp', 'year', 'month', 'day'
    ]

    CATEGORY_PATTERNS = [
        'channel', 'type', 'category', 'status',
        'region', 'country', 'state', 'zone',
        'warehouse', 'department', 'segment'
    ]

    ID_PATTERNS = [
        'id', 'index', 'code', 'key', 'number',
        'ref', 'order', 'customer', 'product'
    ]

    AMOUNT_PATTERNS = [
        'total', 'amount', 'price', 'cost',
        'revenue', 'sales', 'profit', 'value',
        'quantity', 'qty', 'count'
    ]

    SKIP_PATTERNS = [
        'description', 'notes', 'comment',
        'address', 'text', 'detail', 'hash',
        'password', 'token', 'secret'
    ]

    SKIP_TABLES = [
        'users', 'conversations', 'roles',
        '_audit_log', '_query_cache',
        '_loaded_files', '_relationships'
    ]

    def analyze_table(self, table_name):
        """Analyze table and decide which columns need indexes"""
        try:
            conn   = get_connection()
            cursor = conn.cursor(dictionary=True)

            cursor.execute(f"DESCRIBE `{table_name}`")
            columns = cursor.fetchall()

            cursor.execute(
                f"SELECT COUNT(*) as cnt "
                f"FROM `{table_name}`"
            )
            row_count = cursor.fetchone()['cnt']
            cursor.close()
            conn.close()

            recommendations = []

            for col in columns:
                col_name = col['Field'].lower()
                col_type = col['Type'].upper()
                col_key  = col['Key']

                if col_key in ['PRI', 'UNI', 'MUL']:
                    continue

                if any(s in col_name
                       for s in self.SKIP_PATTERNS):
                    continue

                reason = self._needs_index(
                    col_name, col_type, row_count)

                if reason:
                    recommendations.append({
                        "table":    table_name,
                        "column":   col['Field'],
                        "col_type": col_type,
                        "reason":   reason,
                        "priority": self._get_priority(
                            col_name, col_type)
                    })

            recommendations.sort(
                key=lambda x: x['priority'],
                reverse=True
            )

            return recommendations

        except Exception as e:
            print(f"[AutoIndexer] Analyze error: {e}")
            return []

    def _needs_index(self, col_name,
                     col_type, row_count):
        if row_count < 100:
            return None

        if any(p in col_name for p in self.DATE_PATTERNS):
            return "Date column — used in WHERE/GROUP BY"

        if any(p in col_name
               for p in self.CATEGORY_PATTERNS):
            return "Category column — used in GROUP BY"

        if any(p in col_name for p in self.ID_PATTERNS):
            if any(t in col_type for t in
                   ['INT', 'VARCHAR', 'CHAR', 'TEXT']):
                return "ID/Key column — used in JOINs"

        if any(p in col_name
               for p in self.AMOUNT_PATTERNS):
            if any(t in col_type for t in
                   ['INT', 'FLOAT', 'DOUBLE',
                    'DECIMAL', 'BIGINT']):
                return "Numeric column — used in SUM/AVG"

        return None

    def _get_priority(self, col_name, col_type):
        score = 0
        if any(p in col_name for p in self.DATE_PATTERNS):
            score += 10
        if any(p in col_name
               for p in self.CATEGORY_PATTERNS):
            score += 8
        if any(p in col_name for p in self.ID_PATTERNS):
            score += 9
        if any(p in col_name
               for p in self.AMOUNT_PATTERNS):
            score += 7
        return score

    def _get_column_type(self, table_name, column_name):
        """Get actual MySQL column type"""
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                SELECT DATA_TYPE
                FROM information_schema.COLUMNS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME  = %s
                AND COLUMN_NAME = %s
            """, (table_name, column_name))
            row = cursor.fetchone()
            cursor.close()
            conn.close()
            return row[0].upper() if row else 'TEXT'
        except Exception:
            return 'TEXT'

    def create_index(self, table_name, column_name):
        """Create index — handles TEXT columns with prefix"""
        try:
            idx_name = (
                f"idx_{table_name[:20]}_"
                f"{column_name[:20]}"
            ).lower()
            idx_name = re.sub(
                r'[^a-z0-9_]', '_', idx_name)

            conn   = get_connection()
            cursor = conn.cursor()

            # Check if index already exists
            cursor.execute("""
                SELECT COUNT(*)
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME   = %s
                AND COLUMN_NAME  = %s
            """, (table_name, column_name))

            exists = cursor.fetchone()[0] > 0

            if exists:
                print(f"[AutoIndexer] Already exists: "
                      f"{table_name}.{column_name}")
                cursor.close()
                conn.close()
                return True, "already_exists"

            # Get column type
            col_type = self._get_column_type(
                table_name, column_name)

            # TEXT/BLOB needs prefix length
            if col_type in ['TEXT', 'BLOB',
                            'MEDIUMTEXT', 'LONGTEXT']:
                sql = (
                    f"CREATE INDEX `{idx_name}` "
                    f"ON `{table_name}` "
                    f"(`{column_name}`(50))"
                )
            else:
                sql = (
                    f"CREATE INDEX `{idx_name}` "
                    f"ON `{table_name}` "
                    f"(`{column_name}`)"
                )

            cursor.execute(sql)
            conn.commit()
            cursor.close()
            conn.close()

            print(f"[AutoIndexer] ✅ Created: {idx_name}")
            return True, "created"

        except Exception as e:
            print(f"[AutoIndexer] ❌ Error: {e}")
            return False, str(e)

    def auto_index_table(self, table_name):
        """Analyze and auto-create all indexes for a table"""
        print(f"\n[AutoIndexer] 🔍 Analyzing: {table_name}")

        recommendations = self.analyze_table(table_name)

        if not recommendations:
            print(f"[AutoIndexer] No indexes needed "
                  f"for {table_name}")
            return []

        results = []
        for rec in recommendations:
            print(f"[AutoIndexer] Creating index on "
                  f"{rec['column']} — {rec['reason']}")

            success, status = self.create_index(
                table_name, rec['column'])

            results.append({
                "column":  rec['column'],
                "reason":  rec['reason'],
                "success": success,
                "status":  status
            })

        created = sum(
            1 for r in results
            if r['status'] == 'created'
        )
        print(f"[AutoIndexer] ✅ Done — "
              f"{created} new indexes on {table_name}")

        return results

    def auto_index_all_tables(self):
        """Index all tables — runs on startup"""
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("SHOW TABLES")
            tables = [
                row[0] for row in cursor.fetchall()
                if not row[0].startswith('_')
                and row[0] not in self.SKIP_TABLES
            ]
            cursor.close()
            conn.close()

            all_results = {}
            for table in tables:
                all_results[table] = \
                    self.auto_index_table(table)

            total_created = sum(
                sum(1 for r in results
                    if r.get('status') == 'created')
                for results in all_results.values()
            )
            print(f"\n[AutoIndexer] 🎉 Complete — "
                  f"{total_created} total indexes created")

            return all_results

        except Exception as e:
            print(f"[AutoIndexer] Error: {e}")
            return {}

    def get_index_report(self):
        """Get all indexes for admin panel"""
        try:
            conn   = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT
                    TABLE_NAME   as table_name,
                    INDEX_NAME   as index_name,
                    COLUMN_NAME  as column_name,
                    NON_UNIQUE   as non_unique
                FROM information_schema.STATISTICS
                WHERE TABLE_SCHEMA = DATABASE()
                AND TABLE_NAME NOT LIKE '!_%' ESCAPE '!'
                AND INDEX_NAME != 'PRIMARY'
                ORDER BY TABLE_NAME, INDEX_NAME
            """)
            indexes = cursor.fetchall()
            cursor.close()
            conn.close()
            return indexes
        except Exception as e:
            print(f"[AutoIndexer] Report error: {e}")
            return []


# Global instance
auto_indexer = AutoIndexer()