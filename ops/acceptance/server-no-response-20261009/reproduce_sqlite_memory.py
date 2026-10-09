"""Local synthetic SQLite reproduction; never reads production chat data."""
import gc
import importlib.util
import platform
import resource
import sqlite3
import sys
import tempfile
from pathlib import Path

spec = importlib.util.spec_from_file_location("store", sys.argv[1])
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
with tempfile.TemporaryDirectory() as directory:
    store = module.DurableChatRunStore(Path(directory) / "runs.db")
    conn = sqlite3.connect(store.path)
    conn.execute("CREATE TABLE padding (value TEXT)")
    conn.executemany("INSERT INTO padding VALUES (?)", (("x" * 4000,) for _ in range(4000)))
    conn.commit()
    conn.close()
    del conn
    gc.collect()
    def measure(label):
        divisor = 1048576 if platform.system() == "Darwin" else 1024
        print(label, "peak_rss_mib", round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / divisor, 1),
              "live_connections", sum(isinstance(item, sqlite3.Connection) for item in gc.get_objects()))
    measure("baseline")
    for _ in range(200):
        with store._connect() as conn:
            conn.execute("SELECT SUM(LENGTH(value)) FROM padding").fetchone()
    del conn
    measure("after_200_reads")
