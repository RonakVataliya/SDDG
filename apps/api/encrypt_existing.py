"""Encrypts content saved before DATA_ENCRYPTION_KEY was set up. Safe to run again. Run: python encrypt_existing.py"""
from dotenv import load_dotenv

load_dotenv()
from core import db  # noqa: E402
from core.crypto import PREFIX, encrypt  # noqa: E402

db.init_db()
for table, columns in db.SECRET.items():
    for col in columns:
        for r in db.many(f"SELECT id, {col} AS v FROM {table} WHERE {col} IS NOT NULL AND {col} NOT LIKE '{PREFIX}%'"):
            db.run(f"UPDATE {table} SET {col}=%s WHERE id=%s", encrypt(r["v"]), r["id"])
        print(f"{table}.{col} done")
