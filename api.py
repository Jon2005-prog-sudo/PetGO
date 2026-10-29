"""Parte 2 - API de Solicitacao de Resgate.

Expoe via HTTP a logica de registro que ja existe em main.py, para que
as outras partes do projeto (3 - encontrar animal, 4 - encontrar lar)
possam criar e consultar solicitacoes de resgate.

Endpoints:
  GET    /health                 -> checagem simples (uptime/load balancer)
  POST   /solicitacoes           -> cria uma solicitacao (multipart ou JSON)
  GET    /solicitacoes           -> lista todas as solicitacoes
  GET    /solicitacoes/<id>      -> busca uma solicitacao pelo id
  GET    /solicitacoes/<id>/foto -> baixa a foto do animal
  PATCH  /solicitacoes/<id>      -> atualiza o status

Rodar em desenvolvimento:
  py api.py
Rodar em producao (no EC2) use gunicorn:
  gunicorn --bind 0.0.0.0:8000 api:app
"""

from __future__ import annotations

import json
import uuid

from flask import Flask, jsonify, request, send_file, abort

import main  # reaproveita a logica de registro ja existente

app = Flask(__name__)

# Limita o tamanho do upload (ex.: 10 MB) para nao estourar o disco.
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024

STATUS_VALIDOS = {"aberto", "em andamento", "resolvido"}


# ----------------------------------------------------------------------
# Helpers
# ----------------------------------------------------------------------
def salvar_foto_upload(arquivo) -> str:
    """Salva uma foto enviada por upload (werkzeug FileStorage).

    Valida a extensao (reaproveita EXTENSOES_IMAGEM do main) e grava em
    data/photos. Retorna o caminho salvo.
    """
    from pathlib import Path

    nome_original = arquivo.filename or ""
    extensao = Path(nome_original).suffix.lower()
    if extensao not in main.EXTENSOES_IMAGEM:
        raise ValueError(
            "Extensao de imagem invalida. Use: "
            + ", ".join(sorted(main.EXTENSOES_IMAGEM))
        )
    main.PASTA_FOTOS.mkdir(parents=True, exist_ok=True)
    destino = main.PASTA_FOTOS / f"{uuid.uuid4().hex[:12]}{extensao}"
    arquivo.save(str(destino))
    return str(destino)


def ler_float_opcional(valor):
    """Converte para float; devolve None se vazio/ausente/invalido-vazio."""
    if valor is None or str(valor).strip() == "":
        return None
    return float(str(valor).replace(",", "."))


def carregar_todas() -> list[dict]:
    if not main.ARQUIVO_JSON.exists():
        return []
    try:
        return json.loads(main.ARQUIVO_JSON.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


# ----------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------
@app.get("/health")
def health():
    return jsonify({"status": "ok"})


@app.post("/solicitacoes")
def criar():
    """Cria uma solicitacao.

    Aceita multipart/form-data (com campo 'foto' opcional) ou JSON puro.
    Campos: nome, contato, endereco (obrigatorios), latitude, longitude,
    especie, porte, estado_saude, descricao, urgencia.
    """
    # Suporta tanto form (com upload de foto) quanto JSON.
    if request.content_type and "application/json" in request.content_type:
        dados = request.get_json(silent=True) or {}
        arquivo_foto = None
    else:
        dados = request.form
        arquivo_foto = request.files.get("foto")

    # Validacao dos obrigatorios.
    obrigatorios = ["nome", "contato", "endereco", "especie", "descricao"]
    faltando = [c for c in obrigatorios if not str(dados.get(c, "")).strip()]
    if faltando:
        return jsonify({"erro": "campos obrigatorios ausentes", "campos": faltando}), 400

    try:
        latitude = ler_float_opcional(dados.get("latitude"))
        longitude = ler_float_opcional(dados.get("longitude"))
    except ValueError:
        return jsonify({"erro": "latitude/longitude devem ser numeros"}), 400

    if latitude is not None and not (-90.0 <= latitude <= 90.0):
        return jsonify({"erro": "latitude fora do intervalo -90..90"}), 400
    if longitude is not None and not (-180.0 <= longitude <= 180.0):
        return jsonify({"erro": "longitude fora do intervalo -180..180"}), 400

    urgencia = str(dados.get("urgencia", "media")).strip().lower()
    if urgencia not in main.URGENCIAS:
        return jsonify(
            {"erro": "urgencia invalida", "valores": main.URGENCIAS}
        ), 400

    # Foto (opcional).
    foto_path = ""
    if arquivo_foto and arquivo_foto.filename:
        try:
            foto_path = salvar_foto_upload(arquivo_foto)
        except ValueError as erro:
            return jsonify({"erro": str(erro)}), 400

    # Reaproveita a logica de montagem e salvamento do main.py.
    solicitacao = main.montar_solicitacao(
        nome=str(dados.get("nome")).strip(),
        contato=str(dados.get("contato")).strip(),
        endereco=str(dados.get("endereco")).strip(),
        latitude=latitude,
        longitude=longitude,
        especie=str(dados.get("especie")).strip(),
        porte=str(dados.get("porte", "")).strip(),
        estado_saude=str(dados.get("estado_saude", "")).strip(),
        descricao=str(dados.get("descricao")).strip(),
        urgencia=urgencia,
        foto_path=foto_path,
    )
    main.salvar(solicitacao)
    return jsonify(solicitacao), 201


@app.get("/solicitacoes")
def listar():
    return jsonify(carregar_todas())


@app.get("/solicitacoes/<id_>")
def obter(id_):
    for s in carregar_todas():
        if s["id"] == id_:
            return jsonify(s)
    abort(404, description="Solicitacao nao encontrada")


@app.get("/solicitacoes/<id_>/foto")
def obter_foto(id_):
    for s in carregar_todas():
        if s["id"] == id_:
            caminho = s.get("foto_path")
            if not caminho:
                abort(404, description="Esta solicitacao nao tem foto")
            from pathlib import Path

            if not Path(caminho).is_file():
                abort(404, description="Arquivo de foto nao encontrado no servidor")
            return send_file(caminho)
    abort(404, description="Solicitacao nao encontrada")


@app.patch("/solicitacoes/<id_>")
def atualizar_status(id_):
    dados = request.get_json(silent=True) or {}
    novo = str(dados.get("status", "")).strip().lower()
    if novo not in STATUS_VALIDOS:
        return jsonify(
            {"erro": "status invalido", "valores": sorted(STATUS_VALIDOS)}
        ), 400

    todas = carregar_todas()
    encontrada = None
    for s in todas:
        if s["id"] == id_:
            s["status"] = novo
            encontrada = s
            break
    if encontrada is None:
        abort(404, description="Solicitacao nao encontrada")

    main.ARQUIVO_JSON.write_text(
        json.dumps(todas, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return jsonify(encontrada)


# Respostas de erro em JSON (mais util para quem consome a API).
@app.errorhandler(404)
def nao_encontrado(e):
    return jsonify({"erro": getattr(e, "description", "nao encontrado")}), 404


@app.errorhandler(413)
def muito_grande(e):
    return jsonify({"erro": "arquivo muito grande (limite 10 MB)"}), 413


if __name__ == "__main__":
    # Desenvolvimento local. Em producao use gunicorn (ver docstring).
    app.run(host="0.0.0.0", port=8000, debug=True)
