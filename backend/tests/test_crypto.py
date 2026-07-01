"""Tests for crypto.py: encrypt/decrypt round-trip and key file creation."""

import stat
from pathlib import Path

from app.crypto import _reset_fernet_cache, decrypt, encrypt, ensure_key


def test_ensure_key_creates_file(tmp_path: Path, monkeypatch) -> None:  # type: ignore[type-arg]
    """ensure_key() creates secret.key in DATA_DIR/config/ if absent."""
    import app.crypto as crypto_mod

    key_path = tmp_path / "config" / "secret.key"
    monkeypatch.setattr(crypto_mod, "_key_path", lambda: key_path)
    _reset_fernet_cache()

    assert not key_path.exists()
    ensure_key()
    assert key_path.exists()
    # File must not be empty
    assert len(key_path.read_bytes()) > 0


def test_key_file_mode_0600(tmp_path: Path, monkeypatch) -> None:  # type: ignore[type-arg]
    """The key file is created with permissions 0600 (owner read/write only)."""
    import app.crypto as crypto_mod

    key_path = tmp_path / "config" / "secret.key"
    monkeypatch.setattr(crypto_mod, "_key_path", lambda: key_path)
    _reset_fernet_cache()

    ensure_key()
    mode = oct(stat.S_IMODE(key_path.stat().st_mode))
    assert mode == "0o600", f"Expected 0o600, got {mode}"


def test_ensure_key_idempotent(tmp_path: Path, monkeypatch) -> None:  # type: ignore[type-arg]
    """Calling ensure_key() twice does not overwrite the existing key."""
    import app.crypto as crypto_mod

    key_path = tmp_path / "config" / "secret.key"
    monkeypatch.setattr(crypto_mod, "_key_path", lambda: key_path)
    _reset_fernet_cache()

    ensure_key()
    first_key = key_path.read_bytes()
    ensure_key()
    second_key = key_path.read_bytes()
    assert first_key == second_key


def test_encrypt_decrypt_round_trip(tmp_path: Path, monkeypatch) -> None:  # type: ignore[type-arg]
    """encrypt() then decrypt() returns the original plaintext."""
    import app.crypto as crypto_mod

    key_path = tmp_path / "config" / "secret.key"
    monkeypatch.setattr(crypto_mod, "_key_path", lambda: key_path)
    _reset_fernet_cache()
    ensure_key()

    plaintext = "super-secret-api-key-value-12345"
    ciphertext = encrypt(plaintext)
    assert ciphertext != plaintext  # it's actually encrypted
    assert decrypt(ciphertext) == plaintext


def test_ciphertext_is_not_plaintext(tmp_path: Path, monkeypatch) -> None:  # type: ignore[type-arg]
    """The ciphertext does not contain the plaintext."""
    import app.crypto as crypto_mod

    key_path = tmp_path / "config" / "secret.key"
    monkeypatch.setattr(crypto_mod, "_key_path", lambda: key_path)
    _reset_fernet_cache()
    ensure_key()

    plaintext = "my-secret"
    ciphertext = encrypt(plaintext)
    assert plaintext not in ciphertext
