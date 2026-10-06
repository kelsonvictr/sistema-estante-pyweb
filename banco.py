"""Todo o SQL da Estante mora aqui.

Regra do projeto: nenhuma outra parte do sistema escreve SQL.
Sempre placeholder ? — nunca f-string nem format dentro de um comando SQL.
"""

import os
import sqlite3

# O banco fica sempre ao lado deste arquivo, não importa de onde o programa foi chamado
# (▶ no PyCharm, terminal, gunicorn dentro do container).
CAMINHO_BANCO = os.path.join(os.path.dirname(os.path.abspath(__file__)), "estante.db")

PRAZO_DIAS = 14
MAXIMO_EMPRESTIMOS_POR_LEITOR = 3


def conectar():
    """A única função de conexão. Todas as outras usam esta."""
    conexao = sqlite3.connect(CAMINHO_BANCO)
    conexao.row_factory = sqlite3.Row
    conexao.execute("PRAGMA foreign_keys = ON")
    return conexao


# ---------------------------------------------------------------------------
# Livros
# ---------------------------------------------------------------------------

def listar_livros(busca=""):
    conexao = conectar()
    try:
        termo = f"%{busca}%"
        return conexao.execute(
            "SELECT id, titulo, autor, ano, exemplares, disponiveis FROM livros "
            "WHERE titulo LIKE ? OR autor LIKE ? "
            "ORDER BY titulo",
            (termo, termo),
        ).fetchall()
    finally:
        conexao.close()


def buscar_livro(livro_id):
    conexao = conectar()
    try:
        return conexao.execute(
            "SELECT id, titulo, autor, ano, exemplares, disponiveis FROM livros WHERE id = ?",
            (livro_id,),
        ).fetchone()
    finally:
        conexao.close()


def inserir_livro(titulo, autor, ano, exemplares):
    """No cadastro, disponiveis nasce igual a exemplares."""
    conexao = conectar()
    try:
        conexao.execute(
            "INSERT INTO livros (titulo, autor, ano, exemplares, disponiveis) "
            "VALUES (?, ?, ?, ?, ?)",
            (titulo, autor, ano, exemplares, exemplares),
        )
        conexao.commit()
    finally:
        conexao.close()


def contar_emprestimos_ativos_do_livro(livro_id):
    conexao = conectar()
    try:
        return conexao.execute(
            "SELECT COUNT(*) FROM emprestimos WHERE livro_id = ? AND data_devolucao IS NULL",
            (livro_id,),
        ).fetchone()[0]
    finally:
        conexao.close()


def atualizar_livro(livro_id, titulo, autor, ano, exemplares):
    """Se exemplares mudar, disponiveis muda a mesma diferença.

    Ex.: "2 de 3" e o bibliotecário compra mais um → "3 de 4".
    A trava "exemplares nunca abaixo dos emprestados" fica na rota, em app.py.
    """
    conexao = conectar()
    try:
        atual = conexao.execute(
            "SELECT exemplares FROM livros WHERE id = ?", (livro_id,)
        ).fetchone()
        diferenca = exemplares - atual["exemplares"]
        conexao.execute(
            "UPDATE livros SET titulo = ?, autor = ?, ano = ?, exemplares = ?, "
            "disponiveis = disponiveis + ? WHERE id = ?",
            (titulo, autor, ano, exemplares, diferenca, livro_id),
        )
        conexao.commit()
    finally:
        conexao.close()


def livro_tem_historico(livro_id):
    """Livro que aparece em QUALQUER empréstimo (ativo ou devolvido) não pode sumir."""
    conexao = conectar()
    try:
        total = conexao.execute(
            "SELECT COUNT(*) FROM emprestimos WHERE livro_id = ?", (livro_id,)
        ).fetchone()[0]
        return total > 0
    finally:
        conexao.close()


def excluir_livro(livro_id):
    conexao = conectar()
    try:
        conexao.execute("DELETE FROM livros WHERE id = ?", (livro_id,))
        conexao.commit()
    finally:
        conexao.close()


def listar_livros_disponiveis():
    conexao = conectar()
    try:
        return conexao.execute(
            "SELECT id, titulo, autor, disponiveis FROM livros "
            "WHERE disponiveis > 0 ORDER BY titulo"
        ).fetchall()
    finally:
        conexao.close()


