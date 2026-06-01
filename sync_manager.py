import time
from datetime import datetime
from db import get_connection


class SyncManager:
    """
    Central manager for all live data sources.
    Tracks sync status, logs events, manages sources.
    """

    def add_source(self, source_name, source_type,
                   table_name, source_url=None,
                   sync_interval=300):
        """
        Register a new data source.
        source_type: 'google_sheet', 'webhook', 'csv'
        """
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO _sync_sources
                (source_name, source_type, table_name,
                 source_url, sync_interval)
                VALUES (%s, %s, %s, %s, %s)
                ON DUPLICATE KEY UPDATE
                    source_url    = VALUES(source_url),
                    sync_interval = VALUES(sync_interval),
                    is_active     = TRUE
            """, (source_name, source_type,
                  table_name, source_url,
                  sync_interval))
            conn.commit()
            cursor.close()
            conn.close()
            print(f"[Sync] ✅ Source registered: "
                  f"{source_name}")
            return True
        except Exception as e:
            print(f"[Sync] Error adding source: {e}")
            return False

    def update_sync_status(self, source_name,
                           status, row_count=0,
                           error=None):
        """Update sync status for a source"""
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE _sync_sources
                SET last_sync      = NOW(),
                    last_status    = %s,
                    last_row_count = %s,
                    error_message  = %s
                WHERE source_name = %s
            """, (status, row_count, error,
                  source_name))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"[Sync] Status update error: {e}")

    def log_sync_event(self, source_name, source_id,
                       rows_added, rows_updated,
                       status, error=None,
                       duration_ms=0):
        """Log a sync event"""
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO _sync_log
                (source_id, source_name, rows_added,
                 rows_updated, status, error,
                 duration_ms)
                VALUES (%s, %s, %s, %s, %s, %s, %s)
            """, (source_id, source_name, rows_added,
                  rows_updated, status, error,
                  duration_ms))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"[Sync] Log error: {e}")

    def get_all_sources(self):
        """Get all registered data sources"""
        try:
            conn   = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM _sync_sources
                ORDER BY source_type, source_name
            """)
            sources = cursor.fetchall()
            cursor.close()
            conn.close()

            # Convert datetime to string
            for s in sources:
                if s.get('last_sync'):
                    s['last_sync'] = \
                        s['last_sync'].strftime(
                            '%Y-%m-%d %H:%M:%S')
                if s.get('created_at'):
                    s['created_at'] = \
                        s['created_at'].strftime(
                            '%Y-%m-%d %H:%M:%S')

            return sources
        except Exception as e:
            print(f"[Sync] Get sources error: {e}")
            return []

    def get_sync_logs(self, limit=50):
        """Get recent sync events"""
        try:
            conn   = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM _sync_log
                ORDER BY synced_at DESC
                LIMIT %s
            """, (limit,))
            logs = cursor.fetchall()
            cursor.close()
            conn.close()

            for log in logs:
                if log.get('synced_at'):
                    log['synced_at'] = \
                        log['synced_at'].strftime(
                            '%Y-%m-%d %H:%M:%S')
            return logs
        except Exception as e:
            print(f"[Sync] Logs error: {e}")
            return []

    def get_sources_due_for_sync(self):
        """Find sources that need syncing now"""
        try:
            conn   = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM _sync_sources
                WHERE is_active = TRUE
                AND source_type = 'google_sheet'
                AND (
                    last_sync IS NULL
                    OR TIMESTAMPDIFF(SECOND,
                       last_sync, NOW())
                       >= sync_interval
                )
            """)
            sources = cursor.fetchall()
            cursor.close()
            conn.close()
            return sources
        except Exception as e:
            print(f"[Sync] Due sync error: {e}")
            return []

    def deactivate_source(self, source_name):
        """Deactivate a data source"""
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                UPDATE _sync_sources
                SET is_active = FALSE
                WHERE source_name = %s
            """, (source_name,))
            conn.commit()
            cursor.close()
            conn.close()
            return True
        except Exception as e:
            print(f"[Sync] Deactivate error: {e}")
            return False


# Global instance
sync_manager = SyncManager()