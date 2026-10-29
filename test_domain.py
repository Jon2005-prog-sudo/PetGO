"""Testes do dominio animal-rescue-app (DESING, Opcao A).

Property-based tests (hypothesis, equivalente ao fast-check do design) para
as 10 Correctness Properties, mais testes de exemplo das regras.

Rode com:  py test_domain.py
"""

from __future__ import annotations

from hypothesis import given, strategies as st, settings

from domain.types import (
    Role, AnimalStatus, AdoptionStatus,
    ANIMAL_TRANSITIONS, ADOPTION_TRANSITIONS,
    is_valid_animal_transition, is_valid_adoption_transition,
)
from domain.repository import InMemoryRepo, novo_id
from domain.animals import AnimalService
from domain.adoption import AdoptionService
from domain import errors


# ----------------------------------------------------------------------
# Helpers de cenario
# ----------------------------------------------------------------------
def cenario():
    repo = InMemoryRepo()
    animais = AnimalService(repo)
    adocao = AdoptionService(repo)
    return repo, animais, adocao


def novo_usuario(repo, role, suspended=False):
    u = {"id": novo_id(), "name": "u", "email": f"{novo_id()}@e.com",
         "role": role, "suspended": suspended}
    return repo.add_usuario(u)


def animal_disponivel(repo, animais, protetor, **extra):
    a = animais.create_animal(protetor["id"], {
        "name": "Rex", "species": extra.get("species", "dog"),
        "description": "cao dócil", "locationCity": extra.get("city", "Fortaleza"),
        "size": extra.get("size"), "sex": extra.get("sex"),
        "ageMonths": extra.get("ageMonths"),
    })
    # SHELTERED -> AVAILABLE (transicao valida)
    animais.change_status(protetor["id"], a["id"], AnimalStatus.AVAILABLE)
    return a


def checar(cond, msg):
    if not cond:
        raise AssertionError(msg)
    print(f"  [OK] {msg}")


# ----------------------------------------------------------------------
# Property 2 e 9: transicoes sempre validas
# ----------------------------------------------------------------------
@given(st.sampled_from(list(AnimalStatus)), st.sampled_from(list(AnimalStatus)))
def test_p2_animal_transitions(cur, nxt):
    valido = is_valid_animal_transition(cur, nxt)
    assert valido == (nxt in ANIMAL_TRANSITIONS[cur])
    # estados terminais nunca transitam
    if not ANIMAL_TRANSITIONS[cur]:
        assert not valido


@given(st.sampled_from(list(AdoptionStatus)), st.sampled_from(list(AdoptionStatus)))
def test_p9_adoption_transitions(cur, nxt):
    valido = is_valid_adoption_transition(cur, nxt)
    assert valido == (nxt in ADOPTION_TRANSITIONS[cur])
    if cur in (AdoptionStatus.APPROVED, AdoptionStatus.REJECTED,
               AdoptionStatus.CANCELLED):
        assert not valido  # terminais


# ----------------------------------------------------------------------
# Property 1: listAvailable so retorna AVAILABLE
# ----------------------------------------------------------------------
@settings(max_examples=50)
@given(st.lists(st.sampled_from(list(AnimalStatus)), min_size=0, max_size=12))
def test_p1_list_available(status_list):
    repo, animais, _ = cenario()
    prot = novo_usuario(repo, Role.PROTECTOR)
    for sstatus in status_list:
        a = {"id": novo_id(), "protectorId": prot["id"], "status": sstatus,
             "description": "x", "species": "dog", "locationCity": "F",
             "photos": [], "name": "n"}
        repo.add_animal(a)
    page = animais.list_available()
    for item in page["items"]:
        assert AnimalStatus(item["status"]) == AnimalStatus.AVAILABLE
    esperado = sum(1 for s in status_list if s == AnimalStatus.AVAILABLE)
    assert page["total"] == esperado


# ----------------------------------------------------------------------
# Property 3, 4: aprovacao exclusiva e animal adotado
# ----------------------------------------------------------------------
@settings(max_examples=30)
@given(st.integers(min_value=1, max_value=6))
def test_p3_p4_approval_exclusive(n_pedidos):
    repo, animais, adocao = cenario()
    prot = novo_usuario(repo, Role.PROTECTOR)
    animal = animal_disponivel(repo, animais, prot)
    pedidos = []
    for _ in range(n_pedidos):
        adot = novo_usuario(repo, Role.ADOPTER)
        pedidos.append(adocao.create_request(adot["id"], animal["id"]))

    adocao.review_request(prot["id"], pedidos[0]["id"], "APPROVE")

    todos = adocao.list_requests_for_animal(animal["id"])
    aprovados = [p for p in todos if AdoptionStatus(p["status"]) == AdoptionStatus.APPROVED]
    assert len(aprovados) == 1  # P3: no maximo um APPROVED
    # P3: os demais viraram REJECTED
    for p in todos:
        if p["id"] != pedidos[0]["id"]:
            assert AdoptionStatus(p["status"]) == AdoptionStatus.REJECTED
    # P4: animal ADOPTED
    assert AnimalStatus(repo.get_animal(animal["id"])["status"]) == AnimalStatus.ADOPTED


# ----------------------------------------------------------------------
# Property 5, 6: pedido so para disponivel; unicidade de ativo
# ----------------------------------------------------------------------
def test_p5_only_available():
    repo, animais, adocao = cenario()
    prot = novo_usuario(repo, Role.PROTECTOR)
    adot = novo_usuario(repo, Role.ADOPTER)
    # animal SHELTERED (nao disponivel)
    a = animais.create_animal(prot["id"], {"description": "x", "species": "cat"})
    try:
        adocao.create_request(adot["id"], a["id"])
        raise AssertionError("deveria recusar pedido para animal nao disponivel")
    except errors.AnimalNotAvailable:
        print("  [OK] P5: pedido recusado para animal nao disponivel")


