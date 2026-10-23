# -*- coding: utf-8 -*-
"""Everything 式秒级文件搜索：SQLite FTS5(trigram) 全盘索引引擎 + 可选对接 Everything。

- 后台并行扫描磁盘建立索引（SQLite FTS5 trigram，支持中文任意子串）；
- 搜索毫秒级返回（≥3 字符走 FTS，短词回退 LIKE）；
- 索引重建为「建新表 → 原子换表」，搜索期间旧索引仍可用；
- 若本机装有 Everything 并开启 HTTP 服务，可优先走 Everything 接口。
"""

from __future__ import annotations

import json
import os
import queue
import sqlite3
import sys
import threading
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Dict, List, Optional

_SKIP_DIRS = {
    "windows", "winnt", "program files", "program files (x86)", "programdata",
    "$recycle.bin", "system volume information", "node_modules", "appdata",
    "tmp", "temp", ".git", "__pycache__", ".cache", ".thumbnails",
    "recovery", "perflogs", "msocache", "config.msi",
}


def _is_link(path: str) -> bool:
    """目录是否为符号链接或 Windows 目录联接（junction），避免遍历成环。"""
    try:
        if os.path.islink(path):
            return True
        if sys.platform == "win32":
            import stat as _stat
            st = os.lstat(path)
            return bool(getattr(st, "st_file_attributes", 0) & _stat.FILE_ATTRIBUTE_REPARSE_POINT)
        return False
    except OSError:
        return False


def default_roots() -> List[str]:
    """默认索引根：Windows 为所有盘符，其他平台为用户主目录。"""
    if sys.platform == "win32":
        import ctypes
        roots = []
        bitmask = ctypes.windll.kernel32.GetLogicalDrives()
        for i in range(26):
            if bitmask & (1 << i):
                roots.append(chr(65 + i) + ":\\")
        return roots or [os.path.expanduser("~")]
    return [os.path.expanduser("~")]


