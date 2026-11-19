"""Encrypts user content before it is stored. The key lives only in the DATA_ENCRYPTION_KEY environment variable."""
import os
from functools import cache

from cryptography.fernet import Fernet

PREFIX = "enc:"


@cache
def fernet():
    key = os.environ.get("DATA_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("DATA_ENCRYPTION_KEY is not set. Set it in the environment (see apps/api/.env.example).")
    return Fernet(key)  # a malformed key fails loudly here too


def encrypt(text):
    return None if text is None else PREFIX + fernet().encrypt(text.encode()).decode()


def decrypt(text):
    """Rows saved before encryption was added have no prefix and are returned as they are."""
    return fernet().decrypt(text[len(PREFIX):].encode()).decode() if text.startswith(PREFIX) else text
