"""Teste focado na ETAPA 1 - Registro (cadastro + login).

Assume o app rodando em http://127.0.0.1:8000 (py app.py).
Usa so a biblioteca padrao.

Cobre:
  - cadastro de usuario comum (fica logado)
  - cadastro de ONG (com CNPJ/endereco)
  - rejeicao de e-mail duplicado
  - rejeicao de senha fraca
  - senha guardada com hash (nunca texto puro)
  - login com senha certa e errada

Rode com:  py test_registro_web.py
"""

from __future__ import annotations

import http.cookiejar
import json
import random
import urllib.parse
import urllib.request
import uuid

BASE = "http://127.0.0.1:8000"


def nova_sessao():
    cj = http.cookiejar.CookieJar()
    return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))


def post_form(opener, caminho, campos):
    dados = urllib.parse.urlencode(campos).encode()
    req = urllib.request.Request(BASE + caminho, data=dados, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    return opener.open(req)


def get(opener, caminho):
    return opener.open(BASE + caminho)


def checar(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  [OK] {msg}")


def gerar_cnpj() -> str:
    """CNPJ valido (14 digitos) com digitos verificadores corretos."""
    base = [random.randint(0, 9) for _ in range(12)]

    def dv(nums, pesos):
        r = sum(n * p for n, p in zip(nums, pesos)) % 11
        return 0 if r < 2 else 11 - r

    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    d1 = dv(base, p1)
    d2 = dv(base + [d1], [6] + p1)
    return "".join(map(str, base + [d1, d2]))


def esta_logado(opener) -> bool:
    """Home mostra 'Cadastrar animal' somente quando logado."""
    return "Cadastrar animal" in get(opener, "/").read().decode()


def main():
    print("== ETAPA 1 - REGISTRO: usuario comum ==")
    sess = nova_sessao()
    email = f"pessoa_{uuid.uuid4().hex[:8]}@email.com"
    post_form(sess, "/registrar", {
        "nome": "Joao Teste", "email": email,
        "senha": "segredo123", "tipo": "comum",
    })
    checar(esta_logado(sess), "usuario comum cadastrado e ja logado")

    print("\n== REGISTRO: ONG com CNPJ e endereco ==")
    sess2 = nova_sessao()
    nome_ong = f"Patas {uuid.uuid4().hex[:5]}"
    cnpj = gerar_cnpj()
    post_form(sess2, "/registrar", {
        "nome": "Resp ONG", "email": f"ong_{uuid.uuid4().hex[:8]}@email.com",
        "senha": "segredo123", "tipo": "ong", "ong_nome": nome_ong,
        "ong_tipo": "adocao", "ong_cnpj": cnpj, "ong_telefone": "+5511988887777",
        "ong_contato": "contato@patas.org", "ong_cidade": "Sao Paulo",
        "ong_street": "Rua X, 1", "ong_state": "SP", "ong_zip": "01000-000",
    })
    ongs = json.loads(get(sess2, "/api/ongs").read())
    ong = next((o for o in ongs if o["nome"] == nome_ong), None)
    checar(ong is not None, "ONG foi cadastrada e aparece na API")
    checar(ong["cnpj"] == cnpj, "CNPJ validado e salvo")
    checar(ong["tipo"] == "adocao", "tipo da ONG salvo (adocao)")

    print("\n== REGISTRO: e-mail duplicado e rejeitado ==")
    sess3 = nova_sessao()
    post_form(sess3, "/registrar", {
        "nome": "Duplicado", "email": email,  # mesmo e-mail do 1o usuario
        "senha": "segredo123", "tipo": "comum",
    })
    checar(not esta_logado(sess3), "cadastro com e-mail duplicado NAO autentica")

    print("\n== REGISTRO: senha fraca e rejeitada ==")
    sess4 = nova_sessao()
    post_form(sess4, "/registrar", {
        "nome": "Fraco", "email": f"fraco_{uuid.uuid4().hex[:8]}@email.com",
        "senha": "123", "tipo": "comum",  # curta e sem letra+numero
    })
    checar(not esta_logado(sess4), "cadastro com senha fraca NAO autentica")

    print("\n== REGISTRO: senha guardada com hash ==")
    import store
    u = store.buscar_usuario_por_email(email)
    checar(u is not None, "usuario persistido no store")
    checar(u["senha_hash"] != "segredo123", "senha NAO esta em texto puro")
    checar(u["senha_hash"].startswith(("pbkdf2:", "scrypt:")), "senha usa hash seguro")

    print("\n== LOGIN ==")
    sess5 = nova_sessao()
    post_form(sess5, "/login", {"email": email, "senha": "ERRADA"})
    checar(not esta_logado(sess5), "login com senha errada NAO autentica")
    post_form(sess5, "/login", {"email": email, "senha": "segredo123"})
    checar(esta_logado(sess5), "login com senha certa autentica")

    print("\n==============================")
    print("  REGISTRO: TODOS OS TESTES PASSARAM")
    print("==============================")


if __name__ == "__main__":
    main()
