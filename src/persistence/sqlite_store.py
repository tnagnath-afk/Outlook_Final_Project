import sqlite3

DB_PATH = "data/db/traceability.db"


def init_db():

    conn = sqlite3.connect(DB_PATH)

    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS requirements(
        req_id TEXT PRIMARY KEY,
        category TEXT,
        text TEXT,
        source_section TEXT,
        status TEXT
    )
    """)

    cur.execute("""
    CREATE TABLE IF NOT EXISTS testcases(
        tc_id TEXT PRIMARY KEY,
        req_id TEXT,
        objective TEXT
    )
    """)

    conn.commit()
    conn.close()


def save_requirements(requirements):

    conn = sqlite3.connect(DB_PATH)

    cur = conn.cursor()

    for r in requirements:

        cur.execute("""
        INSERT OR REPLACE INTO requirements
        VALUES (?,?,?,?,?)
        """, (
            r["req_id"],
            r["category"],
            r["text"],
            r["source_section"],
            r["status"]
        ))

    conn.commit()
    conn.close()


def save_testcases(testcases):

    conn = sqlite3.connect(DB_PATH)

    cur = conn.cursor()

    for t in testcases:

        cur.execute("""
        INSERT OR REPLACE INTO testcases
        VALUES (?,?,?)
        """, (
            t["tc_id"],
            t["req_id"],
            t["objective"]
        ))

    conn.commit()
    conn.close()