# ---------------------------------------------------------------------------
# Leitores — o espelho do acervo
# ---------------------------------------------------------------------------

def listar_leitores(busca=""):
    conexao = conectar()
    try:
        termo = f"%{busca}%"
        return conexao.execute(
            "SELECT id, nome, email, telefone FROM leitores "
            "WHERE nome LIKE ? ORDER BY nome",
            (termo,),
        ).fetchall()
    finally:
        conexao.close()


def buscar_leitor(leitor_id):
    conexao = conectar()
    try:
        return conexao.execute(
            "SELECT id, nome, email, telefone FROM leitores WHERE id = ?",
            (leitor_id,),
        ).fetchone()
    finally:
        conexao.close()


def inserir_leitor(nome, email, telefone):
    """E-mail repetido levanta sqlite3.IntegrityError — a rota transforma em flash."""
    conexao = conectar()
    try:
        conexao.execute(
            "INSERT INTO leitores (nome, email, telefone) VALUES (?, ?, ?)",
            (nome, email, telefone),
        )
        conexao.commit()
    finally:
        conexao.close()


def atualizar_leitor(leitor_id, nome, email, telefone):
    conexao = conectar()
    try:
        conexao.execute(
            "UPDATE leitores SET nome = ?, email = ?, telefone = ? WHERE id = ?",
            (nome, email, telefone, leitor_id),
        )
        conexao.commit()
    finally:
        conexao.close()


def leitor_tem_historico(leitor_id):
    conexao = conectar()
    try:
        total = conexao.execute(
            "SELECT COUNT(*) FROM emprestimos WHERE leitor_id = ?", (leitor_id,)
        ).fetchone()[0]
        return total > 0
    finally:
        conexao.close()


def excluir_leitor(leitor_id):
    conexao = conectar()
    try:
        conexao.execute("DELETE FROM leitores WHERE id = ?", (leitor_id,))
        conexao.commit()
    finally:
        conexao.close()


def contar_emprestimos_ativos_do_leitor(leitor_id):
    conexao = conectar()
    try:
        return conexao.execute(
            "SELECT COUNT(*) FROM emprestimos WHERE leitor_id = ? AND data_devolucao IS NULL",
            (leitor_id,),
        ).fetchone()[0]
    finally:
        conexao.close()


# ---------------------------------------------------------------------------
# Empréstimos — a ida e a volta
# ---------------------------------------------------------------------------

# O status é calculado no SQL, com a data de hoje entrando por placeholder.
_SQL_EMPRESTIMOS = """
    SELECT e.id,
           e.data_emprestimo,
           e.data_prevista,
           e.data_devolucao,
           l.titulo AS livro,
           r.nome   AS leitor,
           CASE
               WHEN e.data_devolucao IS NOT NULL THEN 'devolvido'
               WHEN e.data_prevista < ?           THEN 'atrasado'
               ELSE 'no_prazo'
           END AS status
    FROM emprestimos e
    JOIN livros   l ON l.id = e.livro_id
    JOIN leitores r ON r.id = e.leitor_id
"""

_FILTROS_STATUS = {
    "ativos": "WHERE e.data_devolucao IS NULL",
    "atrasados": "WHERE e.data_devolucao IS NULL AND e.data_prevista < ?",
    "devolvidos": "WHERE e.data_devolucao IS NOT NULL",
}


def listar_emprestimos(hoje, status=None):
    """hoje é um str AAAA-MM-DD vindo do Python (date.today().isoformat())."""
    conexao = conectar()
    try:
        sql = _SQL_EMPRESTIMOS
        parametros = [hoje]
        if status in _FILTROS_STATUS:
            sql += _FILTROS_STATUS[status]
            if status == "atrasados":
                parametros.append(hoje)
        sql += " ORDER BY e.data_emprestimo DESC, e.id DESC"
        return conexao.execute(sql, parametros).fetchall()
    finally:
        conexao.close()


def buscar_emprestimo(emprestimo_id):
    conexao = conectar()
    try:
        return conexao.execute(
            "SELECT id, livro_id, leitor_id, data_emprestimo, data_prevista, data_devolucao "
            "FROM emprestimos WHERE id = ?",
            (emprestimo_id,),
        ).fetchone()
    finally:
        conexao.close()


