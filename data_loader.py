import pandas as pd
from sqlalchemy import create_engine, text
from sqlalchemy.engine import URL
from dotenv import load_dotenv
import os
import time
import threading

load_dotenv()

def get_engine():
    connection_url = URL.create(
        drivername="mysql+mysqlconnector",
        username=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        database=os.getenv("DB_NAME"),
        port=3306
    )
    return create_engine(connection_url)


def detect_separator(filepath):
    """Auto detect if file uses comma or semicolon"""
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        first_line = f.readline()
        semicolons = first_line.count(';')
        commas = first_line.count(',')
        return ';' if semicolons > commas else ','


def clean_dataframe(df):
    """Clean column names and data"""
    df.columns = [
        col.strip().lower()
           .replace(" ", "_")
           .replace("-", "_")
           .replace("(", "")
           .replace(")", "")
           .replace("/", "_")
        for col in df.columns
    ]
    df.dropna(how='all', inplace=True)
    for col in df.select_dtypes(include='object').columns:
        df[col] = df[col].astype(str).str.strip()
    return df


def get_table_name_from_file(filename):
    """Auto generate clean table name from filename"""
    name = os.path.splitext(filename)[0]
    name = name.lower()
    name = name.replace(" ", "_").replace("-", "_")
    name = ''.join(c for c in name if c.isalnum() or c == '_')
    return name


def load_csv_to_mysql(filepath, table_name=None):
    """
    Load a single CSV into MySQL.
    If table_name not provided, auto generates from filename.
    """
    try:
        if not os.path.exists(filepath):
            print(f"[Loader] File not found: {filepath}")
            return False

        # Auto generate table name if not provided
        if not table_name:
            filename = os.path.basename(filepath)
            table_name = get_table_name_from_file(filename)

        sep = detect_separator(filepath)
        print(f"[Loader] Detected separator: '{sep}'")

        df = pd.read_csv(
            filepath, sep=sep,
            encoding='utf-8', encoding_errors='ignore'
        )

        print(f"[Loader] Found columns: {list(df.columns)}")
        print(f"[Loader] Total rows: {len(df)}")

        df = clean_dataframe(df)
        print(f"[Loader] Clean columns: {list(df.columns)}")

        engine = get_engine()
        df.to_sql(
            table_name, con=engine,
            if_exists='replace', index=False
        )

        # Log this file in our tracking table
        _log_loaded_file(filepath, table_name, len(df))

        print(f"[Loader] ✅ Loaded {len(df)} rows → '{table_name}'")
        return True

    except Exception as e:
        print(f"[Loader] ❌ Error loading {filepath}: {e}")
        return False


def load_multiple_files(file_table_map):
    """Load multiple files at once"""
    results = {}
    for filepath, table_name in file_table_map.items():
        print(f"\n[Loader] Loading {filepath} → {table_name}")
        results[table_name] = load_csv_to_mysql(filepath, table_name)

    print("\n[Loader] ===== Summary =====")
    for table, success in results.items():
        status = "✅ Success" if success else "❌ Failed"
        print(f"  {table}: {status}")
    return results


def load_all_files_in_folder(folder="data"):
    """
    Automatically loads ALL CSV files in a folder.
    No need to specify filenames manually.
    """
    if not os.path.exists(folder):
        print(f"[Loader] Folder '{folder}' not found")
        return {}

    results = {}
    files = [
        f for f in os.listdir(folder)
        if f.lower().endswith(('.csv', '.xlsx', '.xls'))
    ]

    if not files:
        print(f"[Loader] No CSV files found in '{folder}'")
        return {}

    print(f"[Loader] Found {len(files)} files in '{folder}'")

    for filename in files:
        filepath = os.path.join(folder, filename)
        table_name = get_table_name_from_file(filename)
        print(f"\n[Loader] Auto loading: {filename} → {table_name}")
        results[table_name] = load_csv_to_mysql(filepath, table_name)

    return results


