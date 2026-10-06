"""A Estante — sistema de uma biblioteca comunitária.

Rotas, validações e regras de negócio moram aqui.
Todo SQL mora em banco.py. As telas moram em templates/.
"""

import os
import sqlite3
from datetime import date, datetime, timedelta
from functools import wraps

from flask import (
    Flask,
    abort,
    flash,
    redirect,
    render_template,
    request,
    session,
    url_for,
)
from werkzeug.security import check_password_hash

import banco

app = Flask(__name__)

# O segredo vem de fora (variável de ambiente). O valor padrão serve só para rodar em casa.
app.secret_key = os.environ.get("SECRET_KEY", "so-pra-rodar-em-casa")


# ---------------------------------------------------------------------------
# Datas: AAAA-MM-DD no banco, dd/mm/aaaa na tela — formatadas num único lugar
# ---------------------------------------------------------------------------

def hoje_iso():
    return date.today().isoformat()


@app.template_filter("data_br")
def data_br(valor):
    if not valor:
        return "—"
    return datetime.strptime(valor, "%Y-%m-%d").strftime("%d/%m/%Y")


# ---------------------------------------------------------------------------
# A porta: login_required
# ---------------------------------------------------------------------------

def login_required(funcao):
    @wraps(funcao)
    def protegida(*args, **kwargs):
        if "usuario" not in session:
            return redirect(url_for("login"))
        return funcao(*args, **kwargs)

    return protegida


@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        nome = request.form.get("usuario", "").strip()
        senha = request.form.get("senha", "")
        usuario = banco.buscar_usuario(nome)
        # Mesma mensagem para usuário e senha errados: não entregamos qual dos dois falhou.
        if usuario and check_password_hash(usuario["senha_hash"], senha):
            session["usuario"] = usuario["nome"]
            return redirect(url_for("painel"))
        flash("Usuário ou senha inválidos.", "erro")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.pop("usuario", None)
    flash("Você saiu da Estante.", "sucesso")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Painel
# ---------------------------------------------------------------------------

@app.route("/")
@login_required
def painel():
    hoje = hoje_iso()
    return render_template(
        "painel.html",
        resumo=banco.resumo_painel(hoje),
        atrasados=banco.listar_atrasados(hoje),
        recentes=banco.listar_emprestimos_recentes(hoje),
    )


# ---------------------------------------------------------------------------
# Acervo (livros)
# ---------------------------------------------------------------------------

@app.route("/livros")
@login_required
def livros():
    busca = request.args.get("q", "")
    return render_template("livros.html", livros=banco.listar_livros(busca), busca=busca)


def ler_formulario_livro():
    """Lê e valida o formulário de livro. Devolve (dados, erros)."""
    dados = {
        "titulo": request.form.get("titulo", "").strip(),
        "autor": request.form.get("autor", "").strip(),
        "ano": request.form.get("ano", "").strip(),
        "exemplares": request.form.get("exemplares", "").strip(),
    }
    erros = []
    if not dados["titulo"]:
        erros.append("O título é obrigatório.")
    if not dados["autor"]:
        erros.append("O autor é obrigatório.")
    if dados["ano"] and not dados["ano"].isdigit():
        erros.append("O ano precisa ser um número.")
    if not dados["exemplares"].isdigit() or int(dados["exemplares"]) < 1:
        erros.append("Informe pelo menos 1 exemplar.")
    return dados, erros


@app.route("/livros/novo", methods=["GET", "POST"])
@login_required
def novo_livro():
    if request.method == "POST":
        dados, erros = ler_formulario_livro()
        if erros:
            for erro in erros:
                flash(erro, "erro")
            return render_template("livro_form.html", livro=dados, modo="novo")
        banco.inserir_livro(
            dados["titulo"],
            dados["autor"],
            int(dados["ano"]) if dados["ano"] else None,
            int(dados["exemplares"]),
        )
        flash(f'Livro "{dados["titulo"]}" cadastrado.', "sucesso")
        return redirect(url_for("livros"))
    return render_template("livro_form.html", livro={}, modo="novo")


