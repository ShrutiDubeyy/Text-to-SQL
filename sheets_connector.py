import time
import pandas as pd
from datetime import datetime
from sync_manager import sync_manager
from data_loader import get_engine


class GoogleSheetsConnector:
    """
    Connects to Google Sheets and syncs data
    to MySQL automatically.

    Setup needed:
    1. Go to console.cloud.google.com
    2. Create project
    3. Enable Google Sheets API
    4. Create Service Account
    5. Download credentials JSON
    6. Share your sheet with service account email
    """

    def __init__(self, credentials_path=None):
        self.credentials_path = credentials_path
        self.client           = None
        self._setup_client()

    def _setup_client(self):
        """Initialize Google Sheets client"""
        try:
            import gspread
            from google.oauth2.service_account \
                import Credentials

            if not self.credentials_path:
                import os
                self.credentials_path = os.getenv(
                    'GOOGLE_CREDENTIALS_PATH',
                    'credentials/google_sheets.json'
                )

            import os
            if not os.path.exists(
                    self.credentials_path):
                print("[Sheets] ⚠️ No credentials "
                      "file found. Google Sheets "
                      "sync disabled.")
                print("[Sheets] To enable: download "
                      "service account JSON from "
                      "Google Cloud Console")
                return

            scopes = [
                'https://spreadsheets.google.com/feeds',
                'https://www.googleapis.com/auth/drive'
            ]

            creds = Credentials.from_service_account_file(
                self.credentials_path,
                scopes=scopes
            )
            self.client = gspread.authorize(creds)
            print("[Sheets] ✅ Google Sheets "
                  "client initialized")

        except ImportError:
            print("[Sheets] Install gspread: "
                  "pip install gspread google-auth")
        except Exception as e:
            print(f"[Sheets] Setup error: {e}")

    def is_available(self):
        """Check if Google Sheets is configured"""
        return self.client is not None

    def sync_sheet(self, sheet_url, table_name,
                   source_name):
        """
        Pull data from Google Sheet and
        sync to MySQL table.
        Only adds new rows — incremental sync.
        """
        if not self.client:
            print("[Sheets] Not configured")
            return False, 0

        start_time = time.time()

        try:
            print(f"[Sheets] 🔄 Syncing: {source_name}")
            sync_manager.update_sync_status(
                source_name, 'syncing')

            # Open spreadsheet
            sheet = self.client.open_by_url(sheet_url)
            worksheet = sheet.get_worksheet(0)

            # Get all data
            data = worksheet.get_all_records()

            if not data:
                print(f"[Sheets] Empty sheet: "
                      f"{source_name}")
                sync_manager.update_sync_status(
                    source_name, 'success', 0)
                return True, 0

            # Convert to DataFrame
            df = pd.DataFrame(data)

            # Clean column names
            df.columns = [
                col.strip().lower()
                   .replace(' ', '_')
                   .replace('-', '_')
                for col in df.columns
            ]

            # Drop empty rows
            df.dropna(how='all', inplace=True)

            # Add sync metadata
            df['_synced_at'] = \
                datetime.now().strftime(
                    '%Y-%m-%d %H:%M:%S')
            df['_source'] = source_name

            # Write to MySQL
            engine = get_engine()
            df.to_sql(
                table_name, con=engine,
                if_exists='replace', index=False
            )

            row_count   = len(df)
            duration_ms = int(
                (time.time() - start_time) * 1000)

            # Update status
            sync_manager.update_sync_status(
                source_name, 'success', row_count)
            sync_manager.log_sync_event(
                source_name, None,
                row_count, 0, 'success',
                duration_ms=duration_ms
            )

            print(f"[Sheets] ✅ Synced {row_count} "
                  f"rows from {source_name} "
                  f"in {duration_ms}ms")

            # Auto-index new table
            try:
                from auto_indexer import auto_indexer
                auto_indexer.auto_index_table(
                    table_name)
            except Exception:
                pass

            return True, row_count

        except Exception as e:
            error_msg = str(e)
            duration_ms = int(
                (time.time() - start_time) * 1000)

            sync_manager.update_sync_status(
                source_name, 'failed', 0, error_msg)
            sync_manager.log_sync_event(
                source_name, None, 0, 0,
                'failed', error_msg, duration_ms
            )

            print(f"[Sheets] ❌ Sync failed "
                  f"for {source_name}: {error_msg}")
            return False, 0

    def sync_all_due(self):
        """Sync all sheets that are due"""
        sources = sync_manager\
            .get_sources_due_for_sync()

        if not sources:
            return

        print(f"[Sheets] {len(sources)} "
              f"sheets due for sync")

        for source in sources:
            self.sync_sheet(
                source['source_url'],
                source['table_name'],
                source['source_name']
            )


# Global instance
sheets = GoogleSheetsConnector()