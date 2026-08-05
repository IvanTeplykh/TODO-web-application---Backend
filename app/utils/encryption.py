import base64
import hashlib
from typing import Optional
from cryptography.fernet import Fernet
from app.core.config import settings

def _get_fernet_key() -> bytes:
    key_bytes = hashlib.sha256(settings.SECRET_KEY.encode("utf-8")).digest()
    return base64.urlsafe_b64encode(key_bytes)

fernet = Fernet(_get_fernet_key())

def encrypt_text(plain_text: Optional[str]) -> Optional[str]:
    if plain_text is None:
        return None
    return fernet.encrypt(plain_text.encode("utf-8")).decode("utf-8")

def decrypt_text(cipher_text: Optional[str]) -> Optional[str]:
    if cipher_text is None:
        return None
    try:
        return fernet.decrypt(cipher_text.encode("utf-8")).decode("utf-8")
    except Exception:
        return cipher_text

def compute_hash(text: Optional[str]) -> Optional[str]:
    if text is None:
        return None
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
