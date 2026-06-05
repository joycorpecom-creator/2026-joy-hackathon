import os
import requests
from dotenv import load_dotenv

load_dotenv()
BASE = os.getenv("BURGERPRINTS_BASE_URL", "https://api.burgerprints.com/v2").rstrip("/")
KEY = os.getenv("BURGERPRINTS_API_KEY", "").strip()

ENDPOINTS = [
    ("authenticated", "GET", "/authenticated"),
    ("orders", "GET", "/order"),
    ("products", "GET", "/product"),
    ("balance", "GET", "/balance"),
]


def probe():
    print(f"base={BASE}")
    print(f"has_key={bool(KEY)}")
    if not KEY:
        print("SKIP real API: set BURGERPRINTS_API_KEY in .env")
        return 0
    bad = 0
    for name, method, path in ENDPOINTS:
        try:
            r = requests.request(method, BASE + path, headers={"api-key": KEY}, timeout=30)
            body = r.text[:500].replace("\n", " ")
            ok = 200 <= r.status_code < 300
            print(f"{name}: HTTP {r.status_code} ok={ok} body={body}")
            bad += 0 if ok else 1
        except Exception as e:
            bad += 1
            print(f"{name}: ERR {e}")
    return bad


if __name__ == "__main__":
    raise SystemExit(probe())
