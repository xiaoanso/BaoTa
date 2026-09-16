# -*- coding: utf-8 -*-
"""deploy_targets 隔离字段。通过 import 官方路径拿 db，不改官方建表语句。"""


def ensure_target_columns():
    import sqlite3
    import public

    db_file = public.get_panel_path() + "/data/db/ssl_data.db"
    conn = sqlite3.connect(db_file)
    try:
        cur = conn.cursor()
        cur.execute("PRAGMA table_info(deploy_targets)")
        names = {row[1] for row in cur.fetchall()}
        if "ssl_hash" not in names:
            cur.execute("ALTER TABLE deploy_targets ADD COLUMN ssl_hash TEXT DEFAULT ''")
        if "auto_deploy" not in names:
            cur.execute("ALTER TABLE deploy_targets ADD COLUMN auto_deploy INTEGER DEFAULT 0")
        conn.commit()
    finally:
        conn.close()
