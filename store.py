"""Camada de dados em JSON para a aplicacao de resgate.

Guarda usuarios, ONGs e animais em arquivos JSON separados dentro de
data/. Esta camada esta isolada de proposito: quando o grupo quiser
trocar por um banco de verdade (SQLite/Postgres), basta reescrever as
funcoes daqui mantendo as mesmas assinaturas.

AVISO (JSON): nao lida bem com acessos simultaneos e nao escala. Serve
para o escopo do trabalho. Para producao real, use um banco.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from pathlib import Path
from threading import Lock

PASTA_DADOS = Path(__file__).resolve().parent / "data"
PASTA_FOTOS = PASTA_DADOS / "photos"

ARQ_USUARIOS = PASTA_DADOS / "usuarios.json"
ARQ_ONGS = PASTA_DADOS / "ongs.json"
ARQ_ANIMAIS = PASTA_DADOS / "animais.json"
ARQ_ALERTAS = PASTA_DADOS / "alertas.json"  # historico de alertas (ponte SNS)

# Um lock por processo evita corromper o JSON em escritas concorrentes
# dentro da mesma instancia (nao resolve multiplos processos, mas ajuda).
_lock = Lock()


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _novo_id() -> str:
    return uuid.uuid4().hex[:8]


def _ler(arquivo: Path) -> list[dict]:
    if not arquivo.exists():
        return []
    try:
        return json.loads(arquivo.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def _escrever(arquivo: Path, dados: list[dict]) -> None:
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    arquivo.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ----------------------------------------------------------------------
# Usuarios
# ----------------------------------------------------------------------
def buscar_usuario_por_email(email: str) -> dict | None:
    email = email.strip().lower()
    for u in _ler(ARQ_USUARIOS):
        if u["email"] == email:
            return u
    return None


def buscar_usuario_por_id(id_: str) -> dict | None:
    for u in _ler(ARQ_USUARIOS):
        if u["id"] == id_:
            return u
    return None


def criar_usuario(nome: str, email: str, senha_hash: str, tipo: str) -> dict:
    """Cria um usuario. tipo: 'comum' ou 'ong'. Email precisa ser unico."""
    with _lock:
        usuarios = _ler(ARQ_USUARIOS)
        email = email.strip().lower()
        if any(u["email"] == email for u in usuarios):
            raise ValueError("Ja existe um usuario com este e-mail.")
        usuario = {
            "id": _novo_id(),
            "nome": nome.strip(),
            "email": email,
            "senha_hash": senha_hash,
            "tipo": tipo,
            "criado_em": _agora(),
        }
        usuarios.append(usuario)
        _escrever(ARQ_USUARIOS, usuarios)
        return usuario


# ----------------------------------------------------------------------
# ONGs
# ----------------------------------------------------------------------
def criar_ong(
    usuario_id: str,
    nome: str,
    tipo: str,
    contato: str,
    cidade: str,
    *,
    cnpj: str = "",
    telefone: str = "",
    street: str = "",
    state: str = "",
    zip_code: str = "",
    website: str = "",
    description: str = "",
) -> dict:
    """Cria uma ONG ligada a um usuario. tipo: 'resgate' ou 'adocao'.

    Campos cnpj/endereco vem dos specs do PetGo (Requisito 7). O CNPJ, se
    informado, precisa ser unico (requirements 2.7 / 5.1).
    """
    with _lock:
        ongs = _ler(ARQ_ONGS)
        cnpj = (cnpj or "").strip()
        if cnpj and any(o.get("cnpj") == cnpj for o in ongs):
            raise ValueError("Ja existe uma ONG com este CNPJ.")
        ong = {
            "id": _novo_id(),
            "usuario_id": usuario_id,
            "nome": nome.strip(),
            "tipo": tipo,
            "contato": contato.strip(),
            "telefone": telefone.strip(),
            "cnpj": cnpj,
            "street": street.strip(),
            "cidade": cidade.strip(),
            "state": state.strip(),
            "zip_code": zip_code.strip(),
            "website": website.strip(),
            "description": description.strip(),
            "criado_em": _agora(),
        }
        ongs.append(ong)
        _escrever(ARQ_ONGS, ongs)
        return ong


def ong_cnpj_existe(cnpj: str) -> bool:
    cnpj = (cnpj or "").strip()
    if not cnpj:
        return False
    return any(o.get("cnpj") == cnpj for o in _ler(ARQ_ONGS))


def listar_ongs() -> list[dict]:
    return _ler(ARQ_ONGS)


def buscar_ong_por_id(id_: str) -> dict | None:
    for o in _ler(ARQ_ONGS):
        if o["id"] == id_:
            return o
    return None


def buscar_ong_por_usuario(usuario_id: str) -> dict | None:
    for o in _ler(ARQ_ONGS):
        if o["usuario_id"] == usuario_id:
            return o
    return None


# ----------------------------------------------------------------------
# Alertas de localizacao (historico) -- ponte com o design (SNS/LocationAlert)
# ----------------------------------------------------------------------
def criar_alerta(dados: dict) -> dict:
    """Registra um alerta de localizacao enviado (requirements 3.3/3.4).

    So deve ser chamado APOS a publicacao bem-sucedida no notificador,
    garantindo a atomicidade do design (P4): sem message_id, nao grava.
    """
    with _lock:
        alertas = _ler(ARQ_ALERTAS)
        alerta = {"id": _novo_id(), "sent_at": _agora(), **dados}
        alertas.append(alerta)
        _escrever(ARQ_ALERTAS, alertas)
        return alerta


def listar_alertas() -> list[dict]:
    return _ler(ARQ_ALERTAS)


# ----------------------------------------------------------------------
# Animais
# ----------------------------------------------------------------------
def criar_animal(dados: dict) -> dict:
    with _lock:
        animais = _ler(ARQ_ANIMAIS)
        animal = {
            "id": _novo_id(),
            "criado_em": _agora(),
            "status": "aberto",
            **dados,
        }
        animais.append(animal)
        _escrever(ARQ_ANIMAIS, animais)
        return animal


def listar_animais() -> list[dict]:
    return _ler(ARQ_ANIMAIS)


def buscar_animal_por_id(id_: str) -> dict | None:
    for a in _ler(ARQ_ANIMAIS):
        if a["id"] == id_:
            return a
    return None


def atualizar_status_animal(id_: str, novo_status: str) -> dict | None:
    with _lock:
        animais = _ler(ARQ_ANIMAIS)
        alvo = None
        for a in animais:
            if a["id"] == id_:
                a["status"] = novo_status
                alvo = a
                break
        if alvo is not None:
            _escrever(ARQ_ANIMAIS, animais)
        return alvo
