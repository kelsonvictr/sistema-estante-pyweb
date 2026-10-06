import os
from datetime import date, timedelta

from werkzeug.security import generate_password_hash

from banco import conectar

SQL_CRIAR_TABELAS = """
CREATE TABLE IF NOT EXISTS livros (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    titulo TEXT NOT NULL,
    autor TEXT NOT NULL,
    ano INTEGER,
    exemplares INTEGER NOT NULL,
    disponiveis INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS leitores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL,
    email TEXT NOT NULL UNIQUE,
    telefone TEXT
);

CREATE TABLE IF NOT EXISTS emprestimos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    livro_id INTEGER NOT NULL REFERENCES livros(id),
    leitor_id INTEGER NOT NULL REFERENCES leitores(id),
    data_emprestimo TEXT NOT NULL,
    data_prevista TEXT NOT NULL,
    data_devolucao TEXT
);

CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    nome TEXT NOT NULL UNIQUE,
    senha_hash TEXT NOT NULL
);
"""

LIVROS_SEMENTE = [
    ("Dom Casmurro", "Machado de Assis", 1899, 3),
    ("Memórias Póstumas de Brás Cubas", "Machado de Assis", 1881, 3),
    ("Grande Sertão: Veredas", "Guimarães Rosa", 1956, 2),
    ("Capitães da Areia", "Jorge Amado", 1937, 3),
    ("O Cortiço", "Aluísio Azevedo", 1890, 2),
    ("Iracema", "José de Alencar", 1865, 1),
    ("Vidas Secas", "Graciliano Ramos", 1938, 2),
    ("Torto Arado", "Itamar Vieira Junior", 2019, 2),
]

LEITORES_SEMENTE = [
    ("Ana Ribeiro", "ana.ribeiro@email.com", "11 91234-5678"),
    ("Bruno Souza", "bruno.souza@email.com", "21 98765-4321"),
    ("Carla Nunes", "carla.nunes@email.com", "31 99876-1234"),
]


def tabelas_vazias(conexao):
    total = conexao.execute("SELECT COUNT(*) FROM livros").fetchone()[0]
    return total == 0


def semear_livros(conexao):
    conexao.executemany(
        "INSERT INTO livros (titulo, autor, ano, exemplares, disponiveis) "
        "VALUES (?, ?, ?, ?, ?)",
        [(titulo, autor, ano, exemplares, exemplares) for titulo, autor, ano, exemplares in LIVROS_SEMENTE],
    )


def semear_leitores(conexao):
    conexao.executemany(
        "INSERT INTO leitores (nome, email, telefone) VALUES (?, ?, ?)",
        LEITORES_SEMENTE,
    )


def semear_usuario_admin(conexao):
    conexao.execute(
        "INSERT INTO usuarios (nome, senha_hash) VALUES (?, ?)",
        # A senha vem de fora (variável de ambiente). "trocar123" serve só para rodar em casa.
        ("admin", generate_password_hash(os.environ.get("ADMIN_SENHA", "trocar123"))),
    )


def semear_emprestimos(conexao):
    hoje = date.today()

    emprestimos = [
        # (titulo_livro, indice_leitor, dias_desde_emprestimo, dias_prazo)
        ("Dom Casmurro", 0, 3, 14),
        ("Grande Sertão: Veredas", 1, 7, 14),
        ("Iracema", 2, 19, 14),  # atrasado: prazo venceu há 5 dias
    ]

    for titulo, indice_leitor, dias_desde_emprestimo, dias_prazo in emprestimos:
        livro_id = conexao.execute(
            "SELECT id FROM livros WHERE titulo = ?", (titulo,)
        ).fetchone()[0]
        leitor_id = conexao.execute(
            "SELECT id FROM leitores ORDER BY id"
        ).fetchall()[indice_leitor]["id"]

        data_emprestimo = hoje - timedelta(days=dias_desde_emprestimo)
        data_prevista = data_emprestimo + timedelta(days=dias_prazo)

        conexao.execute(
            "INSERT INTO emprestimos (livro_id, leitor_id, data_emprestimo, data_prevista, data_devolucao) "
            "VALUES (?, ?, ?, ?, NULL)",
            (livro_id, leitor_id, data_emprestimo.isoformat(), data_prevista.isoformat()),
        )
        conexao.execute(
            "UPDATE livros SET disponiveis = disponiveis - 1 WHERE id = ?",
            (livro_id,),
        )


def criar_banco():
    conexao = conectar()
    try:
        conexao.executescript(SQL_CRIAR_TABELAS)

        if tabelas_vazias(conexao):
            semear_livros(conexao)
            semear_leitores(conexao)
            semear_usuario_admin(conexao)
            semear_emprestimos(conexao)
            conexao.commit()
            print("Banco criado e semeado com sucesso.")
        else:
            print("Banco já continha dados; nenhuma semente foi inserida de novo.")
    finally:
        conexao.close()


if __name__ == "__main__":
    criar_banco()
