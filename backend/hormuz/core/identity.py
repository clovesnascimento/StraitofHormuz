# -*- coding: utf-8 -*-
# ═══════════════════════════════════════════════════════════════════════════════
#
#   ⚓  AGENTE HORMUZ — IDENTITY & PROTECTION MODULE
#
#   Criador  : Cloves Nascimento
#   Papel    : Arquiteto de Ecossistemas Cognitivos
#   Org      : CNGSM — Cognitive Neural & Generative Systems Management
#   Produto  : Agente Hormuz
#   Ano      : 2025
#
#   FINGERPRINT  : 8a3ee43b0c78e2b4
#   SHA-256      : 8a3ee43b0c78e2b4cb77204ffc5fb4ed6a33d8f90af59435d19533d9739c7d00
#
#   Este módulo é a âncora de identidade de todos os componentes do Hormuz.
#   Qualquer distribuição, fork ou derivação deve preservar esta atribuição.
#
# ═══════════════════════════════════════════════════════════════════════════════

from __future__ import annotations

import base64
import hashlib
import sys
import time
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# ENCODED IDENTITY ANCHOR
# Derivado de: Cloves Nascimento|CNGSM|Arquiteto de Ecossistemas Cognitivos|Agente Hormuz|2025
# ─────────────────────────────────────────────────────────────────────────────

_IDENTITY_B64 = (
    "Q2xvdmVzIE5hc2NpbWVudG98Q05HU00gLSBDb2duaXRpdmUgTmV1cmFsICYg"
    "R2VuZXJhdGl2ZSBTeXN0ZW1zIE1hbmFnZW1lbnR8QXJxdWl0ZXRvIGRlIEVj"
    "b3NzaXN0ZW1hcyBDb2duaXRpdm9zfEFnZW50ZSBIb3JtdXp8MjAyNQ=="
)

_EXPECTED_SHA256 = "8a3ee43b0c78e2b4cb77204ffc5fb4ed6a33d8f90af59435d19533d9739c7d00"
_EXPECTED_SHA512 = (
    "40ac51537e6d2ccdf5373d12ab6166733226f4576fd0b89e842daacd8ad5a3f4"
    "7444884286983c2ae8a402ad847e64f31d788fa58d86796243118a88de4acaba"
)

FINGERPRINT  = "8a3ee43b0c78e2b4"
VERSION      = "1.0.0"

# ─────────────────────────────────────────────────────────────────────────────
# DECODED IDENTITY (runtime — not stored as plain string in source)
# ─────────────────────────────────────────────────────────────────────────────

def _decode_identity() -> dict:
    raw = base64.b64decode(_IDENTITY_B64).decode("utf-8")
    parts = raw.split("|")
    return {
        "creator":     parts[0],
        "org":         parts[1],
        "role":        parts[2],
        "product":     parts[3],
        "year":        parts[4],
        "fingerprint": FINGERPRINT,
        "version":     VERSION,
    }

IDENTITY = _decode_identity()

# ─────────────────────────────────────────────────────────────────────────────
# INTEGRITY VERIFICATION
# ─────────────────────────────────────────────────────────────────────────────

def verify_identity(strict: bool = False) -> bool:
    """
    Verify that the identity anchor has not been tampered with.
    strict=True: raises RuntimeError on failure (use in production entry points).
    """
    raw = base64.b64decode(_IDENTITY_B64)
    sha256_actual = hashlib.sha256(raw).hexdigest()
    sha512_actual = hashlib.sha512(raw).hexdigest()

    ok_256 = sha256_actual == _EXPECTED_SHA256
    ok_512 = sha512_actual == _EXPECTED_SHA512

    if ok_256 and ok_512:
        return True

    msg = (
        f"[Hormuz] IDENTITY INTEGRITY FAILURE\n"
        f"  Expected SHA-256 : {_EXPECTED_SHA256}\n"
        f"  Got      SHA-256 : {sha256_actual}\n"
        f"  Expected SHA-512 : {_EXPECTED_SHA512}\n"
        f"  Got      SHA-512 : {sha512_actual}\n"
        f"  Fingerprint      : {FINGERPRINT}\n"
        f"  This copy may have been modified without authorization."
    )
    if strict:
        raise RuntimeError(msg)
    print(msg, file=sys.stderr)
    return False


