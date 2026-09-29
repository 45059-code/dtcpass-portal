#!/usr/bin/env python3
"""
Multi-Layer Encryption Vault for DTC Passes
Encrypts pass database into a secure, scrambled format for frontend static CDN deployment.
No plain-text names, phone numbers, photos, or details are visible.
"""

import os
import json
import base64
import hashlib

KEY = "DTC@SEC99#PORTAL$VAULT!2026"
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SOURCE_DB = os.path.join(BASE_DIR, "backend", "passes_db.json")
TARGET_JSON = os.path.join(BASE_DIR, "passes.json")

def encode_vault(plain_str: str) -> dict:
    raw_bytes = plain_str.encode("utf-8")
    key_bytes = KEY.encode("utf-8")
    klen = len(key_bytes)
    
    # Layer 1: XOR mask + Layer 2: Byte displacement (+47 mod 256)
    step1 = bytearray()
    for i, b in enumerate(raw_bytes):
        x = (b ^ key_bytes[i % klen])
        x = (x + 47) % 256
        step1.append(x)
    
    # Layer 2b: Array inversion (reverse byte stream)
    step2 = step1[::-1]
    
    # Layer 3: High-entropy Base64 encoding
    enc = base64.b64encode(step2).decode("ascii")
    
    return {
        "status": 200,
        "vault": enc,
        "hash": hashlib.sha256(enc.encode("ascii")).hexdigest()[:16]
    }

def main():
    if not os.path.exists(SOURCE_DB):
        print(f"[ERROR] Source database not found: {SOURCE_DB}")
        return 1

    with open(SOURCE_DB, "r", encoding="utf-8") as f:
        data = json.load(f)

    passes = data.get("passes", []) if isinstance(data, dict) else data
    plain_str = json.dumps({"passes": passes}, ensure_ascii=False)
    
    vault_payload = encode_vault(plain_str)
    
    with open(TARGET_JSON, "w", encoding="utf-8") as f:
        json.dump(vault_payload, f, indent=2)
        
    print(f"[SECURE VAULT] Successfully encrypted {len(passes)} passes into passes.json!")
    print(f"[SECURE VAULT] 3-layer encryption applied: XOR Masking -> Byte Rotation & Inversion -> Base64 Envelope.")
    print(f"[SECURE VAULT] Checksum: {vault_payload['hash']}")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
