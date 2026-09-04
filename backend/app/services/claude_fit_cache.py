import os
import sqlite3
import hashlib
import json
import logging
import threading
from pathlib import Path
from typing import Optional, Tuple, Dict, Any

logger = logging.getLogger("claude_fit_cache")
ROOT_DIR = Path(__file__).resolve().parent.parent.parent.parent
DEFAULT_DB_PATH = ROOT_DIR / "artifacts" / "claude_fit_cache.sqlite3"


class ClaudeFitCache:
    """
    Persistent, thread-safe, SQLite-backed cache for Claude Strategic Fit scores.
    Features:
      - Staleness detection via SHA-256 payload hash (value, scope, deadline, compliance, win prob, neighbors).
      - Thread-safe connection handling.
      - Full bypass support for override / what-if simulations.
    """

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = Path(db_path or DEFAULT_DB_PATH)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        return conn

    def _init_db(self):
        with self._lock, self._get_connection() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS claude_fit_cache (
                    tender_no TEXT PRIMARY KEY,
                    data_hash TEXT NOT NULL,
                    strategic_fit REAL NOT NULL,
                    strategic_rationale TEXT NOT NULL,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    cached_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_fit_cache_hash ON claude_fit_cache(tender_no, data_hash)")
            conn.commit()

    @staticmethod
    def compute_payload_hash(
        tender_no: str,
        tender_name: str,
        organization: str,
        tender_value: float,
        compliance_status: str,
        ml_win_prob: float,
        similar_tenders: Optional[list] = None,
        deadline: Optional[str] = None
    ) -> str:
        """
        Computes a deterministic SHA-256 hash over the tender's core business payload.
        Any change to value, scope/title, authority, compliance, ML prob, or deadline
        alters this hash, flagging the cached score as stale.
        """
        norm_neighbors = []
        if similar_tenders:
            for s in similar_tenders[:3]:
                norm_neighbors.append({
                    "no": str(s.get("tender_no", "")).strip(),
                    "sim": round(float(s.get("similarity", 0.0)), 3),
                    "out": str(s.get("outcome", "")).strip()
                })

        payload = {
            "no": str(tender_no).strip().upper(),
            "name": str(tender_name).strip().lower(),
            "org": str(organization).strip().lower(),
            "val": round(float(tender_value or 0.0), 2),
            "status": str(compliance_status).strip().upper(),
            "ml_prob": round(float(ml_win_prob or 0.0), 3),
            "deadline": str(deadline).strip() if deadline else "",
            "neighbors": norm_neighbors
        }
        serialized = json.dumps(payload, sort_keys=True, separators=(',', ':'))
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()

    def get(self, tender_no: str, current_hash: str) -> Optional[Tuple[float, str]]:
        """
        Retrieves cached (strategic_fit, rationale) if tender_no exists and data_hash matches current_hash.
        Returns None on cache miss or hash mismatch (staleness detected).
        """
        tender_key = str(tender_no).strip().upper()
        try:
            with self._lock, self._get_connection() as conn:
                cursor = conn.execute(
                    "SELECT data_hash, strategic_fit, strategic_rationale FROM claude_fit_cache WHERE tender_no = ?",
                    (tender_key,)
                )
                row = cursor.fetchone()
                if row:
                    if row["data_hash"] == current_hash:
                        logger.info(f"[ClaudeFitCache][HIT] Reusing fresh cached score for tender {tender_key}")
                        return float(row["strategic_fit"]), str(row["strategic_rationale"])
                    else:
                        logger.info(f"[ClaudeFitCache][STALE] Underlying data changed for tender {tender_key} (hash mismatch). Re-scoring required.")
                        return None
                return None
        except Exception as e:
            logger.warning(f"[ClaudeFitCache] Cache read error for {tender_key}: {e}")
            return None

    def set(
        self,
        tender_no: str,
        data_hash: str,
        strategic_fit: float,
        strategic_rationale: str,
        input_tokens: int = 0,
        output_tokens: int = 0
    ) -> bool:
        """
        Persists newly computed strategic fit score and rationale.
        """
        tender_key = str(tender_no).strip().upper()
        try:
            with self._lock, self._get_connection() as conn:
                conn.execute("""
                    INSERT INTO claude_fit_cache (
                        tender_no, data_hash, strategic_fit, strategic_rationale,
                        input_tokens, output_tokens, cached_at
                    ) VALUES (?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
                    ON CONFLICT(tender_no) DO UPDATE SET
                        data_hash = excluded.data_hash,
                        strategic_fit = excluded.strategic_fit,
                        strategic_rationale = excluded.strategic_rationale,
                        input_tokens = excluded.input_tokens,
                        output_tokens = excluded.output_tokens,
                        cached_at = CURRENT_TIMESTAMP
                """, (
                    tender_key,
                    data_hash,
                    float(strategic_fit),
                    str(strategic_rationale),
                    int(input_tokens),
                    int(output_tokens)
                ))
                conn.commit()
                logger.info(f"[ClaudeFitCache][STORED] Cached strategic fit ({strategic_fit:.2f}) for tender {tender_key}")
                return True
        except Exception as e:
            logger.warning(f"[ClaudeFitCache] Cache write error for {tender_key}: {e}")
            return False

    def invalidate(self, tender_no: str) -> bool:
        """
        Deletes cached entry for a tender to force a re-score.
        """
        tender_key = str(tender_no).strip().upper()
        try:
            with self._lock, self._get_connection() as conn:
                conn.execute("DELETE FROM claude_fit_cache WHERE tender_no = ?", (tender_key,))
                conn.commit()
                return True
        except Exception as e:
            logger.warning(f"[ClaudeFitCache] Cache invalidate error for {tender_key}: {e}")
            return False

    def clear(self):
        """Clears all entries (useful for test isolation)."""
        try:
            with self._lock, self._get_connection() as conn:
                conn.execute("DELETE FROM claude_fit_cache")
                conn.commit()
        except Exception as e:
            logger.warning(f"[ClaudeFitCache] Clear error: {e}")
