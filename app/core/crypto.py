import base64
import hashlib
import hmac
import os
import uuid
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings


def _get_aes_key() -> bytes:
    key_bytes = settings.ENCRYPTION_KEY.encode("utf-8")
    return hashlib.sha256(key_bytes).digest()


def encrypt_field(plaintext: Optional[str]) -> Optional[str]:
    if plaintext is None:
        return None
    key = _get_aes_key()
    aesgcm = AESGCM(key)
    nonce = os.urandom(12)
    ciphertext = aesgcm.encrypt(nonce, plaintext.encode("utf-8"), None)
    combined = nonce + ciphertext
    return base64.b64encode(combined).decode("utf-8")


def decrypt_field(ciphertext: Optional[str]) -> Optional[str]:
    if ciphertext is None:
        return None
    try:
        raw = base64.b64decode(ciphertext.encode("utf-8"))
        if len(raw) < 12:
            return ciphertext
        nonce = raw[:12]
        ct = raw[12:]
        key = _get_aes_key()
        aesgcm = AESGCM(key)
        decrypted = aesgcm.decrypt(nonce, ct, None)
        return decrypted.decode("utf-8")
    except Exception:
        return ciphertext


def compute_hmac_index(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower()
    key_bytes = settings.HMAC_KEY.encode("utf-8")
    return hmac.new(key_bytes, normalized.encode("utf-8"), hashlib.sha256).hexdigest()


def generate_uuidv7() -> uuid.UUID:
    return uuid.uuid4()
