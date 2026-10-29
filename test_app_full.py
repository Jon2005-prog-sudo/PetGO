"""Teste e2e (end-to-end) do fluxo completo da aplicacao web.

Usa apenas a biblioteca padrao (urllib + http.cookiejar), falando HTTP com
o servidor assumido rodando em http://127.0.0.1:8000.

Exercita o fluxo completo:
  1. Registra um ADOTANTE (login automatico).
  2. Registra outro usuario e o torna PROTETOR
     (pedido de verificacao + aprovacao pelo ADMIN semente admin@local).
  3. Protetor cadastra um animal (status inicial SHELTERED).
  4. Protetor evolui o status SHELTERED -> AVAILABLE.
  5. Adotante cria um pedido de adocao.
  6. Protetor aprova o pedido.
  7. Confirma, via API, que o animal ficou ADOPTED e some da vitrine.
  8. Valida /api/health.

Cada checagem imprime "[OK] msg". No fim imprime "TODOS OS TESTES PASSARAM".

Pre-requisito: o servidor precisa estar no ar:
    gunicorn --bind 127.0.0.1:8000 app:app
ou
    py app.py

Uso:
    py test_app_full.py
"""

from __future__ import annotations

import http.cookiejar
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid

BASE = "http://127.0.0.1:8000"

ADMIN_EMAIL = "admin@local"
ADMIN_SENHA = "admin12345"


class Cliente:
    """Um 'navegador' com seu proprio jar de cookies (sessao independente)."""

    def __init__(self):
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.jar),
            _NoRedirect(),
        )

    def get(self, path: str):
        req = urllib.request.Request(BASE + path, method="GET")
        return self._abrir(req)

    def post_form(self, path: str, dados: dict):
        corpo = urllib.parse.urlencode(dados).encode("utf-8")
        req = urllib.request.Request(
            BASE + path,
            data=corpo,
            method="POST",
            headers={"Content-Type": "application/x-www-form-urlencoded"},
        )
        return self._abrir(req)

    def _abrir(self, req):
        try:
            resp = self.opener.open(req, timeout=15)
            corpo = resp.read().decode("utf-8", errors="replace")
            return resp.status, corpo, resp.headers
        except urllib.error.HTTPError as e:
            corpo = e.read().decode("utf-8", errors="replace")
            return e.code, corpo, e.headers


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Nao segue redirect automaticamente, para podermos inspecionar 302."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def ok(msg: str) -> None:
    print(f"[OK] {msg}")


def falhar(msg: str) -> None:
    print(f"[FALHA] {msg}")
    sys.exit(1)


def esperar(cond: bool, msg: str) -> None:
    if cond:
        ok(msg)
    else:
        falhar(msg)


def get_json(cliente: Cliente, path: str):
    status, corpo, _ = cliente.get(path)
    if status != 200:
        falhar(f"GET {path} retornou {status}")
    return json.loads(corpo)


