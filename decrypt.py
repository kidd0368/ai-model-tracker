#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""解密 data.enc -> data.json（每日更新流程用）
用法: SITE_PASSWORD='...' python3 decrypt.py
"""
import json, os, sys, base64, tempfile
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.primitives import hashes
from cryptography.exceptions import InvalidTag
from validate_data import validate_or_raise

ROOT = os.path.dirname(os.path.abspath(__file__))
PASSWORD = os.environ.get("SITE_PASSWORD") or (sys.argv[1] if len(sys.argv) > 1 else None)
if not PASSWORD:
    sys.exit("ERROR: 請以 SITE_PASSWORD 環境變數提供密碼")

with open(os.path.join(ROOT, "data.enc"), encoding="utf-8") as f:
    p = json.load(f)

kdf = PBKDF2HMAC(algorithm=hashes.SHA256(), length=32,
                 salt=base64.b64decode(p["salt"]), iterations=p["iter"])
key = kdf.derive(PASSWORD.encode("utf-8"))
try:
    pt = AESGCM(key).decrypt(base64.b64decode(p["iv"]), base64.b64decode(p["ct"]), None)
except InvalidTag:
    sys.exit("ERROR: SITE_PASSWORD 不正確，data.enc 未被修改")
data = json.loads(pt.decode("utf-8"))
validate_or_raise(data)

target = os.path.join(ROOT, "data.json")
fd, temporary = tempfile.mkstemp(prefix=".data.json.", suffix=".tmp", dir=ROOT)
try:
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, target)
finally:
    try:
        os.unlink(temporary)
    except FileNotFoundError:
        pass
print("OK: data.json restored (version %s, updated %s)" % (
    data["meta"].get("version"), data["meta"].get("updated")))