@app.route("/livros/<int:livro_id>/editar", methods=["GET", "POST"])
@login_required
def editar_livro(livro_id):
    livro = banco.buscar_livro(livro_id)
    if livro is None:
        abort(404)
    if request.method == "POST":
        dados, erros = ler_formulario_livro()
        emprestados = banco.contar_emprestimos_ativos_do_livro(livro_id)
        # Regra: exemplares nunca fica abaixo da quantidade emprestada agora.
        if not erros and int(dados["exemplares"]) < emprestados:
            erros.append(
                f"Este livro tem {emprestados} exemplar(es) emprestado(s) agora: "
                f"não dá para ficar com menos que isso."
            )
        if erros:
            for erro in erros:
                flash(erro, "erro")
            dados["id"] = livro_id
            return render_template("livro_form.html", livro=dados, modo="editar")
        banco.atualizar_livro(
            livro_id,
            dados["titulo"],
            dados["autor"],
            int(dados["ano"]) if dados["ano"] else None,
            int(dados["exemplares"]),
        )
        flash(f'Livro "{dados["titulo"]}" atualizado.', "sucesso")
        return redirect(url_for("livros"))
    return render_template("livro_form.html", livro=livro, modo="editar")


@app.route("/livros/<int:livro_id>/excluir", methods=["GET", "POST"])
@login_required
def excluir_livro(livro_id):
    livro = banco.buscar_livro(livro_id)
    if livro is None:
        abort(404)
    tem_historico = banco.livro_tem_historico(livro_id)
    if request.method == "POST":
        # A trava existe no servidor, não só no template: esconder o botão é educação,
        # recusar aqui é segurança.
        if tem_historico:
            flash("Este livro tem histórico de empréstimos e não pode ser excluído.", "erro")
            return redirect(url_for("livros"))
        banco.excluir_livro(livro_id)
        flash(f'Livro "{livro["titulo"]}" excluído.', "erro")
        return redirect(url_for("livros"))
    return render_template("livro_excluir.html", livro=livro, tem_historico=tem_historico)


# ---------------------------------------------------------------------------
# Leitores — o espelho do acervo
# ---------------------------------------------------------------------------

@app.route("/leitores")
@login_required
def leitores():
    busca = request.args.get("q", "")
    return render_template("leitores.html", leitores=banco.listar_leitores(busca), busca=busca)


def ler_formulario_leitor():
    dados = {
        "nome": request.form.get("nome", "").strip(),
        "email": request.form.get("email", "").strip().lower(),
        "telefone": request.form.get("telefone", "").strip(),
    }
    erros = []
    if not dados["nome"]:
        erros.append("O nome é obrigatório.")
    if not dados["email"] or "@" not in dados["email"]:
        erros.append("Informe um e-mail válido.")
    return dados, erros


@app.route("/leitores/novo", methods=["GET", "POST"])
@login_required
def novo_leitor():
    if request.method == "POST":
        dados, erros = ler_formulario_leitor()
        if not erros:
            try:
                banco.inserir_leitor(dados["nome"], dados["email"], dados["telefone"])
                flash(f'Leitor(a) "{dados["nome"]}" cadastrado(a).', "sucesso")
                return redirect(url_for("leitores"))
            except sqlite3.IntegrityError:
                erros.append("Já existe um leitor com este e-mail.")
        for erro in erros:
            flash(erro, "erro")
        return render_template("leitor_form.html", leitor=dados, modo="novo")
    return render_template("leitor_form.html", leitor={}, modo="novo")


@app.route("/leitores/<int:leitor_id>/editar", methods=["GET", "POST"])
@login_required
def editar_leitor(leitor_id):
    leitor = banco.buscar_leitor(leitor_id)
    if leitor is None:
        abort(404)
    if request.method == "POST":
        dados, erros = ler_formulario_leitor()
        if not erros:
            try:
                banco.atualizar_leitor(leitor_id, dados["nome"], dados["email"], dados["telefone"])
                flash(f'Leitor(a) "{dados["nome"]}" atualizado(a).', "sucesso")
                return redirect(url_for("leitores"))
            except sqlite3.IntegrityError:
                erros.append("Já existe um leitor com este e-mail.")
        for erro in erros:
            flash(erro, "erro")
        dados["id"] = leitor_id
        return render_template("leitor_form.html", leitor=dados, modo="editar")
    return render_template("leitor_form.html", leitor=leitor, modo="editar")


