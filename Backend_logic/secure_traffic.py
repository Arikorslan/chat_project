from __future__ import annotations

import secrets
from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC

DEFAULT_ITERATIONS = 200_000
KEY_LENGTH = 32
NONCE_LENGTH = 12


class SecureTraffic:
    def __init__(self, key: bytes) -> None:
        self.key = key
        self.aesgcm = AESGCM(key)

    @classmethod
    def derive_key(cls, password: bytes, salt: bytes) -> bytes:
        kdf = PBKDF2HMAC(
            algorithm=hashes.SHA256(),
            length=KEY_LENGTH,
            salt=salt,
            iterations=DEFAULT_ITERATIONS,
        )
        return kdf.derive(password)

    @classmethod
    def from_password(cls, password: bytes, salt: bytes) -> "SecureTraffic":
        return cls(cls.derive_key(password, salt))

    def encrypt(self, plaintext: bytes) -> bytes:
        nonce = secrets.token_bytes(NONCE_LENGTH)
        ciphertext = self.aesgcm.encrypt(nonce, plaintext, None)
        return nonce + ciphertext

    def decrypt(self, ciphertext: bytes) -> bytes:
        if len(ciphertext) < NONCE_LENGTH + 16:
            raise InvalidTag("Ciphertext is too short")
        nonce = ciphertext[:NONCE_LENGTH]
        encrypted = ciphertext[NONCE_LENGTH:]
        return self.aesgcm.decrypt(nonce, encrypted, None)