def _ensure_tracking_table():
    """Create file tracking table if not exists"""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE IF NOT EXISTS _loaded_files (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    filepath VARCHAR(500),
                    table_name VARCHAR(200),
                    row_count INT,
                    loaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    file_modified FLOAT
                )
            """))
            conn.commit()
    except Exception as e:
        print(f"[Loader] Tracking table error: {e}")


def _log_loaded_file(filepath, table_name, row_count):
    """Track which files have been loaded"""
    try:
        _ensure_tracking_table()
        modified_time = os.path.getmtime(filepath)
        engine = get_engine()
        with engine.connect() as conn:
            # Remove old entry for this file
            conn.execute(
                text("DELETE FROM _loaded_files WHERE filepath = :fp"),
                {"fp": filepath}
            )
            # Add new entry
            conn.execute(text("""
                INSERT INTO _loaded_files
                (filepath, table_name, row_count, file_modified)
                VALUES (:fp, :tn, :rc, :fm)
            """), {
                "fp": filepath,
                "tn": table_name,
                "rc": row_count,
                "fm": modified_time
            })
            conn.commit()
    except Exception as e:
        print(f"[Loader] Logging error: {e}")

def _file_needs_reload(filepath):
    """
    Check if file needs reloading.
    Only reload if file modified time is 
    significantly newer than last load time.
    """
    try:
        if not os.path.exists(filepath):
            return False

        current_modified = os.path.getmtime(filepath)

        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT file_modified 
                    FROM _loaded_files
                    WHERE filepath = :fp
                """),
                {"fp": filepath}
            ).fetchone()

            if not result:
                return True  # Never loaded

            last_modified = float(result[0])
            diff = current_modified - last_modified

            # Only reload if file is more than 5 minutes newer
            # This prevents the infinite reload loop
            return diff > 300

    except Exception:
        return True


def get_loaded_tables():
    """Returns list of all tables with row counts"""
    try:
        engine = get_engine()
        with engine.connect() as conn:
            result = conn.execute(text("SHOW TABLES"))
            tables = [row[0] for row in result]

        table_info = []
        for table in tables:
            # Skip internal tracking tables
            if table.startswith('_'):
                continue
            with engine.connect() as conn:
                count = conn.execute(
                    text(f"SELECT COUNT(*) FROM `{table}`")
                ).fetchone()[0]
            table_info.append({
                "name": table,
                "rows": count
            })

        return table_info

    except Exception as e:
        print(f"[Loader] Error: {e}")
        return []


# ── File Watcher ──────────────────────────────────────────────

class DataFolderWatcher:
    """
    Watches the data/ folder for new or changed files.
    Automatically loads them into MySQL.
    No manual work needed.
    """

    def __init__(self, folder="data", interval=30):
        self.folder = folder
        self.interval = interval  # Check every 30 seconds
        self.running = False
        self.thread = None
        # Track relationship refresh callback
        self.on_new_file = None

    def start(self):
        """Start watching in background thread"""
        _ensure_tracking_table()
        self.running = True
        self.thread = threading.Thread(
            target=self._watch_loop,
            daemon=True
        )
        self.thread.start()
        print(f"[Watcher] 👀 Watching '{self.folder}' folder "
              f"every {self.interval}s")

    def stop(self):
        self.running = False
        print("[Watcher] Stopped")

    def _watch_loop(self):
        while self.running:
            try:
                self._check_for_changes()
            except Exception as e:
                print(f"[Watcher] Error: {e}")
            time.sleep(self.interval)

    def _check_for_changes(self):
        if not os.path.exists(self.folder):
            return

        files = [
            f for f in os.listdir(self.folder)
            if f.lower().endswith(('.csv', '.xlsx', '.xls'))
            and not f.startswith('_')
        ]

        new_files_found = False

        for filename in files:
            filepath = os.path.join(self.folder, filename)

            if _file_needs_reload(filepath):
                print(f"\n[Watcher] 🆕 New/changed file: {filename}")
                table_name = get_table_name_from_file(filename)
                success = load_csv_to_mysql(filepath, table_name)

                if success:
                    print(f"[Watcher] ✅ Auto loaded: {filename} → {table_name}")
                    new_files_found = True

                    # Trigger relationship refresh if callback set
                    if self.on_new_file:
                        self.on_new_file(table_name)

        if new_files_found:
            print("[Watcher] 🔄 Relationships will be refreshed")


# Global watcher instance
watcher = DataFolderWatcher(folder="data", interval=30)