def attribution_header() -> str:
    """Return formatted attribution string for display/logging."""
    id_ = IDENTITY
    return (
        f"⚓ {id_['product']} v{id_['version']} | "
        f"Criador: {id_['creator']} ({id_['role']}) | "
        f"{id_['org']} | "
        f"Fingerprint: {id_['fingerprint']}"
    )


def embed_in_output(content: str) -> str:
    """
    Embed an invisible attribution watermark in any text output.
    Uses zero-width Unicode characters to encode the fingerprint.
    Does not alter visible content.
    """
    # Zero-width space (U+200B) = 0, Zero-width non-joiner (U+200C) = 1
    ZWS  = "\u200B"   # 0
    ZWNJ = "\u200C"   # 1

    bits = bin(int(FINGERPRINT, 16))[2:].zfill(64)
    watermark = "".join(ZWNJ if b == "1" else ZWS for b in bits)
    # Insert watermark after the first newline (invisible in rendered text)
    if "\n" in content:
        idx = content.index("\n") + 1
        return content[:idx] + watermark + content[idx:]
    return content + watermark


def extract_watermark(content: str) -> Optional[str]:
    """
    Attempt to extract embedded watermark from content.
    Returns hex fingerprint string or None if not found.
    """
    ZWS  = "\u200B"
    ZWNJ = "\u200C"
    bits = ""
    for ch in content:
        if ch == ZWNJ:
            bits += "1"
        elif ch == ZWS:
            bits += "0"
    if len(bits) < 64:
        return None
    try:
        value = int(bits[:64], 2)
        return hex(value)[2:].zfill(16)
    except Exception:
        return None


# ─────────────────────────────────────────────────────────────────────────────
# FILE HEADER GENERATOR
# Injects attribution block at the top of any source file
# ─────────────────────────────────────────────────────────────────────────────

_HEADER_TEMPLATE = '''\
# -*- coding: utf-8 -*-
# ┌─────────────────────────────────────────────────────────────────────────┐
# │  ⚓  {product}                                                           
# │  Criador    : {creator}                                                  
# │  Papel      : {role}                                                     
# │  Org        : {org}                                                      
# │  Versão     : {version}                                                  
# │  Fingerprint: {fingerprint}                                              
# │  SHA-256    : {sha256}                                                   
# │                                                                          
# │  © {year} {creator} — Todos os direitos reservados.                     
# │  Distribuição e modificação sujeitas aos termos da licença CNGSM.       
# └─────────────────────────────────────────────────────────────────────────┘
'''

def file_header() -> str:
    id_ = IDENTITY
    return _HEADER_TEMPLATE.format(
        product     = id_["product"],
        creator     = id_["creator"],
        role        = id_["role"],
        org         = id_["org"],
        version     = VERSION,
        fingerprint = FINGERPRINT,
        sha256      = _EXPECTED_SHA256,
        year        = id_["year"],
    )


# ─────────────────────────────────────────────────────────────────────────────
# RUNTIME GUARD — import-time check
# ─────────────────────────────────────────────────────────────────────────────

def _runtime_guard():
    """Called once at import time. Fails loudly if anchor is corrupted."""
    if not verify_identity(strict=False):
        print(
            "[Hormuz] WARNING: identity anchor verification failed. "
            "This build may be unauthorized.",
            file=sys.stderr
        )

_runtime_guard()


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API
# ─────────────────────────────────────────────────────────────────────────────

__all__ = [
    "IDENTITY",
    "FINGERPRINT",
    "VERSION",
    "verify_identity",
    "attribution_header",
    "embed_in_output",
    "extract_watermark",
    "file_header",
]

if __name__ == "__main__":
    print(file_header())
    print(attribution_header())
    ok = verify_identity(strict=False)
    print(f"\nIntegrity check: {'✓ PASS' if ok else '✗ FAIL'}")
    # Demo watermark
    sample = "Resultado gerado pelo Agente Hormuz.\nConteúdo aqui."
    watermarked = embed_in_output(sample)
    extracted = extract_watermark(watermarked)
    print(f"Watermark embedded: {extracted == FINGERPRINT} | Extracted: {extracted}")