class FastIndex:
    """SQLite FTS5 文件索引。线程模型：重建在后台线程，搜索在主线程（WAL 并发读）。"""

    def __init__(self, db_path: Optional[str] = None, roots: Optional[List[str]] = None):
        if db_path is None:
            base = os.path.join(os.path.expanduser("~"), ".desktop_assistant")
            os.makedirs(base, exist_ok=True)
            db_path = os.path.join(base, "file_index.db")
        self.db_path = db_path
        self.roots = roots or default_roots()
        self._fts = False
        self._check_fts()

    # ------------------------------------------------------------------
    def _check_fts(self) -> None:
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(name, tokenize='trigram')"
            )
            conn.execute("DROP TABLE IF EXISTS _fts_probe")
            conn.commit()
            conn.close()
            self._fts = True
        except sqlite3.OperationalError:
            self._fts = False

    def stats(self) -> Dict:
        try:
            conn = sqlite3.connect(self.db_path)
            count = conn.execute("SELECT COUNT(*) FROM files").fetchone()[0]
            conn.close()
        except sqlite3.OperationalError:
            count = 0
        built_at = ""
        try:
            with open(self.db_path + ".meta", "r", encoding="utf-8") as f:
                built_at = json.load(f).get("built_at", "")
        except (OSError, ValueError):
            pass
        size_mb = 0.0
        if os.path.exists(self.db_path):
            size_mb = os.path.getsize(self.db_path) / (1024 * 1024)
        return {"count": count, "size_mb": round(size_mb, 1), "built_at": built_at, "fts": self._fts}

    # ------------------------------------------------------------------
    def rebuild(self, roots: Optional[List[str]] = None,
                progress: Optional[Callable[[int], None]] = None,
                cancel: Optional[Callable[[], bool]] = None,
                workers: Optional[int] = None) -> int:
        """重建索引（阻塞，请在后台线程调用）。返回索引文件数。"""
        roots = roots or self.roots
        workers = workers or max(2, min(8, (os.cpu_count() or 4)))
        conn = sqlite3.connect(self.db_path, check_same_thread=False)
        try:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("DROP TABLE IF EXISTS files_new")
            conn.execute("CREATE TABLE files_new(path TEXT PRIMARY KEY, name TEXT, "
                         "ext TEXT, size INTEGER, mtime REAL)")
            if self._fts:
                conn.execute("DROP TABLE IF EXISTS files_fts_new")
                conn.execute("CREATE VIRTUAL TABLE files_fts_new USING fts5(name, path, "
                             "tokenize='trigram')")

            q: queue.Queue = queue.Queue(maxsize=4000)
            stop = threading.Event()

            def produce(root: str) -> None:
                for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
                    if stop.is_set():
                        return
                    # 跳过符号链接/目录联接（Windows 常见 "Application Data" 等联接环）
                    dirnames[:] = [d for d in dirnames
                                   if d.lower() not in _SKIP_DIRS
                                   and not d.startswith(".")
                                   and not _is_link(os.path.join(dirpath, d))]
                    for fn in filenames:
                        if stop.is_set():
                            return
                        # 带超时入队：取消时消费者已退出，不能永久阻塞在 put 上
                        while not stop.is_set():
                            try:
                                q.put(os.path.join(dirpath, fn), timeout=0.2)
                                break
                            except queue.Full:
                                continue

            count = 0
            batch: List[tuple] = []
            last_report = 0

            def flush() -> None:
                nonlocal batch
                if batch:
                    conn.executemany("INSERT OR IGNORE INTO files_new VALUES (?,?,?,?,?)", batch)
                    batch = []

            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(produce, r) for r in roots]
                pending = set(futures)
                while pending or not q.empty():
                    try:
                        path = q.get(timeout=0.3)
                    except queue.Empty:
                        pending = {f for f in pending if not f.done()}
                        continue
                    if cancel and cancel():
                        stop.set()
                        break
                    try:
                        st = os.stat(path, follow_symlinks=False)
                        size, mtime = st.st_size, st.st_mtime
                    except OSError:
                        continue
                    name = os.path.basename(path)
                    ext = os.path.splitext(name)[1].lower()
                    batch.append((path, name, ext, size, mtime))
                    count += 1
                    if len(batch) >= 2000:
                        flush()
                        if progress and count - last_report >= 20000:
                            last_report = count
                            progress(count)
            flush()
            if progress:
                progress(count)

            # 取消：丢弃新建表，保留旧索引不动（与「旧索引保留」提示一致）
            if cancel and cancel():
                conn.execute("DROP TABLE IF EXISTS files_new")
                if self._fts:
                    conn.execute("DROP TABLE IF EXISTS files_fts_new")
                conn.commit()
                return count

            if self._fts:
                conn.execute("INSERT INTO files_fts_new(rowid, name, path) "
                             "SELECT rowid, name, path FROM files_new")
            conn.commit()

            # 原子换表
            conn.execute("DROP TABLE IF EXISTS files")
            conn.execute("ALTER TABLE files_new RENAME TO files")
            if self._fts:
                conn.execute("DROP TABLE IF EXISTS files_fts")
                conn.execute("ALTER TABLE files_fts_new RENAME TO files_fts")
            conn.commit()

            built_at = time.strftime("%Y-%m-%d %H:%M")
            with open(self.db_path + ".meta", "w", encoding="utf-8") as f:
                json.dump({"built_at": built_at}, f)
            return count
        finally:
            conn.close()

    # ------------------------------------------------------------------
    def search(self, query: str, limit: int = 200, match_path: bool = False) -> List[Dict]:
        """秒级搜索。返回 [{path,name,size}]。索引为空返回 []（由调用方走降级）。"""
        query = (query or "").strip()
        if not query:
            return []
        if not os.path.exists(self.db_path):
            return []
        try:
            conn = sqlite3.connect(self.db_path, timeout=5)
        except sqlite3.OperationalError:
            return []
        try:
            rows = []
            # 优先 FTS（≥3 字符，任意子串，中文可用）
            if self._fts and len(query) >= 3:
                phrase = '"' + query.replace('"', '""') + '"'
                try:
                    rows = conn.execute(
                        "SELECT f.path, f.size, f.name FROM files f "
                        "JOIN files_fts ON files_fts.rowid = f.rowid "
                        "WHERE files_fts MATCH ? ORDER BY f.path LIMIT ?",
                        (phrase, limit)).fetchall()
                except sqlite3.OperationalError:
                    rows = []
            if not rows:
                like_q = query.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                like = f"%{like_q}%"
                col = "path" if match_path else "name"
                rows = conn.execute(
                    f"SELECT path, size, name FROM files WHERE {col} LIKE ? ESCAPE '\\' "
                    "ORDER BY path LIMIT ?", (like, limit)).fetchall()
            return [{"path": r[0], "size": r[1], "name": r[2]} for r in rows]
        except sqlite3.OperationalError:
            return []
        finally:
            conn.close()


class EverythingBackend:
    """对接本机已安装的 Everything（HTTP 服务，默认 127.0.0.1:80）。"""

    BASE = "http://127.0.0.1:80"

    def available(self, timeout: float = 0.6) -> bool:
        try:
            with urllib.request.urlopen(self.BASE + "/?search=*&json=1", timeout=timeout):
                return True
        except Exception:
            return False

    def search(self, query: str, limit: int = 200) -> List[Dict]:
        q = urllib.parse.quote(query)
        url = f"{self.BASE}/?search={q}&json=1&count={limit}&sort=1"
        try:
            with urllib.request.urlopen(url, timeout=3) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except Exception:
            return []
        out = []
        for r in data.get("results", [])[:limit]:
            name = r.get("name", "")
            path = r.get("path", "")
            full = os.path.join(path, name) if path else name
            out.append({"path": full, "name": name, "size": r.get("size", 0)})
        return out
