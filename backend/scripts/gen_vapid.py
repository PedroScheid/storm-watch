"""Gera as chaves VAPID para Web Push e imprime no formato do .env.

Uso:
    python scripts/gen_vapid.py

Copie as duas linhas para o seu backend/.env.
- VAPID_PUBLIC_KEY  -> chave pública (o frontend busca via /vapid-public-key)
- VAPID_PRIVATE_KEY -> chave privada (fica só no backend)
"""

from __future__ import annotations

import base64

from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat


def b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def main() -> None:
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()

    # Chave pública = ponto não-comprimido (o "applicationServerKey" do navegador).
    pub_raw = public_key.public_bytes(Encoding.X962, PublicFormat.UncompressedPoint)
    # Chave privada = valor escalar de 32 bytes.
    priv_raw = private_key.private_numbers().private_value.to_bytes(32, "big")

    print("# Cole no backend/.env:")
    print(f"VAPID_PUBLIC_KEY={b64url(pub_raw)}")
    print(f"VAPID_PRIVATE_KEY={b64url(priv_raw)}")


if __name__ == "__main__":
    main()
