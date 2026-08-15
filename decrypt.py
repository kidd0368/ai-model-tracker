#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解密 data.enc -> data.json（每日更新流程用）
用法: SITE_PASSWORD='...' python3 decrypt.py
"""
import json, os, sys, base64
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes

ROOT = os.path.dirname(os.path.abspath(__file__))
PASSWORD = os.environ.get("SITE_PASSWORD") or (sys.argv[1] if len(sys.argv) > 1 else None)
if not PASSWORD:
    sys.exit("ERROR: 請以 SITE_PASSWORD 環境變數提供密碼")

with open(os.path.join(ROOT, "data.enc"), encoding="utf-8") as f:
    p = json.load(f)

kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                 salt=base64.b64decode(p["salt"]), iterations=p["iter"])
key = kdf.derive(PASSWORD.encode("utf-8"))
pt = AESGCM(key).decrypt(base64.b64decode(p["iv"]), base64.b64decode(p["ct"]), None)
data = json.loads(pt.decode("utf-8"))
with open(os.path.join(ROOT, "data.json"), "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)
print("OK: data.json restored (version %s, updated %s)" % (
    data["meta"].get("version"), data["meta"].get("updated")))