def test_p6_unique_active():
    repo, animais, adocao = cenario()
    prot = novo_usuario(repo, Role.PROTECTOR)
    adot = novo_usuario(repo, Role.ADOPTER)
    animal = animal_disponivel(repo, animais, prot)
    adocao.create_request(adot["id"], animal["id"])
    try:
        adocao.create_request(adot["id"], animal["id"])
        raise AssertionError("deveria recusar segundo pedido ativo")
    except errors.DuplicateActiveRequest:
        print("  [OK] P6: segundo pedido ativo do mesmo adotante recusado")


# ----------------------------------------------------------------------
# Property 7, 8: so protetor verificado publica; autorizacao por papel
# ----------------------------------------------------------------------
def test_p7_p8_authorization():
    repo, animais, adocao = cenario()
    adot = novo_usuario(repo, Role.ADOPTER)
    # adotante nao pode criar animal (P7/P8)
    try:
        animais.create_animal(adot["id"], {"description": "x"})
        raise AssertionError("adotante nao deveria cadastrar animal")
    except errors.NotAuthorized:
        print("  [OK] P7/P8: adotante nao cadastra animal")

    # adotante nao pode revisar pedido de outro
    prot = novo_usuario(repo, Role.PROTECTOR)
    animal = animal_disponivel(repo, animais, prot)
    outro_adot = novo_usuario(repo, Role.ADOPTER)
    pedido = adocao.create_request(outro_adot["id"], animal["id"])
    intruso = novo_usuario(repo, Role.ADOPTER)
    try:
        adocao.review_request(intruso["id"], pedido["id"], "APPROVE")
        raise AssertionError("intruso nao deveria revisar")
    except errors.NotAuthorized:
        print("  [OK] P8: nao-dono nao revisa pedido")


# ----------------------------------------------------------------------
# Property 10: notificacao ao destinatario correto
# ----------------------------------------------------------------------
def test_p10_notifications():
    repo, animais, adocao = cenario()
    prot = novo_usuario(repo, Role.PROTECTOR)
    animal = animal_disponivel(repo, animais, prot)
    adot = novo_usuario(repo, Role.ADOPTER)
    pedido = adocao.create_request(adot["id"], animal["id"])
    # protetor recebe notificacao de novo pedido
    nots_prot = repo.notificacoes_do_usuario(prot["id"])
    checar(any(n["type"] == "ADOPTION_REQUEST_CREATED" for n in nots_prot),
           "P10: protetor notificado de novo pedido")
    adocao.review_request(prot["id"], pedido["id"], "APPROVE")
    nots_adot = repo.notificacoes_do_usuario(adot["id"])
    checar(any(n["type"] == "ADOPTION_DECISION" for n in nots_adot),
           "P10: adotante notificado da decisao")
    # ninguem alheio recebeu
    terceiro = novo_usuario(repo, Role.ADOPTER)
    checar(repo.notificacoes_do_usuario(terceiro["id"]) == [],
           "P10: usuario alheio NAO recebeu notificacao")


# ----------------------------------------------------------------------
# Concorrencia (Cenario 1 do Error Handling / Req 7.7)
# ----------------------------------------------------------------------
def test_concurrency_second_approval_conflict():
    repo, animais, adocao = cenario()
    prot = novo_usuario(repo, Role.PROTECTOR)
    animal = animal_disponivel(repo, animais, prot)
    a1 = adocao.create_request(novo_usuario(repo, Role.ADOPTER)["id"], animal["id"])
    a2 = adocao.create_request(novo_usuario(repo, Role.ADOPTER)["id"], animal["id"])
    adocao.review_request(prot["id"], a1["id"], "APPROVE")  # 1a aprova
    # a2 ja foi auto-rejeitado; tentar aprovar deve falhar (pedido nao pendente)
    try:
        adocao.review_request(prot["id"], a2["id"], "APPROVE")
        raise AssertionError("segunda aprovacao deveria falhar")
    except (errors.Conflict, errors.InvalidTransition):
        print("  [OK] concorrencia: segunda aprovacao do mesmo animal recusada")


# ----------------------------------------------------------------------
# Runner (executa property tests + exemplos)
# ----------------------------------------------------------------------
if __name__ == "__main__":
    print("== Property 2: transicoes do animal ==")
    test_p2_animal_transitions()
    print("  [OK] P2: nenhuma transicao invalida aceita")

    print("\n== Property 9: transicoes de adocao ==")
    test_p9_adoption_transitions()
    print("  [OK] P9: terminais nao transitam")

    print("\n== Property 1: vitrine so AVAILABLE ==")
    test_p1_list_available()
    print("  [OK] P1: listAvailable so retorna AVAILABLE")

    print("\n== Property 3 e 4: aprovacao exclusiva + animal adotado ==")
    test_p3_p4_approval_exclusive()
    print("  [OK] P3/P4: um APPROVED, resto REJECTED, animal ADOPTED")

    print("\n== Property 5 e 6 ==")
    test_p5_only_available()
    test_p6_unique_active()

    print("\n== Property 7 e 8 ==")
    test_p7_p8_authorization()

    print("\n== Property 10 ==")
    test_p10_notifications()

    print("\n== Concorrencia ==")
    test_concurrency_second_approval_conflict()

    print("\n==============================")
    print("  DOMINIO: TODOS OS TESTES PASSARAM")
    print("==============================")