def main() -> None:
    sufixo = uuid.uuid4().hex[:8]

    # ------------------------------------------------------------------
    # 0. Health check da API
    # ------------------------------------------------------------------
    anon = Cliente()
    try:
        saude = get_json(anon, "/api/health")
    except urllib.error.URLError:
        falhar(
            "Nao foi possivel conectar ao servidor em "
            f"{BASE}. Suba a app antes (py app.py)."
        )
    esperar(saude.get("status") == "ok", "/api/health responde {'status':'ok'}")

    # ------------------------------------------------------------------
    # 1. Registrar ADOTANTE (login automatico)
    # ------------------------------------------------------------------
    adotante = Cliente()
    email_adotante = f"adotante_{sufixo}@teste.com"
    status, corpo, _ = adotante.post_form(
        "/registrar",
        {"nome": "Adotante Teste", "email": email_adotante, "senha": "senha12345"},
    )
    esperar(status in (302, 303), "registro de adotante redireciona (login automatico)")

    # Confirma sessao: GET /meus-pedidos deve responder 200 (logado).
    status, corpo, _ = adotante.get("/meus-pedidos")
    esperar(status == 200, "adotante autenticado acessa /meus-pedidos")

    # ------------------------------------------------------------------
    # 2. Registrar outro usuario e torna-lo PROTETOR
    # ------------------------------------------------------------------
    protetor = Cliente()
    email_protetor = f"protetor_{sufixo}@teste.com"
    status, _, _ = protetor.post_form(
        "/registrar",
        {"nome": "Protetor Teste", "email": email_protetor, "senha": "senha12345"},
    )
    esperar(status in (302, 303), "registro de protetor (ainda ADOTANTE) ok")

    # Pede verificacao de protetor.
    status, _, _ = protetor.post_form(
        "/tornar-protetor",
        {"org_name": "ONG Teste", "document_url": ""},
    )
    esperar(status in (302, 303), "pedido de verificacao de protetor enviado")

    # Admin loga e aprova o pedido.
    admin = Cliente()
    status, _, _ = admin.post_form(
        "/login", {"email": ADMIN_EMAIL, "senha": ADMIN_SENHA}
    )
    esperar(status in (302, 303), "admin semente faz login")

    status, corpo, _ = admin.get("/admin")
    esperar(status == 200, "admin acessa painel de verificacoes")

    # Extrai o user_id do solicitante a partir do form do painel admin.
    user_ids = re.findall(r'name="user_id" value="([^"]+)"', corpo)
    esperar(len(user_ids) >= 1, "ha ao menos um pedido pendente no painel admin")

    # Precisamos do id do NOSSO protetor. Descobrimos via /api? Nao expomos
    # usuarios. Entao aprovamos todos os pendentes (ambiente de teste isolado
    # por e-mail unico; aprovar extras nao afeta o nosso fluxo).
    aprovados = 0
    for uid in set(user_ids):
        status, _, _ = admin.post_form(
            "/admin/decidir",
            {"user_id": uid, "decision": "APPROVE", "reason": ""},
        )
        if status in (302, 303):
            aprovados += 1
    esperar(aprovados >= 1, "admin aprovou pedido(s) de protetor")

    # Protetor confirma que agora tem acesso ao painel (rota exclusiva).
    status, _, _ = protetor.get("/painel")
    esperar(status == 200, "usuario promovido acessa /painel (agora e PROTETOR)")

    # ------------------------------------------------------------------
    # 3. Protetor cadastra um animal (SHELTERED)
    # ------------------------------------------------------------------
    especie_unica = f"Especie{sufixo}"
    status, _, _ = protetor.post_form(
        "/animais/novo",
        {
            "name": "Rex",
            "species": especie_unica,
            "breed": "SRD",
            "size": "MEDIUM",
            "sex": "MALE",
            "ageMonths": "24",
            "description": "Cachorro docil para adocao.",
            "locationCity": "Sao Paulo",
        },
    )
    esperar(status in (302, 303), "protetor cadastra animal")

    # Descobre o id do animal via painel.
    status, painel_html, _ = protetor.get("/painel")
    esperar(status == 200, "painel do protetor carrega")
    ids_animal = re.findall(r'/animais/([0-9a-f]+)/status', painel_html)
    esperar(len(ids_animal) >= 1, "animal aparece no painel do protetor")
    animal_id = ids_animal[0]

    # Confirma que NAO esta na vitrine ainda (SHELTERED, nao AVAILABLE).
    vitrine = get_json(anon, "/api/animais")
    esta = any(a["id"] == animal_id for a in vitrine)
    esperar(not esta, "animal SHELTERED nao aparece na vitrine")

    # ------------------------------------------------------------------
    # 4. Protetor evolui SHELTERED -> AVAILABLE
    # ------------------------------------------------------------------
    status, _, _ = protetor.post_form(
        f"/animais/{animal_id}/status", {"status": "AVAILABLE"}
    )
    esperar(status in (302, 303), "protetor muda status para AVAILABLE")

    animal = get_json(anon, f"/api/animais/{animal_id}")
    esperar(animal["status"] == "AVAILABLE", "animal agora esta AVAILABLE")

    vitrine = get_json(anon, "/api/animais")
    esta = any(a["id"] == animal_id for a in vitrine)
    esperar(esta, "animal AVAILABLE aparece na vitrine (/api/animais)")

    # ------------------------------------------------------------------
    # 5. Adotante cria pedido de adocao
    # ------------------------------------------------------------------
    status, _, _ = adotante.post_form(
        f"/animais/{animal_id}/adotar",
        {"message": "Tenho quintal grande."},
    )
    esperar(status in (302, 303), "adotante cria pedido de adocao")

    # Descobre o id do pedido via painel do protetor.
    status, painel_html, _ = protetor.get("/painel")
    ids_pedido = re.findall(r'/pedidos/([0-9a-f]+)/revisar', painel_html)
    esperar(len(ids_pedido) >= 1, "pedido aparece no painel do protetor")
    pedido_id = ids_pedido[0]

    # ------------------------------------------------------------------
    # 6. Protetor aprova o pedido
    # ------------------------------------------------------------------
    status, _, _ = protetor.post_form(
        f"/pedidos/{pedido_id}/revisar",
        {"decision": "APPROVE", "note": "Aprovado!"},
    )
    esperar(status in (302, 303), "protetor aprova o pedido")

    # ------------------------------------------------------------------
    # 7. Confirma animal ADOPTED e pedido APPROVED; fora da vitrine
    # ------------------------------------------------------------------
    animal = get_json(anon, f"/api/animais/{animal_id}")
    esperar(animal["status"] == "ADOPTED", "animal ficou ADOPTED apos aprovacao")

    vitrine = get_json(anon, "/api/animais")
    esta = any(a["id"] == animal_id for a in vitrine)
    esperar(not esta, "animal ADOPTED saiu da vitrine (so AVAILABLE aparece)")

    # Pedido APPROVED visivel em /meus-pedidos do adotante.
    status, html_pedidos, _ = adotante.get("/meus-pedidos")
    esperar(status == 200, "adotante acessa /meus-pedidos")
    esperar(
        "Aprovado" in html_pedidos,
        "pedido do adotante aparece como APROVADO em /meus-pedidos",
    )

    print("\nTODOS OS TESTES PASSARAM")


if __name__ == "__main__":
    main()
