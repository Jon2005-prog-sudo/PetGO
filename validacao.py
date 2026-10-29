"""Validacoes de entrada (ponte com os specs do PetGo).

Implementa, em Python puro, as regras que o design/requirements pedem via
Pydantic no PetGo original:
  - senha forte (requirements 4.2 / 6.1)
  - telefone em Formato_E164 (requirements 4.3)
  - CNPJ em Formato_CNPJ, 14 digitos (requirements 4.7 / 7.x)

Cada funcao levanta ValueError com mensagem clara quando invalida.
"""

from __future__ import annotations

import re

_RE_E164 = re.compile(r"^\+[1-9]\d{7,14}$")
_RE_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def validar_email(email: str) -> str:
    email = (email or "").strip().lower()
    if not _RE_EMAIL.match(email):
        raise ValueError("E-mail invalido.")
    return email


def validar_senha(senha: str) -> None:
    """Minimo 8 caracteres, ao menos uma letra e um numero (requirements 4.2)."""
    if len(senha or "") < 8:
        raise ValueError("A senha deve ter ao menos 8 caracteres.")
    if not re.search(r"[A-Za-z]", senha) or not re.search(r"\d", senha):
        raise ValueError("A senha deve conter ao menos uma letra e um numero.")


def validar_telefone_e164(phone: str) -> str:
    """Formato_E164, ex.: +5511999998888 (requirements 4.3)."""
    phone = (phone or "").strip()
    if not _RE_E164.match(phone):
        raise ValueError("Telefone deve estar no formato E.164, ex.: +5511999998888.")
    return phone


def validar_cnpj(cnpj: str) -> str:
    """Valida CNPJ (14 digitos) com digitos verificadores (requirements 4.7).

    Aceita com ou sem mascara; retorna so os digitos.
    """
    digitos = re.sub(r"\D", "", cnpj or "")
    if len(digitos) != 14:
        raise ValueError("CNPJ deve ter 14 digitos.")
    if digitos == digitos[0] * 14:
        raise ValueError("CNPJ invalido.")

    def dv(base: str, pesos: list[int]) -> str:
        soma = sum(int(d) * p for d, p in zip(base, pesos))
        resto = soma % 11
        return "0" if resto < 2 else str(11 - resto)

    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    d1 = dv(digitos[:12], pesos1)
    d2 = dv(digitos[:12] + d1, pesos2)
    if digitos[12:] != d1 + d2:
        raise ValueError("CNPJ invalido (digitos verificadores).")
    return digitos
