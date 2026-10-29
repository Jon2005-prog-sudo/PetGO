"""Parte 2 - Solicitacao de Resgate (apenas o REGISTRO).

Coleta os dados de uma solicitacao de resgate, registra a foto do animal,
guarda a localizacao e salva tudo num arquivo JSON.

Rode com:  py main.py   (ou python main.py)
"""

from __future__ import annotations

import json
import shutil
import urllib.parse
import uuid
import webbrowser
from datetime import datetime
from pathlib import Path

# --- Onde as coisas sao salvas ---
PASTA_DADOS = Path("data")
ARQUIVO_JSON = PASTA_DADOS / "rescues.json"
PASTA_FOTOS = PASTA_DADOS / "photos"

EXTENSOES_IMAGEM = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
URGENCIAS = ["baixa", "media", "alta", "critica"]


# ----------------------------------------------------------------------
# Leitura de entrada (com validacao basica)
# ----------------------------------------------------------------------
def ler_texto(rotulo: str, obrigatorio: bool = True) -> str:
    while True:
        valor = input(f"{rotulo}: ").strip()
        if valor or not obrigatorio:
            return valor
        print("  -> Campo obrigatorio, tente de novo.")


def ler_coordenada(rotulo: str, mini: float, maxi: float) -> float | None:
    """Le uma coordenada. Enter vazio retorna None (coordenada opcional)."""
    while True:
        bruto = input(f"{rotulo}: ").strip().replace(",", ".")
        if not bruto:
            return None
        try:
            valor = float(bruto)
        except ValueError:
            print("  -> Numero invalido. Exemplo: -23.5505 (ou Enter para pular)")
            continue
        if mini <= valor <= maxi:
            return valor
        print(f"  -> Precisa estar entre {mini} e {maxi}.")


def ler_sim_nao(rotulo: str) -> bool:
    """Le uma resposta sim/nao. Aceita s/n (padrao: nao)."""
    resposta = input(f"{rotulo} (s/n) [n]: ").strip().lower()
    return resposta in ("s", "sim", "y", "yes")


def ler_urgencia() -> str:
    print("Urgencia:")
    for i, u in enumerate(URGENCIAS, start=1):
        print(f"  {i}) {u}")
    while True:
        escolha = input("Escolha (1-4) [2]: ").strip() or "2"
        if escolha.isdigit() and 1 <= int(escolha) <= len(URGENCIAS):
            return URGENCIAS[int(escolha) - 1]
        print("  -> Opcao invalida.")


# ----------------------------------------------------------------------
# Localizacao: link do Google Maps (por coordenadas ou por endereco)
# ----------------------------------------------------------------------
def montar_mapa_url(
    endereco: str, latitude: float | None = None, longitude: float | None = None
) -> str:
    """Gera um link do Google Maps.

    Se houver coordenadas, aponta para o ponto exato; senao, faz a busca
    pelo endereco por extenso.
    """
    if latitude is not None and longitude is not None:
        return f"https://www.google.com/maps?q={latitude},{longitude}"
    consulta = urllib.parse.quote_plus(endereco)
    return f"https://www.google.com/maps/search/?api=1&query={consulta}"


def abrir_no_mapa(url: str) -> None:
    """Abre o link do mapa no navegador padrao."""
    try:
        webbrowser.open(url)
        print(f"  -> Abrindo no navegador: {url}")
    except Exception as erro:  # nao travar o registro se o navegador falhar
        print(f"  [AVISO] Nao foi possivel abrir o navegador: {erro}")
        print(f"          Abra manualmente: {url}")


# ----------------------------------------------------------------------
# Foto do animal: valida e copia pra pasta do projeto
# ----------------------------------------------------------------------
def registrar_foto(caminho_origem: str) -> str:
    """Valida e copia a imagem para data/photos. Retorna o novo caminho."""
    origem = Path(caminho_origem).expanduser()
    if not origem.is_file():
        raise ValueError(f"Arquivo de foto nao encontrado: {origem}")
    if origem.suffix.lower() not in EXTENSOES_IMAGEM:
        raise ValueError(
            "Extensao de imagem invalida. Use: " + ", ".join(sorted(EXTENSOES_IMAGEM))
        )
    PASTA_FOTOS.mkdir(parents=True, exist_ok=True)
    destino = PASTA_FOTOS / f"{uuid.uuid4().hex[:12]}{origem.suffix.lower()}"
    shutil.copy2(origem, destino)
    return str(destino)


