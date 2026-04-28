from __future__ import annotations

import base64
import binascii
from datetime import datetime, timezone

_ALPHABET = "123456789ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz"
_INDEX = {ch: idx for idx, ch in enumerate(_ALPHABET)}


def b58decode(value: str) -> bytes:
    value = str(value or "").strip()
    if not value:
        return b""
    number = 0
    for char in value:
        if char not in _INDEX:
            raise ValueError("invalid_base58")
        number = number * 58 + _INDEX[char]
    data = number.to_bytes((number.bit_length() + 7) // 8, "big") if number else b""
    leading = len(value) - len(value.lstrip("1"))
    return b"\x00" * leading + data


def b58encode(data: bytes) -> str:
    data = bytes(data or b"")
    if not data:
        return ""
    number = int.from_bytes(data, "big")
    chars: list[str] = []
    while number:
        number, rem = divmod(number, 58)
        chars.append(_ALPHABET[rem])
    leading = len(data) - len(data.lstrip(b"\x00"))
    return "1" * leading + "".join(reversed(chars or ["1"]))


def decode_signature(value: str) -> bytes:
    value = str(value or "").strip()
    if not value:
        raise ValueError("signature_required")
    decoders = (b58decode, base64.b64decode, binascii.unhexlify)
    for decoder in decoders:
        try:
            decoded = decoder(value)
        except Exception:
            continue
        if len(decoded) == 64:
            return decoded
    raise ValueError("invalid_signature_encoding")


def build_login_message(*, wallet: str, nonce: str, app_id: str = "ava_box", issued_at: int = 0) -> str:
    issued = datetime.fromtimestamp(issued_at or 0, tz=timezone.utc).isoformat().replace("+00:00", "Z") if issued_at else ""
    return "\n".join(
        [
            "Ava DeviceKit wants you to sign in.",
            f"Wallet: {wallet}",
            f"App: {app_id or 'ava_box'}",
            f"Nonce: {nonce}",
            f"Issued At: {issued}",
            "Only sign this message from the Ava customer portal.",
        ]
    )


def verify_solana_signature(*, wallet: str, message: str, signature: str) -> bool:
    pubkey = b58decode(wallet)
    if len(pubkey) != 32:
        raise ValueError("invalid_wallet_public_key")
    sig = decode_signature(signature)
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except Exception as exc:  # pragma: no cover - dependency boundary
        raise RuntimeError("cryptography_required_for_wallet_signature") from exc
    try:
        Ed25519PublicKey.from_public_bytes(pubkey).verify(sig, message.encode("utf-8"))
        return True
    except Exception:
        return False
