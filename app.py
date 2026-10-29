"""Aplicacao web de resgate de animais (camada web sobre o dominio).

Expoe TODAS as features do pacote `domain/` pela interface web, usando
persistencia em JSON via JsonRepo. Cobre:

  - Cadastro/login de usuarios (ADOPTER por padrao).
  - Pedido de verificacao de protetor + painel de ADMIN que aprova/rejeita.
  - Cadastro e ciclo de vida de animais (protetor).
  - Vitrine publica (so animais AVAILABLE) com filtros.
  - Pedidos de adocao (adotante) + revisao (protetor).
  - Denuncias de resgate + assumir resgate (protetor).
  - Notificacoes do usuario.
  - API JSON simples (/api/...).

O objeto WSGI continua sendo `app` (ou seja, `app:app`).

Dev:        py app.py
Producao:   gunicorn --bind 127.0.0.1:8000 app:app   (Apache faz o proxy)
"""

from __future__ import annotations

import os
import uuid
from functools import wraps
from pathlib import Path

from flask import (
    Flask,
    jsonify,
    redirect,
    render_template,
    request,
    session,
    send_file,
    url_for,
    flash,
    abort,
)
from werkzeug.middleware.proxy_fix import ProxyFix
from werkzeug.security import generate_password_hash, check_password_hash

import validacao
from domain.json_repo import JsonRepo, PASTA_FOTOS
from domain.users import UserService
from domain.animals import AnimalService
from domain.adoption import AdoptionService
from domain.rescue import RescueService
from domain.types import (
    Role,
    AnimalStatus,
    AdoptionStatus,
    ANIMAL_TRANSITIONS,
)
from domain.errors import (
    DomainError,
    NotAuthorized,
    NotFound,
    ValidationError,
    InvalidTransition,
    AnimalNotAvailable,
    DuplicateActiveRequest,
    Conflict,
)

# ----------------------------------------------------------------------
# Repositorio e servicos de dominio
# ----------------------------------------------------------------------
repo = JsonRepo()
user_service = UserService(repo)
animal_service = AnimalService(repo)
adoption_service = AdoptionService(repo)
rescue_service = RescueService(repo)

# ----------------------------------------------------------------------
# App Flask
# ----------------------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-troque-esta-chave-em-producao")
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10 MB por upload

EXTENSOES_IMAGEM = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}

# Valores aceitos nos formularios (espelham o dominio).
SIZES = ["SMALL", "MEDIUM", "LARGE"]
SEXES = ["MALE", "FEMALE", "UNKNOWN"]

# Rotulos amigaveis (pt-BR) para exibir os enums de status.
STATUS_LABEL = {
    AnimalStatus.NEEDS_RESCUE.value: "Precisa de resgate",
    AnimalStatus.IN_RESCUE.value: "Em resgate",
    AnimalStatus.SHELTERED.value: "Abrigado",
    AnimalStatus.AVAILABLE.value: "Disponivel para adocao",
    AnimalStatus.ADOPTED.value: "Adotado",
    AnimalStatus.UNAVAILABLE.value: "Indisponivel",
    AdoptionStatus.SENT.value: "Enviado",
    AdoptionStatus.UNDER_REVIEW.value: "Em analise",
    AdoptionStatus.APPROVED.value: "Aprovado",
    AdoptionStatus.REJECTED.value: "Rejeitado",
    AdoptionStatus.CANCELLED.value: "Cancelado",
}

SIZE_LABEL = {"SMALL": "Pequeno", "MEDIUM": "Medio", "LARGE": "Grande"}
SEX_LABEL = {"MALE": "Macho", "FEMALE": "Femea", "UNKNOWN": "Nao informado"}

# Credenciais do ADMIN semente (criado na primeira execucao).
ADMIN_EMAIL = "admin@local"
ADMIN_SENHA = "admin12345"


