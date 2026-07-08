import sqlite3
from backend.app.core.constants import DB_PATH

def init_db(db_path=DB_PATH):
    db_path.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                job_id          TEXT PRIMARY KEY,
                status          TEXT NOT NULL DEFAULT 'pending',
                original_filename TEXT NOT NULL,
                pdf_path        TEXT NOT NULL,
                result_path     TEXT,
                page_count      INTEGER,
                error_message   TEXT,
                created_at      TEXT NOT NULL,
                started_at      TEXT,
                completed_at    TEXT,
                retry_count     INTEGER NOT NULL DEFAULT 0,
                email_recipient TEXT,
                tender_id       INTEGER
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_status ON jobs(status)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_jobs_created_at ON jobs(created_at)")
        
        # Safe migration alterations for existing databases
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN email_recipient TEXT")
        except sqlite3.OperationalError:
            pass
        try:
            conn.execute("ALTER TABLE jobs ADD COLUMN tender_id INTEGER")
        except sqlite3.OperationalError:
            pass
