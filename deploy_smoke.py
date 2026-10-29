"""Smoke test de producao: valida que app:app (o WSGI que o gunicorn servira)
importa e responde. Nao sobe servidor; usa o test client do Flask.

Rode com:  py deploy_smoke.py
"""

from app import app  # mesmo objeto que o gunicorn carrega: "app:app"

c = app.test_client()

r = c.get("/api/health")
assert r.status_code == 200, r.status_code
assert r.get_json()["status"] == "ok"
print("[OK] app:app importa e /api/health responde 200")

r = c.get("/")
assert r.status_code == 200, r.status_code
print("[OK] home (/) responde 200")

r = c.get("/api/animais")
assert r.status_code == 200, r.status_code
print("[OK] /api/animais responde 200")

print("SMOKE_OK")