# ----------------------------------------------------------------------
# ADMIN semente
# ----------------------------------------------------------------------
def garantir_admin_semente() -> None:
    """Cria um usuario ADMIN na primeira execucao, se nao existir nenhum.

    Permite que o fluxo de verificacao de protetor funcione localmente de
    ponta a ponta (sem depender de outro admin ja cadastrado).
    """
    ja_tem_admin = any(
        u.get("role") == Role.ADMIN.value for u in repo.all_usuarios()
    )
    if ja_tem_admin:
        return
    # Se o e-mail ja existe (mas nao e admin), nao recria.
    if any(u.get("email") == ADMIN_EMAIL for u in repo.all_usuarios()):
        return
    admin = user_service.register(
        nome="Administrador",
        email=ADMIN_EMAIL,
        senha_hash=generate_password_hash(ADMIN_SENHA),
        role=Role.ADOPTER,
    )
    admin["role"] = Role.ADMIN
    repo.save_usuario(admin)


garantir_admin_semente()


# ----------------------------------------------------------------------
# Helpers de autenticacao / contexto
# ----------------------------------------------------------------------
def usuario_atual() -> dict | None:
    uid = session.get("usuario_id")
    return repo.get_usuario(uid) if uid else None


def login_obrigatorio(f):
    @wraps(f)
    def wrapper(*args, **kwargs):
        if "usuario_id" not in session or usuario_atual() is None:
            if request.path.startswith("/api/"):
                return jsonify({"erro": "autenticacao necessaria"}), 401
            return redirect(url_for("login", next=request.path))
        return f(*args, **kwargs)

    return wrapper


