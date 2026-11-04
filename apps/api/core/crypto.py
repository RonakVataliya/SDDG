"""Encrypts user content before it is stored. The key lives only in the DATA_ENCRYPTION_KEY environment variable."""
import os
from functools import cache

from cryptography.fernet import Fernet

PREFIX = "enc:"


@cache
def fernet():
    return Fernet(os.environ["DATA_ENCRYPTION_KEY"])  # missing or malformed key: fail loudly


def encrypt(text):
    return None if text is None else PREFIX + fernet().encrypt(text.encode()).decode()


def decrypt(text):
    """Rows saved before encryption was added have no prefix and are returned as they are."""
    return fernet().decrypt(text[len(PREFIX):].encode()).decode() if text.startswith(PREFIX) else text
