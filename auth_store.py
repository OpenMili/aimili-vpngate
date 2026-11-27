"""Password hashing shared by the web service and native installer."""
from __future__ import annotations

import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2-sha256"
ITERATIONS = 600_000


def set_password(config: dict, password: str) -> None:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, ITERATIONS)
    config["password_hash"] = f"{ALGORITHM}${ITERATIONS}${salt.hex()}${digest.hex()}"
    config.pop("password", None)


def verify_password(config: dict, password: str) -> bool:
    try:
        algorithm, iterations, salt_hex, digest_hex = config["password_hash"].split("$")
        count = int(iterations)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
        if algorithm != ALGORITHM or not 100_000 <= count <= 1_000_000 or len(salt) < 16 or len(expected) != 32:
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, count)
        return hmac.compare_digest(expected, digest)
    except (KeyError, ValueError, AttributeError, TypeError):
        return False