@app.route("/leitores/<int:leitor_id>/excluir", methods=["GET", "POST"])
@login_required
def excluir_leitor(leitor_id):
    leitor = banco.buscar_leitor(leitor_id)
    if leitor is None:
        abort(404)
    tem_historico = banco.leitor_tem_historico(leitor_id)
    if request.method == "POST":
        if tem_historico:
            flash("Este leitor tem histórico de empréstimos e não pode ser excluído.", "erro")
            return redirect(url_for("leitores"))
        banco.excluir_leitor(leitor_id)
        flash(f'Leitor(a) "{leitor["nome"]}" excluído(a).', "erro")
        return redirect(url_for("leitores"))
    return render_template("leitor_excluir.html", leitor=leitor, tem_historico=tem_historico)


# ---------------------------------------------------------------------------
# Empréstimos — a ida e a volta
# ---------------------------------------------------------------------------

@app.route("/emprestimos")
@login_required
def emprestimos():
    status = request.args.get("status")
    if status not in ("ativos", "atrasados", "devolvidos"):
        status = None
    return render_template(
        "emprestimos.html",
        emprestimos=banco.listar_emprestimos(hoje_iso(), status),
        status=status,
    )


@app.route("/emprestimos/novo", methods=["GET", "POST"])
@login_required
def novo_emprestimo():
    hoje = date.today()
    data_prevista = hoje + timedelta(days=banco.PRAZO_DIAS)

    if request.method == "POST":
        livro_id = request.form.get("livro_id", "")
        leitor_id = request.form.get("leitor_id", "")
        livro = banco.buscar_livro(int(livro_id)) if livro_id.isdigit() else None
        leitor = banco.buscar_leitor(int(leitor_id)) if leitor_id.isdigit() else None

        # As regras ficam aqui, no servidor — nunca confiamos no formulário.
        if livro is None or leitor is None:
            flash("Escolha um livro e um leitor.", "erro")
        elif livro["disponiveis"] < 1:
            flash(f'"{livro["titulo"]}" está sem exemplar disponível.', "erro")
        elif banco.contar_emprestimos_ativos_do_leitor(leitor["id"]) >= banco.MAXIMO_EMPRESTIMOS_POR_LEITOR:
            flash(
                f'{leitor["nome"]} já tem {banco.MAXIMO_EMPRESTIMOS_POR_LEITOR} empréstimos ativos. '
                f"Devolva um antes de emprestar outro.",
                "erro",
            )
        elif not banco.registrar_emprestimo(
            livro["id"], leitor["id"], hoje.isoformat(), data_prevista.isoformat()
        ):
            flash(f'"{livro["titulo"]}" acabou de ficar sem exemplar.', "erro")
        else:
            flash(
                f'"{livro["titulo"]}" emprestado para {leitor["nome"]}. '
                f"Devolução até {data_prevista.strftime('%d/%m/%Y')}.",
                "sucesso",
            )
            return redirect(url_for("emprestimos"))

    return render_template(
        "emprestimo_form.html",
        livros=banco.listar_livros_disponiveis(),
        leitores=banco.listar_leitores(),
        data_prevista=data_prevista.isoformat(),
    )


@app.route("/emprestimos/<int:emprestimo_id>/devolver", methods=["POST"])
@login_required
def devolver_emprestimo(emprestimo_id):
    if banco.buscar_emprestimo(emprestimo_id) is None:
        abort(404)
    if banco.registrar_devolucao(emprestimo_id, hoje_iso()):
        flash("Devolução registrada. O exemplar voltou para a estante.", "sucesso")
    else:
        flash("Este empréstimo já tinha sido devolvido.", "erro")
    return redirect(url_for("emprestimos"))


if __name__ == "__main__":
    app.run(debug=True)
