#!/usr/bin/env python3
"""Еженедельный бэкап: консистентная копия user_data.db + архив clean/.

Копии лежат в <проект>/backups/, хранятся последние KEEP штук каждого вида.
Копия БД делается через sqlite3.backup (безопасно при работающем боте) и
проверяется PRAGMA integrity_check. Зависит только от стандартной библиотеки.

Восстановление: остановить бота, скопировать нужный user_data_*.db поверх
user_data.db (владелец deploy), запустить бота.
"""

import sqlite3
import sys
import tarfile
from datetime import datetime
from pathlib import Path
from typing import Optional

ROOT = Path(__file__).resolve().parent.parent
KEEP = 8


def backup_db(db_path: Path, out_dir: Path, stamp: str) -> Path:
    dest = out_dir / f"user_data_{stamp}.db"
    src = sqlite3.connect(db_path)
    dst = sqlite3.connect(dest)
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()

    check = sqlite3.connect(dest)
    try:
        result = check.execute("PRAGMA integrity_check").fetchone()[0]
    finally:
        check.close()
    if result != "ok":
        dest.unlink()
        raise RuntimeError(f"integrity_check копии БД: {result}")
    return dest


def backup_clean(clean_dir: Path, out_dir: Path, stamp: str) -> Optional[Path]:
    if not clean_dir.is_dir() or not any(clean_dir.iterdir()):
        return None
    dest = out_dir / f"clean_{stamp}.tar.gz"
    with tarfile.open(dest, "w:gz") as tar:
        tar.add(clean_dir, arcname="clean")
    return dest


def prune(out_dir: Path, pattern: str, keep: int) -> list:
    files = sorted(out_dir.glob(pattern))  # метка времени в имени → порядок по дате
    old = files[:-keep] if len(files) > keep else []
    for f in old:
        f.unlink()
    return old


def run(db_path: Path, clean_dir: Path, out_dir: Path, keep: int = KEEP) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    db_copy = backup_db(db_path, out_dir, stamp)
    print(f"{stamp} БД → {db_copy.name} ({db_copy.stat().st_size} Б)")

    clean_copy = backup_clean(clean_dir, out_dir, stamp)
    if clean_copy:
        print(f"{stamp} clean/ → {clean_copy.name} ({clean_copy.stat().st_size} Б)")
    else:
        print(f"{stamp} clean/ пуста или нет — архив пропущен")

    removed = prune(out_dir, "user_data_*.db", keep) + prune(out_dir, "clean_*.tar.gz", keep)
    if removed:
        print(f"удалено старых копий: {len(removed)}")


if __name__ == "__main__":
    try:
        run(ROOT / "user_data.db", ROOT / "clean", ROOT / "backups")
    except Exception as e:
        print(f"BACKUP FAILED: {type(e).__name__}: {e}", file=sys.stderr)
        sys.exit(1)