def registrar_emprestimo(livro_id, leitor_id, data_emprestimo, data_prevista):
    """INSERT do empréstimo + UPDATE de disponiveis, na mesma conexão, com UM commit.

    O UPDATE só baixa o exemplar se ainda houver um disponível: se duas pessoas
    emprestarem o último exemplar ao mesmo tempo, a segunda não passa.
    """
    conexao = conectar()
    try:
        cursor = conexao.execute(
            "UPDATE livros SET disponiveis = disponiveis - 1 "
            "WHERE id = ? AND disponiveis > 0",
            (livro_id,),
        )
        if cursor.rowcount == 0:
            conexao.rollback()
            return False
        conexao.execute(
            "INSERT INTO emprestimos (livro_id, leitor_id, data_emprestimo, data_prevista, data_devolucao) "
            "VALUES (?, ?, ?, ?, NULL)",
            (livro_id, leitor_id, data_emprestimo, data_prevista),
        )
        conexao.commit()
        return True
    finally:
        conexao.close()


def registrar_devolucao(emprestimo_id, data_devolucao):
    """Grava a devolução + devolve o exemplar, na mesma conexão, com UM commit.

    Devolve False se o empréstimo já estava devolvido (ou não existe): o UPDATE
    com `AND data_devolucao IS NULL` não encontra linha nenhuma — e por isso o
    botão Voltar + Devolver de novo não soma exemplar duas vezes.
    """
    conexao = conectar()
    try:
        cursor = conexao.execute(
            "UPDATE emprestimos SET data_devolucao = ? "
            "WHERE id = ? AND data_devolucao IS NULL",
            (data_devolucao, emprestimo_id),
        )
        if cursor.rowcount == 0:
            conexao.rollback()
            return False
        conexao.execute(
            "UPDATE livros SET disponiveis = disponiveis + 1 "
            "WHERE id = (SELECT livro_id FROM emprestimos WHERE id = ?)",
            (emprestimo_id,),
        )
        conexao.commit()
        return True
    finally:
        conexao.close()


# ---------------------------------------------------------------------------
# Painel — COUNT e SUM
# ---------------------------------------------------------------------------

def resumo_painel(hoje):
    conexao = conectar()
    try:
        titulos = conexao.execute("SELECT COUNT(*) FROM livros").fetchone()[0]
        disponiveis = conexao.execute(
            "SELECT COALESCE(SUM(disponiveis), 0) FROM livros"
        ).fetchone()[0]
        ativos = conexao.execute(
            "SELECT COUNT(*) FROM emprestimos WHERE data_devolucao IS NULL"
        ).fetchone()[0]
        atrasados = conexao.execute(
            "SELECT COUNT(*) FROM emprestimos "
            "WHERE data_devolucao IS NULL AND data_prevista < ?",
            (hoje,),
        ).fetchone()[0]
        return {
            "titulos": titulos,
            "disponiveis": disponiveis,
            "ativos": ativos,
            "atrasados": atrasados,
        }
    finally:
        conexao.close()


def listar_atrasados(hoje):
    """Leitor, livro e dias de atraso (calculados pelo SQLite com julianday)."""
    conexao = conectar()
    try:
        return conexao.execute(
            "SELECT e.id, r.nome AS leitor, l.titulo AS livro, e.data_prevista, "
            "       CAST(julianday(?) - julianday(e.data_prevista) AS INTEGER) AS dias_atraso "
            "FROM emprestimos e "
            "JOIN livros   l ON l.id = e.livro_id "
            "JOIN leitores r ON r.id = e.leitor_id "
            "WHERE e.data_devolucao IS NULL AND e.data_prevista < ? "
            "ORDER BY e.data_prevista",
            (hoje, hoje),
        ).fetchall()
    finally:
        conexao.close()


def listar_emprestimos_recentes(hoje, limite=5):
    conexao = conectar()
    try:
        return conexao.execute(
            _SQL_EMPRESTIMOS + " ORDER BY e.data_emprestimo DESC, e.id DESC LIMIT ?",
            (hoje, limite),
        ).fetchall()
    finally:
        conexao.close()


# ---------------------------------------------------------------------------
# Usuários — a porta
# ---------------------------------------------------------------------------

def buscar_usuario(nome):
    conexao = conectar()
    try:
        return conexao.execute(
            "SELECT id, nome, senha_hash FROM usuarios WHERE nome = ?", (nome,)
        ).fetchone()
    finally:
        conexao.close()
