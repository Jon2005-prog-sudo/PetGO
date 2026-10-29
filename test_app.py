"""Teste de ponta a ponta da aplicacao web (app.py).

Sobe nada por conta propria: assume que o app ja esta rodando em
http://127.0.0.1:8000 (py app.py). Usa so a biblioteca padrao.

Exercita: cadastro de usuario comum, cadastro de ONG, login, sessao,
cadastro de animal com foto, e os endpoints da API.

Rode com:  py test_app.py
"""

from __future__ import annotations

import http.cookiejar
import io
import json
import urllib.request
import urllib.parse
import urllib.error
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


def post_multipart(opener, caminho, campos, nome_arquivo, bytes_arquivo):
    """Monta um multipart/form-data simples (para o upload da foto)."""
    limite = "----teste" + uuid.uuid4().hex
    corpo = io.BytesIO()

    def esc(texto):
        return texto.encode()

    for chave, valor in campos.items():
        corpo.write(esc(f"--{limite}\r\n"))
        corpo.write(esc(f'Content-Disposition: form-data; name="{chave}"\r\n\r\n'))
        corpo.write(esc(f"{valor}\r\n"))

    corpo.write(esc(f"--{limite}\r\n"))
    corpo.write(
        esc(f'Content-Disposition: form-data; name="foto"; filename="{nome_arquivo}"\r\n')
    )
    corpo.write(esc("Content-Type: image/png\r\n\r\n"))
    corpo.write(bytes_arquivo)
    corpo.write(esc(f"\r\n--{limite}--\r\n"))

    req = urllib.request.Request(BASE + caminho, data=corpo.getvalue(), method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={limite}")
    return opener.open(req)


def checar(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  [OK] {msg}")


def gerar_cnpj() -> str:
    """Gera um CNPJ valido (14 digitos) com digitos verificadores corretos."""
    import random

    base = [random.randint(0, 9) for _ in range(12)]

    def dv(nums, pesos):
        s = sum(n * p for n, p in zip(nums, pesos))
        r = s % 11
        return 0 if r < 2 else 11 - r

    p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    p2 = [6] + p1
    d1 = dv(base, p1)
    d2 = dv(base + [d1], p2)
    return "".join(map(str, base + [d1, d2]))


def main():
    print("== Teste: health ==")
    r = urllib.request.urlopen(BASE + "/api/health")
    checar(json.loads(r.read())["status"] == "ok", "api/health responde ok")

    # --- Usuario comum ---
    print("\n== Teste: cadastro de usuario comum + sessao ==")
    sess = nova_sessao()
    email = f"pessoa_{uuid.uuid4().hex[:6]}@email.com"
    r = post_form(sess, "/registrar", {
        "nome": "Joao Teste", "email": email, "senha": "segredo123", "tipo": "comum",
    })
    checar(r.status == 200, "cadastro redirecionou para pagina valida")
    # Apos cadastrar, ja esta logado: a home deve mostrar link de cadastrar animal.
    html = get(sess, "/").read().decode()
    checar("Cadastrar animal" in html, "usuario ficou logado apos cadastro")

    # --- Cadastro de animal com foto ---
    print("\n== Teste: cadastro de animal com foto ==")
    pixel_png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c6360000002000154a24f3b0000000049454e44ae426082"
    )
    r = post_multipart(sess, "/animais/novo", {
        "especie": "cachorro", "porte": "medio", "estado_saude": "ferido",
        "descricao": "Cachorro embaixo de um carro", "urgencia": "alta",
        "endereco": "Av. Paulista, 1000", "latitude": "-23.5505", "longitude": "-46.6333",
    }, "foto.png", pixel_png)
    checar(r.status == 200, "cadastro de animal aceito")

    animais = json.loads(get(sess, "/api/animais").read())
    checar(len(animais) >= 1, "api/animais lista ao menos 1 animal")
    animal = animais[-1]
    checar(animal["especie"] == "cachorro", "especie do animal bateu")
    checar(animal["status"] == "aberto", "status inicial e aberto")
    checar(animal["localizacao"]["latitude"] == -23.5505, "latitude salva")
    checar(bool(animal["foto_path"]), "foto foi salva")

    # A foto deve ser baixavel pela API.
    rf = get(sess, f"/api/animais/{animal['id']}/foto")
    checar(rf.status == 200, "foto do animal e baixavel pela API")

    # --- ONG (com CNPJ e endereco dos specs) ---
    print("\n== Teste: cadastro de ONG com CNPJ ==")
    sess2 = nova_sessao()
    email_ong = f"ong_{uuid.uuid4().hex[:6]}@email.com"
    nome_ong = f"Patas Felizes {uuid.uuid4().hex[:4]}"
    cnpj = gerar_cnpj()
    post_form(sess2, "/registrar", {
        "nome": "Resp ONG", "email": email_ong, "senha": "segredo123", "tipo": "ong",
        "ong_nome": nome_ong, "ong_tipo": "adocao",
        "ong_cnpj": cnpj, "ong_telefone": "+5511988887777",
        "ong_contato": "contato@patas.org", "ong_cidade": "Sao Paulo",
        "ong_street": "Rua das Flores, 100", "ong_state": "SP", "ong_zip": "01234-567",
        "ong_website": "https://patas.org", "ong_description": "Resgate e adocao.",
    })
    ongs = json.loads(get(sess2, "/api/ongs").read())
    checar(any(o["nome"] == nome_ong for o in ongs), "ONG aparece na api/ongs")
    ong = next(o for o in ongs if o["nome"] == nome_ong)
    checar(ong["tipo"] == "adocao", "tipo da ONG bateu")
    checar(ong["cnpj"] == cnpj, "CNPJ foi validado e salvo")
    checar(ong["state"] == "SP", "endereco (estado) foi salvo")

    # CNPJ duplicado deve ser rejeitado (unicidade dos specs).
    sess_dup = nova_sessao()
    post_form(sess_dup, "/registrar", {
        "nome": "Outro", "email": f"x_{uuid.uuid4().hex[:6]}@email.com",
        "senha": "segredo123", "tipo": "ong", "ong_nome": "Dup",
        "ong_tipo": "resgate", "ong_cnpj": cnpj,
    })
    ongs2 = json.loads(get(sess_dup, "/api/ongs").read())
    qtd_cnpj = sum(1 for o in ongs2 if o.get("cnpj") == cnpj)
    checar(qtd_cnpj == 1, "CNPJ duplicado foi rejeitado (continua unico)")

    # --- Alerta de localizacao (ponte com SNS) ---
    print("\n== Teste: alerta de localizacao ==")
    import json as _json
    import urllib.request as _req
    corpo = _json.dumps({
        "recipient_type": "ngo", "recipient_id": ong["id"], "animal_id": animal["id"],
        "latitude": -23.5505, "longitude": -46.6333,
    }).encode()
    r = _req.Request(BASE + "/api/alertas", data=corpo, method="POST")
    r.add_header("Content-Type", "application/json")
    resp = sess.open(r)
    checar(resp.status == 202, "alerta aceito com 202")
    alerta = _json.loads(resp.read())
    checar(alerta["notification_id"].startswith("local-"), "alerta publicado (id local)")
    alertas = _json.loads(get(sess, "/api/alertas").read())
    checar(any(a["id"] == alerta["id"] for a in alertas), "alerta registrado no historico")

    # Coordenada invalida deve dar 422.
    corpo_inv = _json.dumps({
        "recipient_type": "ngo", "recipient_id": ong["id"], "animal_id": animal["id"],
        "latitude": 999, "longitude": 0,
    }).encode()
    ri = _req.Request(BASE + "/api/alertas", data=corpo_inv, method="POST")
    ri.add_header("Content-Type", "application/json")
    try:
        sess.open(ri)
        raise AssertionError("coordenada invalida deveria dar 422")
    except urllib.error.HTTPError as e:
        checar(e.code == 422, "coordenada invalida rejeitada com 422")

    # --- Seguranca: senha nao pode estar em texto puro ---
    print("\n== Teste: senha guardada com hash ==")
    import store
    u = store.buscar_usuario_por_email(email)
    checar(u is not None, "usuario foi persistido")
    checar(u["senha_hash"] != "segredo123", "senha NAO esta em texto puro")
    checar(u["senha_hash"].startswith(("pbkdf2:", "scrypt:")), "senha usa hash seguro")

    # --- Login com senha errada deve falhar ---
    print("\n== Teste: login ==")
    sess3 = nova_sessao()
    post_form(sess3, "/login", {"email": email, "senha": "ERRADA"})
    html = get(sess3, "/").read().decode()
    checar("Cadastrar animal" not in html, "login com senha errada NAO autentica")

    post_form(sess3, "/login", {"email": email, "senha": "segredo123"})
    html = get(sess3, "/").read().decode()
    checar("Cadastrar animal" in html, "login com senha certa autentica")

    print("\n==============================")
    print("  TODOS OS TESTES PASSARAM")
    print("==============================")


if __name__ == "__main__":
    main()
