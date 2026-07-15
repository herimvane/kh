import hashlib
import hmac
import os
import secrets


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return f"pbkdf2_sha256${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    try:
        algorithm, salt_hex, digest_hex = stored.split("$", 2)
        if algorithm != "pbkdf2_sha256":
            return False
        salt = bytes.fromhex(salt_hex)
        bytes.fromhex(digest_hex)
    except (AttributeError, ValueError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 120_000)
    return hmac.compare_digest(digest.hex(), digest_hex)


def new_session_token() -> str:
    return secrets.token_urlsafe(32)


def session_token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