def papel_obrigatorio(*roles):
    """Exige que o usuario logado tenha um dos papeis informados."""
    valores = {r.value if isinstance(r, Role) else r for r in roles}

    def deco(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            u = usuario_atual()
            if u is None:
                return redirect(url_for("login", next=request.path))
            if u.get("role") not in valores:
                abort(403, description="Voce nao tem permissao para acessar isto.")
            return f(*args, **kwargs)

        return wrapper

    return deco


@app.context_processor
def injetar_contexto():
    return {
        "usuario": usuario_atual(),
        "Role": Role,
        "STATUS_LABEL": STATUS_LABEL,
        "SIZE_LABEL": SIZE_LABEL,
        "SEX_LABEL": SEX_LABEL,
    }


# ----------------------------------------------------------------------
# Helpers diversos
# ----------------------------------------------------------------------
def salvar_foto(arquivo) -> str:
    """Valida e salva uma foto enviada por upload. Retorna o caminho (str)."""
    nome = arquivo.filename or ""
    ext = Path(nome).suffix.lower()
    if ext not in EXTENSOES_IMAGEM:
        raise ValueError(
            "Extensao de imagem invalida. Use: " + ", ".join(sorted(EXTENSOES_IMAGEM))
        )
    PASTA_FOTOS.mkdir(parents=True, exist_ok=True)
    destino = PASTA_FOTOS / f"{uuid.uuid4().hex[:12]}{ext}"
    arquivo.save(str(destino))
    return str(destino)


def inteiro_opcional(valor):
    if valor is None or str(valor).strip() == "":
        return None
    return int(str(valor).strip())


def flash_erro_dominio(e: Exception) -> None:
    """Traduz uma excecao de dominio em mensagem flash amigavel."""
    flash(str(e) or "Nao foi possivel concluir a operacao.", "erro")


def _transicoes_validas(status_atual: str) -> list[str]:
    """Lista os proximos status validos (strings) a partir do atual."""
    try:
        atual = AnimalStatus(status_atual)
    except ValueError:
        return []
    return [s.value for s in ANIMAL_TRANSITIONS.get(atual, [])]


# ----------------------------------------------------------------------
# Vitrine publica
# ----------------------------------------------------------------------
@app.get("/")
def home():
    filtros = {
        "species": request.args.get("species", "").strip(),
        "size": request.args.get("size", "").strip(),
        "sex": request.args.get("sex", "").strip(),
        "locationCity": request.args.get("locationCity", "").strip(),
        "ageMonthsMax": request.args.get("ageMonthsMax", "").strip(),
    }
    filtro_dominio = {}
    for chave in ("species", "size", "sex", "locationCity"):
        if filtros[chave]:
            filtro_dominio[chave] = filtros[chave]
    if filtros["ageMonthsMax"]:
        try:
            filtro_dominio["ageMonthsMax"] = int(filtros["ageMonthsMax"])
        except ValueError:
            filtros["ageMonthsMax"] = ""

    try:
        resultado = animal_service.list_available(filtro_dominio, offset=0, limit=100)
        itens = resultado["items"]
    except DomainError:
        itens = []
    return render_template(
        "home.html", items=itens, filtros=filtros, sizes=SIZES, sexes=SEXES
    )


# ----------------------------------------------------------------------
# Cadastro / login
# ----------------------------------------------------------------------
@app.route("/registrar", methods=["GET", "POST"])
def registrar():
    if request.method == "GET":
        return render_template("registrar.html")

    nome = request.form.get("nome", "").strip()
    email = request.form.get("email", "").strip()
    senha = request.form.get("senha", "")

    if not nome or not email or not senha:
        flash("Preencha nome, e-mail e senha.", "erro")
        return redirect(url_for("registrar"))

    try:
        email = validacao.validar_email(email)
        validacao.validar_senha(senha)
    except ValueError as e:
        flash(str(e), "erro")
        return redirect(url_for("registrar"))

    try:
        usuario = user_service.register(
            nome=nome,
            email=email,
            senha_hash=generate_password_hash(senha),
            role=Role.ADOPTER,
        )
    except DomainError as e:
        flash_erro_dominio(e)
        return redirect(url_for("registrar"))

    session["usuario_id"] = usuario["id"]
    flash("Cadastro realizado! Voce ja esta logado.", "ok")
    return redirect(url_for("home"))


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "GET":
        return render_template("login.html")

    email = (request.form.get("email", "") or "").strip().lower()
    senha = request.form.get("senha", "")
    usuario = next(
        (u for u in repo.all_usuarios() if u.get("email") == email), None
    )
    if usuario is None or not check_password_hash(usuario.get("passwordHash", ""), senha):
        flash("E-mail ou senha incorretos.", "erro")
        return redirect(url_for("login"))

    session["usuario_id"] = usuario["id"]
    destino = request.args.get("next") or url_for("home")
    return redirect(destino)


@app.get("/logout")
def logout():
    session.clear()
    flash("Voce saiu da conta.", "ok")
    return redirect(url_for("home"))


# ----------------------------------------------------------------------
# Verificacao de protetor
# ----------------------------------------------------------------------
@app.route("/tornar-protetor", methods=["GET", "POST"])
@login_obrigatorio
def tornar_protetor():
    u = usuario_atual()
    if u.get("role") == Role.PROTECTOR.value:
        flash("Voce ja e um protetor verificado.", "ok")
        return redirect(url_for("painel"))
    if u.get("role") == Role.ADMIN.value:
        flash("Administradores nao precisam solicitar verificacao.", "ok")
        return redirect(url_for("home"))

    if request.method == "GET":
        return render_template("tornar_protetor.html")

    org_name = request.form.get("org_name", "").strip()
    document_url = request.form.get("document_url", "").strip()
    if not org_name:
        flash("Informe o nome da organizacao/protetor.", "erro")
        return redirect(url_for("tornar_protetor"))

    try:
        user_service.request_protector_verification(
            u["id"], org_name, document_url
        )
    except DomainError as e:
        flash_erro_dominio(e)
        return redirect(url_for("tornar_protetor"))

    flash(
        "Pedido enviado! Aguarde a aprovacao de um administrador.", "ok"
    )
    return redirect(url_for("home"))


# ----------------------------------------------------------------------
# Painel do ADMIN
# ----------------------------------------------------------------------
@app.get("/admin")
@papel_obrigatorio(Role.ADMIN)
def admin():
    pendentes = user_service.list_pending_applications()
    # Enriquecer com dados do solicitante.
    linhas = []
    for app_ in pendentes:
        solicitante = repo.get_usuario(app_["userId"])
        linhas.append({"app": app_, "usuario": solicitante})
    return render_template("admin.html", linhas=linhas)


@app.post("/admin/decidir")
@papel_obrigatorio(Role.ADMIN)
def admin_decidir():
    admin_user = usuario_atual()
    user_id = request.form.get("user_id", "").strip()
    decision = request.form.get("decision", "").strip().upper()
    reason = request.form.get("reason", "").strip()
    if decision not in ("APPROVE", "REJECT"):
        flash("Decisao invalida.", "erro")
        return redirect(url_for("admin"))
    try:
        user_service.decide_protector_verification(
            admin_user["id"], user_id, decision, reason
        )
        # Marca a aplicacao correspondente (a mais recente PENDING deste user).
        for a in user_service.list_pending_applications():
            if a["userId"] == user_id:
                a["status"] = (
                    "APPROVED" if decision == "APPROVE" else "REJECTED"
                )
                a["reason"] = reason
                repo.save_aplicacao(a)
    except DomainError as e:
        flash_erro_dominio(e)
        return redirect(url_for("admin"))

    flash("Decisao registrada.", "ok")
    return redirect(url_for("admin"))


# ----------------------------------------------------------------------
# Cadastro de animal (protetor)
# ----------------------------------------------------------------------
@app.route("/animais/novo", methods=["GET", "POST"])
@papel_obrigatorio(Role.PROTECTOR)
def novo_animal():
    if request.method == "GET":
        return render_template("novo_animal.html", sizes=SIZES, sexes=SEXES)

    u = usuario_atual()
    descricao = request.form.get("description", "").strip()
    if not descricao:
        flash("A descricao e obrigatoria.", "erro")
        return redirect(url_for("novo_animal"))

    try:
        age_months = inteiro_opcional(request.form.get("ageMonths"))
    except ValueError:
        flash("Idade (meses) deve ser um numero inteiro.", "erro")
        return redirect(url_for("novo_animal"))

    photos = []
    arquivo = request.files.get("foto")
    if arquivo and arquivo.filename:
        try:
            photos.append(salvar_foto(arquivo))
        except ValueError as e:
            flash(str(e), "erro")
            return redirect(url_for("novo_animal"))

    size = request.form.get("size", "").strip() or None
    sex = request.form.get("sex", "").strip() or None

    dados = {
        "name": request.form.get("name", "").strip(),
        "species": request.form.get("species", "").strip(),
        "breed": request.form.get("breed", "").strip() or None,
        "size": size if size in SIZES else None,
        "sex": sex if sex in SEXES else None,
        "ageMonths": age_months,
        "description": descricao,
        "locationCity": request.form.get("locationCity", "").strip(),
        "photos": photos,
    }

    try:
        animal = animal_service.create_animal(u["id"], dados)
    except DomainError as e:
        flash_erro_dominio(e)
        return redirect(url_for("novo_animal"))

    flash("Animal cadastrado (status: abrigado).", "ok")
    return redirect(url_for("painel"))


# ----------------------------------------------------------------------
# Painel do protetor: meus animais + pedidos recebidos
# ----------------------------------------------------------------------
@app.get("/painel")
@papel_obrigatorio(Role.PROTECTOR)
def painel():
    u = usuario_atual()
    meus = [
        a for a in repo.all_animais() if a.get("protectorId") == u["id"]
    ]
    linhas = []
    for animal in meus:
        pedidos = adoption_service.list_requests_for_animal(animal["id"])
        pedidos_view = []
        for p in pedidos:
            adotante = repo.get_usuario(p["adopterId"])
            pedidos_view.append(
                {"pedido": p, "adotante": adotante}
            )
        linhas.append(
            {
                "animal": animal,
                "transicoes": _transicoes_validas(animal["status"]),
                "pedidos": pedidos_view,
            }
        )
    return render_template("painel.html", linhas=linhas)


@app.post("/animais/<id_>/status")
@papel_obrigatorio(Role.PROTECTOR)
def mudar_status(id_):
    u = usuario_atual()
    novo = request.form.get("status", "").strip()
    try:
        animal_service.change_status(u["id"], id_, AnimalStatus(novo))
    except ValueError:
        flash("Status invalido.", "erro")
        return redirect(url_for("painel"))
    except DomainError as e:
        flash_erro_dominio(e)
        return redirect(url_for("painel"))
    flash("Status atualizado.", "ok")
    return redirect(url_for("painel"))


@app.post("/pedidos/<id_>/revisar")
@papel_obrigatorio(Role.PROTECTOR, Role.ADMIN)
def revisar_pedido(id_):
    u = usuario_atual()
    decision = request.form.get("decision", "").strip().upper()
    note = request.form.get("note", "").strip()
    try:
        adoption_service.review_request(u["id"], id_, decision, note)
    except DomainError as e:
        flash_erro_dominio(e)
        return redirect(url_for("painel"))
    flash("Pedido revisado.", "ok")
    return redirect(url_for("painel"))


# ----------------------------------------------------------------------
# Detalhe do animal + pedido de adocao
# ----------------------------------------------------------------------
@app.get("/animais/<id_>")
def animal_detail(id_):
    try:
        animal = animal_service.get_animal(id_)
    except NotFound:
        abort(404, description="Animal nao encontrado")
    protetor = repo.get_usuario(animal.get("protectorId")) if animal.get("protectorId") else None
    return render_template("animal_detail.html", animal=animal, protetor=protetor)


@app.post("/animais/<id_>/adotar")
@login_obrigatorio
def adotar(id_):
    u = usuario_atual()
    message = request.form.get("message", "").strip()
    try:
        adoption_service.create_request(u["id"], id_, message)
    except DomainError as e:
        flash_erro_dominio(e)
        return redirect(url_for("animal_detail", id_=id_))
    flash("Pedido de adocao enviado!", "ok")
    return redirect(url_for("meus_pedidos"))


# ----------------------------------------------------------------------
# Meus pedidos (adotante)
# ----------------------------------------------------------------------
@app.get("/meus-pedidos")
@login_obrigatorio
def meus_pedidos():
    u = usuario_atual()
    pedidos = adoption_service.list_requests_by_adopter(u["id"])
    linhas = []
    for p in pedidos:
        animal = repo.get_animal(p["animalId"])
        linhas.append({"pedido": p, "animal": animal})
    return render_template("meus_pedidos.html", linhas=linhas)


@app.post("/pedidos/<id_>/cancelar")
@login_obrigatorio
def cancelar_pedido(id_):
    u = usuario_atual()
    try:
        adoption_service.cancel_request(u["id"], id_)
    except DomainError as e:
        flash_erro_dominio(e)
        return redirect(url_for("meus_pedidos"))
    flash("Pedido cancelado.", "ok")
    return redirect(url_for("meus_pedidos"))


# ----------------------------------------------------------------------
# Denuncias de resgate
# ----------------------------------------------------------------------
@app.route("/reportar", methods=["GET", "POST"])
@login_obrigatorio
def reportar():
    if request.method == "GET":
        return render_template("reportar.html")

    u = usuario_atual()
    descricao = request.form.get("description", "").strip()
    photos = []
    arquivo = request.files.get("foto")
    if arquivo and arquivo.filename:
        try:
            photos.append(salvar_foto(arquivo))
        except ValueError as e:
            flash(str(e), "erro")
            return redirect(url_for("reportar"))

    dados = {
        "description": descricao,
        "latitude": request.form.get("latitude", "").strip(),
        "longitude": request.form.get("longitude", "").strip(),
        "locationCity": request.form.get("locationCity", "").strip(),
        "photos": photos,
    }
    try:
        rescue_service.report_animal(u["id"], dados)
    except DomainError as e:
        flash_erro_dominio(e)
        return redirect(url_for("reportar"))

    flash("Denuncia registrada! Protetores poderao assumir o resgate.", "ok")
    return redirect(url_for("home"))


@app.get("/denuncias")
@papel_obrigatorio(Role.PROTECTOR)
def denuncias():
    abertas = rescue_service.list_open_reports()
    return render_template("denuncias.html", denuncias=abertas)


@app.post("/denuncias/<id_>/assumir")
@papel_obrigatorio(Role.PROTECTOR)
def assumir_denuncia(id_):
    u = usuario_atual()
    try:
        rescue_service.assume_rescue(u["id"], id_)
    except DomainError as e:
        flash_erro_dominio(e)
        return redirect(url_for("denuncias"))
    flash("Resgate assumido! O animal aparece no seu painel (em resgate).", "ok")
    return redirect(url_for("painel"))


# ----------------------------------------------------------------------
# Notificacoes
# ----------------------------------------------------------------------
@app.get("/notificacoes")
@login_obrigatorio
def notificacoes():
    u = usuario_atual()
    itens = repo.notificacoes_do_usuario(u["id"])
    return render_template("notificacoes.html", notificacoes=itens)


# ----------------------------------------------------------------------
# API JSON
# ----------------------------------------------------------------------
@app.get("/api/health")
def api_health():
    return jsonify({"status": "ok"})


@app.get("/api/animais")
def api_listar_animais():
    try:
        resultado = animal_service.list_available({}, offset=0, limit=100)
        return jsonify(resultado["items"])
    except DomainError:
        return jsonify([])


@app.get("/api/animais/<id_>")
def api_obter_animal(id_):
    try:
        animal = animal_service.get_animal(id_)
    except NotFound:
        abort(404, description="Animal nao encontrado")
    return jsonify(animal)


@app.get("/api/animais/<id_>/foto")
def api_foto_animal(id_):
    try:
        animal = animal_service.get_animal(id_)
    except NotFound:
        abort(404, description="Animal nao encontrado")
    photos = animal.get("photos") or []
    if not photos:
        abort(404, description="Foto nao encontrada")
    caminho = photos[0]
    if not caminho or not Path(caminho).is_file():
        abort(404, description="Foto nao encontrada")
    return send_file(caminho)


# ----------------------------------------------------------------------
# Tratamento de erros
# ----------------------------------------------------------------------
@app.errorhandler(NotAuthorized)
def _erro_nao_autorizado(e):
    if request.path.startswith("/api/"):
        return jsonify({"erro": str(e)}), 403
    return render_template("erro.html", codigo=403, mensagem=str(e)), 403


@app.errorhandler(NotFound)
def _erro_nao_encontrado(e):
    if request.path.startswith("/api/"):
        return jsonify({"erro": str(e)}), 404
    return render_template("erro.html", codigo=404, mensagem=str(e)), 404


@app.errorhandler(ValidationError)
@app.errorhandler(InvalidTransition)
@app.errorhandler(AnimalNotAvailable)
@app.errorhandler(DuplicateActiveRequest)
@app.errorhandler(Conflict)
def _erro_regra(e):
    if request.path.startswith("/api/"):
        return jsonify({"erro": str(e)}), 400
    flash(str(e) or "Operacao invalida.", "erro")
    return redirect(request.referrer or url_for("home"))


@app.errorhandler(403)
def erro_403(e):
    if request.path.startswith("/api/"):
        return jsonify({"erro": getattr(e, "description", "sem permissao")}), 403
    return render_template(
        "erro.html", codigo=403, mensagem=getattr(e, "description", "Acesso negado")
    ), 403


@app.errorhandler(404)
def erro_404(e):
    if request.path.startswith("/api/"):
        return jsonify({"erro": getattr(e, "description", "nao encontrado")}), 404
    return render_template(
        "erro.html", codigo=404, mensagem="Pagina nao encontrada"
    ), 404


@app.errorhandler(413)
def erro_413(e):
    if request.path.startswith("/api/"):
        return jsonify({"erro": "arquivo muito grande (limite 10 MB)"}), 413
    return render_template(
        "erro.html", codigo=413, mensagem="Arquivo muito grande (limite 10 MB)"
    ), 413


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=8000, debug=True)
