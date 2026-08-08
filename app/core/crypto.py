import base64
import hashlib
import hmac
import os
import uuid
from typing import Optional

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import settings

# Pre-computed key bytes and pre-initialized AESGCM cipher instance
_AES_KEY_BYTES = hashlib.sha256(settings.ENCRYPTION_KEY.encode("utf-8")).digest()
_AESGCM_CIPHER = AESGCM(_AES_KEY_BYTES)
_HMAC_KEY_BYTES = settings.HMAC_KEY.encode("utf-8")

# Fast cache for common small strings (e.g. priorities, booleans)
_HMAC_CACHE: dict[str, str] = {}


def encrypt_field(plaintext: Optional[str]) -> Optional[str]:
    if plaintext is None:
        return None
    nonce = os.urandom(12)
    ciphertext = _AESGCM_CIPHER.encrypt(nonce, plaintext.encode("utf-8"), None)
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
        decrypted = _AESGCM_CIPHER.decrypt(nonce, ct, None)
        return decrypted.decode("utf-8")
    except Exception:
        return ciphertext


def compute_hmac_index(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    normalized = value.strip().lower()
    cached = _HMAC_CACHE.get(normalized)
    if cached is not None:
        return cached
    computed = hmac.new(_HMAC_KEY_BYTES, normalized.encode("utf-8"), hashlib.sha256).hexdigest()
    if len(_HMAC_CACHE) < 5000:
        _HMAC_CACHE[normalized] = computed
    return computed


def generate_uuidv7() -> uuid.UUID:
    return uuid.uuid4()

