from app.core.crypto import compute_hmac_index, decrypt_field, encrypt_field


def encrypt_text(plain_text: str | None) -> str | None:
    return encrypt_field(plain_text)


def decrypt_text(cipher_text: str | None) -> str | None:
    return decrypt_field(cipher_text)


def compute_hash(text: str | None) -> str | None:
    return compute_hmac_index(text)
