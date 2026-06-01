import json
import hashlib
import hmac
import time
import pandas as pd
from datetime import datetime
from db import get_connection
from data_loader import get_engine
from sync_manager import sync_manager


class WebhookHandler:
    """
    Receives data from external systems via webhooks.
    External system sends POST → data stored instantly.

    Use cases:
    - Shopify sends new orders
    - Salesforce sends new leads
    - SAP sends inventory updates
    - Any system that supports webhooks
    """

    def __init__(self, secret_key=None):
        import os
        self.secret = secret_key or \
                      os.getenv('SECRET_KEY', 'default')

    def generate_webhook_token(self, source_name):
        """
        Generate unique token for a webhook source.
        External system uses this to authenticate.
        """
        raw = f"{source_name}:{self.secret}"
        return hashlib.sha256(
            raw.encode()).hexdigest()[:32]

    def verify_token(self, source_name, token):
        """Verify webhook token is valid"""
        expected = self.generate_webhook_token(
            source_name)
        return hmac.compare_digest(expected, token)

    def process_webhook(self, source_name,
                        table_name, data,
                        token=None, ip_address=None):
        """
        Process incoming webhook data.

        data format (JSON array):
        [
            {"column1": "value1", "column2": "value2"},
            {"column1": "value3", "column2": "value4"}
        ]
        """
        start_time = time.time()

        try:
            # Validate token if provided
            if token and not self.verify_token(
                    source_name, token):
                self._log_webhook(
                    source_name, table_name,
                    0, ip_address, 'unauthorized')
                return False, "Invalid token"

            # Parse data
            if isinstance(data, str):
                data = json.loads(data)

            if not data:
                return False, "No data received"

            # Convert to DataFrame
            if isinstance(data, list):
                df = pd.DataFrame(data)
            elif isinstance(data, dict):
                df = pd.DataFrame([data])
            else:
                return False, "Invalid data format"

            # Clean columns
            df.columns = [
                col.strip().lower()
                   .replace(' ', '_')
                   .replace('-', '_')
                for col in df.columns
            ]

            # Add metadata
            df['_received_at'] = \
                datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            df['_source'] = source_name

            # Append to MySQL table
            engine = get_engine()
            df.to_sql(
                table_name, con=engine,
                if_exists='append', index=False
            )

            row_count   = len(df)
            duration_ms = int(
                (time.time() - start_time) * 1000)

            # Log success
            self._log_webhook(
                source_name, table_name,
                row_count, ip_address, 'success')

            # Update sync source status
            sync_manager.update_sync_status(
                source_name, 'success', row_count)

            # Invalidate cache
            try:
                from local_engine import cache_clear
                cache_clear()
            except Exception:
                pass

            print(f"[Webhook] ✅ Received "
                  f"{row_count} rows from "
                  f"{source_name} in {duration_ms}ms")

            return True, f"Received {row_count} rows"

        except Exception as e:
            error_msg = str(e)
            self._log_webhook(
                source_name, table_name,
                0, ip_address, 'failed')
            print(f"[Webhook] ❌ Error from "
                  f"{source_name}: {error_msg}")
            return False, error_msg

    def _log_webhook(self, source_name, table_name,
                     rows, ip_address, status):
        """Log webhook event"""
        try:
            conn   = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO _webhook_log
                (source_name, table_name,
                 rows_received, ip_address, status)
                VALUES (%s, %s, %s, %s, %s)
            """, (source_name, table_name,
                  rows, ip_address, status))
            conn.commit()
            cursor.close()
            conn.close()
        except Exception as e:
            print(f"[Webhook] Log error: {e}")

    def get_webhook_logs(self, limit=50):
        """Get recent webhook events"""
        try:
            conn   = get_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute("""
                SELECT * FROM _webhook_log
                ORDER BY received_at DESC
                LIMIT %s
            """, (limit,))
            logs = cursor.fetchall()
            cursor.close()
            conn.close()

            for log in logs:
                if log.get('received_at'):
                    log['received_at'] = \
                        log['received_at'].strftime(
                            '%Y-%m-%d %H:%M:%S')
            return logs
        except Exception as e:
            print(f"[Webhook] Logs error: {e}")
            return []


# Global instance
webhook_handler = WebhookHandler()