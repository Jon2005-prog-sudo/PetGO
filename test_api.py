"""Teste de ponta a ponta dos endpoints da API (com ela rodando).

Sobe nada por conta propria: assume que a API esta rodando em
http://127.0.0.1:8000 (py api.py). Exercita criar, listar, buscar e
atualizar status, conferindo os codigos de resposta e os dados.

Rode com:  py test_api.py
"""

from __future__ import annotations

import json
import urllib.request

BASE = "http://127.0.0.1:8000"


def pedir(metodo: str, caminho: str, corpo: dict | None = None):
    dados = None
    headers = {}
    if corpo is not None:
        dados = json.dumps(corpo).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(BASE + caminho, data=dados, headers=headers, method=metodo)
    try:
        with urllib.request.urlopen(req) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def checar(cond: bool, msg: str) -> None:
    if not cond:
        raise AssertionError(msg)
    print(f"  [OK] {msg}")


print("== POST /solicitacoes (JSON, sem foto) ==")
status, criada = pedir("POST", "/solicitacoes", {
    "nome": "Maria Silva",
    "contato": "maria@email.com",
    "endereco": "Av. Paulista, 1000 - Sao Paulo",
    "especie": "cachorro",
    "porte": "medio",
    "estado_saude": "ferido",
    "descricao": "Cachorro embaixo de um carro",
    "urgencia": "alta",
})
checar(status == 201, f"status 201 na criacao (veio {status})")
checar("id" in criada, "resposta traz um id")
checar(criada["status"] == "aberto", "status inicial 'aberto'")
checar(criada["localizacao"]["endereco"] == "Av. Paulista, 1000 - Sao Paulo", "endereco gravado")
id_ = criada["id"]

print("\n== POST com campo obrigatorio faltando -> 400 ==")
status, erro = pedir("POST", "/solicitacoes", {"nome": "So nome"})
checar(status == 400, f"status 400 quando falta campo (veio {status})")
checar("campos" in erro, "resposta lista os campos faltando")

print("\n== GET /solicitacoes ==")
status, lista = pedir("GET", "/solicitacoes")
checar(status == 200, "status 200 na listagem")
checar(any(s["id"] == id_ for s in lista), "a solicitacao criada aparece na lista")

print("\n== GET /solicitacoes/<id> ==")
status, uma = pedir("GET", f"/solicitacoes/{id_}")
checar(status == 200, "status 200 ao buscar por id")
checar(uma["id"] == id_, "id bateu")

print("\n== GET /solicitacoes/<id-inexistente> -> 404 ==")
status, _ = pedir("GET", "/solicitacoes/naoexiste")
checar(status == 404, f"status 404 para id inexistente (veio {status})")

print("\n== PATCH /solicitacoes/<id> (status) ==")
status, atual = pedir("PATCH", f"/solicitacoes/{id_}", {"status": "em andamento"})
checar(status == 200, "status 200 ao atualizar")
checar(atual["status"] == "em andamento", "status mudou para 'em andamento'")

print("\n==============================")
print("  API: TODOS OS TESTES PASSARAM")
print("==============================")
