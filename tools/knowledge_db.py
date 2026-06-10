from __future__ import annotations

from pathlib import Path

from tools.init_knowledge_db import DB_PATH, initialize_knowledge_db


def ensure_knowledge_db(db_path: Path = DB_PATH) -> None:
    if not db_path.exists():
        initialize_knowledge_db(verbose=False)