# ----------------------------------------------------------------------
# Salvar no JSON (anexa a solicitacao a lista existente)
# ----------------------------------------------------------------------
def salvar(solicitacao: dict) -> None:
    PASTA_DADOS.mkdir(parents=True, exist_ok=True)
    if ARQUIVO_JSON.exists():
        try:
            lista = json.loads(ARQUIVO_JSON.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            lista = []
    else:
        lista = []
    lista.append(solicitacao)
    ARQUIVO_JSON.write_text(
        json.dumps(lista, ensure_ascii=False, indent=2), encoding="utf-8"
    )


# ----------------------------------------------------------------------
# Monta o dicionario da solicitacao (logica pura, facil de testar)
# ----------------------------------------------------------------------
def montar_solicitacao(
    *,
    nome: str,
    contato: str,
    endereco: str,
    latitude: float | None = None,
    longitude: float | None = None,
    especie: str,
    porte: str,
    estado_saude: str,
    descricao: str,
    urgencia: str,
    foto_path: str = "",
) -> dict:
    """Monta a estrutura da solicitacao a partir de dados ja coletados.

    O endereco e obrigatorio; latitude/longitude sao opcionais (ficam
    None quando a pessoa nao pega o ponto exato no mapa).
    """
    return {
        "id": uuid.uuid4().hex[:8],
        "criado_em": datetime.now().isoformat(timespec="seconds"),
        "status": "aberto",
        "solicitante": {"nome": nome, "contato": contato},
        "localizacao": {
            "endereco": endereco,
            "latitude": latitude,
            "longitude": longitude,
            "mapa_url": montar_mapa_url(endereco, latitude, longitude),
        },
        "animal": {
            "especie": especie,
            "porte": porte,
            "estado_saude": estado_saude,
            "descricao": descricao,
            "urgencia": urgencia,
        },
        "foto_path": foto_path,
    }


# ----------------------------------------------------------------------
# Fluxo de registro (interativo)
# ----------------------------------------------------------------------
def registrar_solicitacao() -> None:
    print("\n=== Nova solicitacao de resgate ===\n")

    print("-- Quem esta solicitando --")
    nome = ler_texto("Nome")
    contato = ler_texto("Contato (telefone/e-mail)")

    print("\n-- Localizacao do resgate --")
    endereco = ler_texto("Endereco (rua, numero, bairro, cidade)")

    latitude = None
    longitude = None
    if ler_sim_nao("Quer conferir/ajustar o local no mapa do Google?"):
        abrir_no_mapa(montar_mapa_url(endereco))
        print("  Dica: no mapa, clique no ponto exato, copie as coordenadas")
        print("        (ex.: -23.5505, -46.6333) e cole abaixo. Ou deixe em branco.")
        if ler_sim_nao("Quer informar as coordenadas exatas do mapa?"):
            latitude = ler_coordenada("  Latitude (Enter para pular)", -90.0, 90.0)
            longitude = ler_coordenada("  Longitude (Enter para pular)", -180.0, 180.0)

    print("\n-- Sobre o animal --")
    especie = ler_texto("Especie (ex.: cachorro, gato)")
    porte = ler_texto("Porte (ex.: pequeno, medio, grande)")
    estado_saude = ler_texto("Estado de saude (ex.: ferido, debilitado, ok)")
    descricao = ler_texto("Descricao da situacao")
    urgencia = ler_urgencia()

    print("\n-- Foto do animal --")
    foto_path = ""
    caminho_foto = ler_texto(
        "Caminho do arquivo de imagem (Enter para pular)", obrigatorio=False
    )
    if caminho_foto:
        try:
            foto_path = registrar_foto(caminho_foto)
        except ValueError as erro:
            print(f"  [AVISO] Foto nao registrada: {erro}")

    solicitacao = montar_solicitacao(
        nome=nome,
        contato=contato,
        endereco=endereco,
        latitude=latitude,
        longitude=longitude,
        especie=especie,
        porte=porte,
        estado_saude=estado_saude,
        descricao=descricao,
        urgencia=urgencia,
        foto_path=foto_path,
    )

    salvar(solicitacao)

    print(f"\n[OK] Solicitacao registrada! ID: {solicitacao['id']}")
    print(f"     Salva em: {ARQUIVO_JSON}")
    print(f"     Mapa: {solicitacao['localizacao']['mapa_url']}")


if __name__ == "__main__":
    registrar_solicitacao()
