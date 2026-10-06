# 📚 Estante — biblioteca comunitária em Flask

Projeto final do curso **Sistemas Web com Python** (programa AI · prof. Kelson Almeida).
Um sistema web completo, construído com Flask + Jinja + SQLite, que controla o acervo de
uma biblioteca comunitária: livros, leitores, empréstimos, devoluções, atrasos, painel e login.

Este repositório é a **versão de referência** da Estante: o resultado dos 12 prompts do Dia 7
mais os 3 prompts de deploy do Dia 8. Use-o para comparar com a sua, tirar dúvida de um
padrão ou, se a sua travou, publicar a partir dele.

> 🌍 No ar: `https://estante-SEUNOME.onrender.com` (troque pelo endereço do seu serviço)
> 🔑 Usuário `admin` · senha: a que você cadastrou em `ADMIN_SENHA` (em casa, `trocar123`)

---

## 1. O que a Estante faz

| Área | O que tem | Regras protegidas no servidor |
|---|---|---|
| **Acervo** | listar, buscar por título/autor, cadastrar, editar, excluir | título e autor obrigatórios · pelo menos 1 exemplar · exemplares nunca abaixo dos emprestados · livro com histórico não se exclui |
| **Leitores** | listar, buscar por nome, cadastrar, editar, excluir | e-mail único (repetido volta ao formulário, sem tela de erro) · leitor com histórico não se exclui |
| **Empréstimos** | lista com status e filtros, emprestar, devolver | prazo de 14 dias · só livro com exemplar disponível · máximo 3 ativos por leitor · devolver devolve o exemplar · devolução repetida é recusada |
| **Painel** | 4 cards de número, atrasados com dias de atraso, 5 mais recentes | números vêm de `COUNT`/`SUM` no banco |
| **Login** | `/login`, `/logout`, `login_required` em todas as telas | senha com hash (`werkzeug.security`) · mesma mensagem para usuário ou senha errados |

**Status de um empréstimo** (calculado no SQL, com a data de hoje vinda do Python):

- 🟦 **No prazo** — sem devolução e data prevista hoje ou no futuro
- 🟥 **Atrasado** — sem devolução e data prevista anterior a hoje
- ⬜ **Devolvido** — tem data de devolução

---

## 2. Arquitetura geral

A Estante é um **monólito server-rendered**: um único programa Flask que faz tudo, das telas
aos dados. Não existe JavaScript, API separada nem ORM. Cada clique segue o mesmo ciclo que
você aprendeu no Dia 1:

```
navegador ──request──▶ app.py (rota) ──▶ banco.py (SQL) ──▶ estante.db (SQLite)
   ▲                        │
   └────────response────────┘  ← templates/*.html renderizados pelo Jinja
```

### Os arquivos e a responsabilidade de cada um

```
estante/
├── app.py              ← rotas, validações e regras de negócio (o "cérebro")
├── banco.py            ← TODO o SQL do sistema, sempre com placeholder ?
├── criar_banco.py      ← cria as 4 tabelas e a semente; pode rodar quantas vezes quiser
├── templates/          ← as telas (Jinja)
│   ├── base.html       ← layout: menu lateral, "Olá, admin", bloco de flash
│   ├── login.html      ← a porta (não herda o base.html: não tem menu)
│   ├── painel.html     ← /
│   ├── livros.html · livro_form.html · livro_excluir.html
│   ├── leitores.html · leitor_form.html · leitor_excluir.html
│   ├── emprestimos.html · emprestimo_form.html
│   └── _status.html    ← o badge de status, usado pela lista e pelo painel
├── static/
│   └── style.css       ← design system: variáveis no :root, modo escuro automático
├── requirements.txt    ← Flask e gunicorn
├── Dockerfile          ← a receita da caixa (Dia 8)
├── .dockerignore       ← o que fica de fora da caixa
├── .gitignore          ← o que fica de fora do GitHub
├── AGENTS.md           ← as regras que o agente de IA segue neste projeto
└── estante.db          ← o banco (gerado; NÃO vai para o Git)
```

### As três camadas, e o que nunca cruza a fronteira

| Camada | Arquivo | Pode | Não pode |
|---|---|---|---|
| **Telas** | `templates/` | mostrar dados, esconder um botão por educação | decidir uma regra de negócio (esconder o botão Excluir não é segurança) |
| **Rotas e regras** | `app.py` | validar o formulário, aplicar as regras, escolher o template, dar `flash` e `redirect` | escrever SQL |
| **Dados** | `banco.py` | todo `SELECT`/`INSERT`/`UPDATE`/`DELETE`, transações | conhecer `request`, `session` ou HTML |

### O banco: 4 tabelas

```
livros                  leitores               emprestimos                 usuarios
──────                  ────────               ───────────                 ────────
id                      id                     id                          id
titulo                  nome                   livro_id  ──▶ livros.id     nome (único)
autor                   email (único)          leitor_id ──▶ leitores.id   senha_hash
ano                     telefone               data_emprestimo  AAAA-MM-DD
exemplares                                     data_prevista    AAAA-MM-DD
disponiveis                                    data_devolucao   AAAA-MM-DD ou NULL
```

Invariante que o sistema mantém: `0 <= disponiveis <= exemplares`, e
`exemplares - disponiveis` é sempre o número de empréstimos ativos daquele livro.

### Onde mora cada regra de negócio

| Regra | Onde | Como |
|---|---|---|
| Prazo de 14 dias | `app.py` → `novo_emprestimo` | `date.today() + timedelta(days=14)`, calculado no servidor; o formulário não manda data |
| Só empresta com exemplar | `app.py` → `novo_emprestimo` **e** `banco.registrar_emprestimo` | a rota checa `disponiveis < 1`; o `UPDATE ... WHERE disponiveis > 0` garante mesmo com dois cliques simultâneos |
| Máximo 3 ativos por leitor | `app.py` → `novo_emprestimo` | `banco.contar_emprestimos_ativos_do_leitor(id) >= 3` → flash de erro, nada muda no banco |
| Emprestar = 1 transação | `banco.registrar_emprestimo` | `UPDATE livros` + `INSERT emprestimos` na mesma conexão, **um** `commit()` |
| Devolver = 1 transação | `banco.registrar_devolucao` | `UPDATE emprestimos ... WHERE data_devolucao IS NULL` + `UPDATE livros +1`, **um** `commit()` |
| Devolução repetida recusada | `banco.registrar_devolucao` | se o `UPDATE` não encontrou linha (`rowcount == 0`), devolve `False` e a rota avisa — por isso Voltar + Devolver de novo não soma exemplar |
| Exemplares ≥ emprestados | `app.py` → `editar_livro` | compara com `banco.contar_emprestimos_ativos_do_livro` antes de salvar |
| Editar exemplares ajusta disponíveis | `banco.atualizar_livro` | `disponiveis = disponiveis + (novo - antigo)`: "2 de 3" vira "3 de 4", nunca "4 de 4" |
| Livro/leitor com histórico não se exclui | `app.py` → `excluir_livro` / `excluir_leitor` | a trava está **dentro do POST**, não só no template |
| E-mail único | tabela (`UNIQUE`) + `app.py` | o `sqlite3.IntegrityError` vira flash amigável |
| Datas | banco em `AAAA-MM-DD`; tela em `dd/mm/aaaa` | um único filtro Jinja, `data_br`, em `app.py` |
| Porta | `app.py` → `login_required` | decorator aplicado em toda rota (sempre **abaixo** de `@app.route`) |

### Mapa de rotas

| Método | Rota | Função | Tela |
|---|---|---|---|
| GET/POST | `/login` | `login` | `login.html` |
| GET | `/logout` | `logout` | → `/login` |
| GET | `/` | `painel` | `painel.html` |
| GET | `/livros?q=` | `livros` | `livros.html` |
| GET/POST | `/livros/novo` | `novo_livro` | `livro_form.html` |
| GET/POST | `/livros/<id>/editar` | `editar_livro` | `livro_form.html` |
| GET/POST | `/livros/<id>/excluir` | `excluir_livro` | `livro_excluir.html` |
| GET | `/leitores?q=` | `leitores` | `leitores.html` |
| GET/POST | `/leitores/novo` | `novo_leitor` | `leitor_form.html` |
| GET/POST | `/leitores/<id>/editar` | `editar_leitor` | `leitor_form.html` |
| GET/POST | `/leitores/<id>/excluir` | `excluir_leitor` | `leitor_excluir.html` |
| GET | `/emprestimos?status=ativos\|atrasados\|devolvidos` | `emprestimos` | `emprestimos.html` |
| GET/POST | `/emprestimos/novo` | `novo_emprestimo` | `emprestimo_form.html` |
| POST | `/emprestimos/<id>/devolver` | `devolver_emprestimo` | → `/emprestimos` |

Padrão de todo formulário: **PRG** (Post → Redirect → Get). Sucesso dá `redirect` com `flash`;
erro renderiza o mesmo template com o que foi digitado. Nenhuma escrita acontece por link GET.

### O design system (`static/style.css`)

Todas as cores vivem em variáveis no `:root` e trocam sozinhas no modo escuro
(`prefers-color-scheme: dark`). Paleta do Python: azul `#3776AB` (ação), amarelo `#FFD43B`
(destaque). Componentes prontos: `.card`, `.card-numero`, `.tabela`, `.formulario` / `.campo`,
`.botao--principal|secundario|perigo`, `.badge--verde|azul|vermelho|cinza`, `.busca`,
`.estado-vazio`, `.flash--sucesso|erro`, `.filtros`, `.acoes`, `.login`.
Regra do projeto: tela nova usa só essas classes — nada de `style=` inline.

---

## 3. Rodar em casa

Pré-requisito: Python 3.12 ou mais novo.

```bash
# 1. dependências (dentro do venv do PyCharm)
pip install -r requirements.txt

# 2. criar o banco com a semente (8 livros, 3 leitores, 3 empréstimos, admin)
python criar_banco.py

# 3. ligar
python app.py          # ou ▶ no PyCharm
```

Abra `http://localhost:5000` e entre com `admin` / `trocar123`.

Rodar `criar_banco.py` de novo **não duplica nada**: se as tabelas já têm dados, ele avisa e
não insere a semente. Para recomeçar do zero, apague o `estante.db` e rode de novo.

A semente vem com um empréstimo **atrasado** (prazo vencido há 5 dias) de propósito: é a prova
de que a regra de data funciona antes de você depender dela.

---

## 4. Docker: a caixa

### Por que existe

Para rodar, a Estante precisa de quatro coisas: o Python na versão certa, o Flask e o gunicorn,
os arquivos do projeto e o comando de ligar. No seu notebook está tudo lá. Num servidor novo,
não tem nada — e instalar na mão "igual ao seu computador" nunca fica igual
("na minha máquina funciona"). O **Docker** empacota tudo isso num pacote padronizado que roda
igualzinho em qualquer lugar: seu notebook, o Render, um servidor de empresa.

Três palavras:

| Palavra | O que é | Analogia |
|---|---|---|
| **Dockerfile** | arquivo de texto com a receita, linha por linha | a receita da marmita |
| **imagem** | o resultado do `build`: o pacote pronto e fechado (não se edita) | a marmita montada e congelada |
| **container** | a imagem ligada, rodando de verdade | a marmita no micro-ondas |

### O Dockerfile deste projeto, linha a linha

```dockerfile
FROM python:3.12-slim
# Começa de uma imagem oficial: um Linux enxuto com Python 3.12 já instalado.

WORKDIR /app
# Toda linha daqui pra frente acontece dentro da pasta /app da caixa.

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
# Copia só a lista de dependências e instala. Vem antes do resto de propósito:
# se você mudar um template, o Docker reaproveita esta camada e não reinstala nada.

COPY . .
# Copia o projeto inteiro — menos o que está no .dockerignore (venv, estante.db…).

CMD python criar_banco.py && gunicorn --bind 0.0.0.0:$PORT app:app
# NÃO roda no build: fica gravado na tampa e executa quando o container LIGA.
# 1) cria o banco e a semente (se já existir, não duplica);
# 2) sobe o gunicorn, o servidor de produção, escutando em TODAS as entradas
#    (0.0.0.0) na porta que o Render informa pela variável PORT.
```

Por que `gunicorn` e não `app.run()`: o `app.run()` é o servidor de desenvolvimento do Flask,
feito para uma pessoa só, e com `debug=True` mostra pedaços do seu código na tela quando dá
erro. O gunicorn atende várias pessoas ao mesmo tempo e não expõe nada. `app:app` se lê:
"no arquivo `app.py`, sirva o objeto `app`".

Por que `0.0.0.0` e não `127.0.0.1`: dentro da caixa, `127.0.0.1` quer dizer "só eu mesmo".
Quem escuta nele não é alcançado por ninguém de fora — nem pelo Render. É o **Bug 1** do
deploy ("No open ports detected").

### A regra do dia

> **A caixa é igual em todo lugar. O que muda de lugar pra lugar — porta, segredos, dados —
> não mora dentro dela.**

| Peça | Destino | Onde |
|---|---|---|
| Python, Flask, gunicorn, `app.py`, `banco.py`, `templates/`, `static/` | 📦 na caixa | `Dockerfile` |
| `PORT`, `SECRET_KEY`, `ADMIN_SENHA` | 🌍 vem de fora | variáveis de ambiente (painel do Render) |
| `.venv/`, `__pycache__/`, `.env`, `estante.db`, `.idea/` | 🏠 fica em casa | `.gitignore` e `.dockerignore` |

No código, isso aparece em duas linhas:

```python
# app.py
app.secret_key = os.environ.get("SECRET_KEY", "so-pra-rodar-em-casa")

# criar_banco.py
generate_password_hash(os.environ.get("ADMIN_SENHA", "trocar123"))
```

`os.environ.get("SECRET_KEY", "...")` quer dizer: "me dá a `SECRET_KEY` deste lugar; se não
existir, use este padrão". Em casa ninguém cadastrou nada, então vale o padrão. No Render,
vale o que está no painel — e o `trocar123` publicado no material **não entra**.

### Testar a caixa no seu computador (opcional)

Precisa do Docker Desktop instalado. Não é necessário para o deploy: quem faz o build é o
Render.

```bash
docker build -t estante .
docker run --rm -p 10000:10000 -e PORT=10000 -e SECRET_KEY=teste -e ADMIN_SENHA=minha-senha estante
```

Abra `http://localhost:10000`. Repare no log: a mensagem do `criar_banco.py` e depois
`Listening at: http://0.0.0.0:10000`.

---

## 5. Deploy no Render

### Antes

- Conta no [GitHub](https://github.com) com e-mail confirmado.
- Conta no [Render](https://render.com), criada com o botão **GitHub**.
- Docker Desktop: **não precisa**.

### Passo a passo

1. **Publicar no GitHub (pelo PyCharm)** — `Git → GitHub → Share Project on GitHub`.
   Nome do repositório: `estante`. Confira no site: tem `Dockerfile`, `app.py`, `templates/`;
   **não** tem `.venv` nem `estante.db`.

2. **Criar o Web Service** — no Render: `New → Web Service → estante`.

   | Campo | Valor |
   |---|---|
   | Name | `estante-seunome` (vira parte da URL) |
   | Language | **Docker** |
   | Branch | `main` |
   | Instance Type | **Free** |

   Com Docker escolhido, os campos de build/start command não importam: quem manda é o
   Dockerfile.

3. **Variáveis de ambiente** — em *Environment Variables*:

   | Nome | Valor |
   |---|---|
   | `SECRET_KEY` | uma frase longa e aleatória (peça ao agente: "gere uma chave aleatória longa e só me mostre") |
   | `ADMIN_SENHA` | a senha do seu admin — **não** use `trocar123` |

   `PORT` você não cria: o Render entrega sozinho (vale 10000).

4. **Create Web Service** e ler os logs, nesta ordem:

   ```
   ==> Building…                                  ← montando a imagem (pip install)
   Banco criado e semeado com sucesso.            ← o criar_banco.py rodou dentro da caixa
   [INFO] Listening at: http://0.0.0.0:10000      ← o gunicorn atendendo
   ==> Your service is live 🎉
   ```

5. **Homologar na URL pública** — entre como `admin` com a senha do passo 3. Busque um livro,
   cadastre outro, faça um empréstimo, devolva. Teste de segurança: `trocar123` tem que ser
   recusada.

Mudou o código depois? `commit + push` pelo PyCharm e o Render faz o deploy sozinho.

### O preço do grátis (e o disco que esquece)

No plano Free do Render:

- o serviço **dorme após 15 minutos** sem visita e leva cerca de 1 minuto para acordar
  (no Demo Day, abra a sua URL uns 2 minutos antes da sua vez);
- o **disco é descartável**: a cada reinício ou deploy novo ele volta vazio, e o `estante.db`
  vai junto. A Estante não quebra porque o `criar_banco.py` roda em todo boot e recria a
  semente. Ótimo para vitrine; péssimo para uma biblioteca de verdade;
- 512 MB de memória e 750 horas por mês.

Pela regra do dia, os **dados** também deveriam morar fora da caixa — num banco próprio, como
o mercado faz. É exatamente o limite que abre a conversa do curso Fullstack.

### BugZilla do deploy 🐛

| Sintoma | Causa | Remédio |
|---|---|---|
| `No open ports detected` | gunicorn escutando em `127.0.0.1` ou numa porta fixa | a última linha do Dockerfile precisa ter `--bind 0.0.0.0:$PORT` |
| "o livro que eu cadastrei sumiu" | o serviço dormiu, acordou com disco vazio e a semente voltou | nenhum no plano grátis — é o limite da vitrine |
| `Build failed` | o `.venv` foi para o GitHub, ou falta dependência no `requirements.txt` (`ModuleNotFoundError`) | conferir o repositório e o `requirements.txt`; commit + push |
| `no such table: livros` | o `criar_banco.py` não rodou antes do gunicorn | conferir o `CMD` do Dockerfile (`python criar_banco.py && gunicorn …`) |

Falhou e não é nenhum desses? Cole o final do log do Render no agente e peça diagnóstico
**sem edição** (Prompt 15 do material).

---

## 6. A trilha de prompts que construiu este projeto

A Estante foi construída inteira por um agente de codificação (Claude Code, Codex ou
Antigravity), um prompt por entrega, com o aluno lendo o diff e homologando cada passo.
As regras que o agente seguiu estão em [`AGENTS.md`](AGENTS.md).

| # | Entrega | Arquivos |
|---|---|---|
| 0 | plano, sem editar | — |
| 1 | fundação + design system + semente | `requirements.txt`, `criar_banco.py`, `banco.py`, `app.py`, `base.html`, `style.css`, `AGENTS.md` |
| 2 | listar e buscar livros | `livros.html`, `banco.listar_livros` |
| 3 | cadastrar e editar livro | `livro_form.html`, `novo_livro`, `editar_livro` |
| 4 | excluir livro com trava do histórico | `livro_excluir.html`, `excluir_livro` |
| 5 | CRUD de leitores (espelho do acervo) | `leitores.html`, `leitor_form.html`, `leitor_excluir.html` |
| 6 | lista de empréstimos com status e filtros | `emprestimos.html`, `_status.html`, `banco.listar_emprestimos` |
| 7 | emprestar (1 transação) | `emprestimo_form.html`, `banco.registrar_emprestimo` |
| 8 | devolver (1 transação, repetição recusada) | `banco.registrar_devolucao`, `devolver_emprestimo` |
| 9 | painel com COUNT/SUM | `painel.html`, `banco.resumo_painel` |
| 10 | login + `login_required` | `login.html`, `login`, `logout` |
| 11 | auditoria, sem editar | — |
| 12 | auditoria de deploy, sem editar | — |
| 13 | empacotar: segredos de fora, Dockerfile, ignores | `Dockerfile`, `.dockerignore`, `.gitignore`, `requirements.txt`, `app.py`, `criar_banco.py` |
| 14 | `git init` + primeiro commit | — |
| 15 | diagnóstico pelo log (só se o deploy falhar) | — |

### Roteiro de teste de 10 minutos

1. Deslogado, digite `/emprestimos/novo` na barra: tem que ir para `/login`.
2. Entre. Busque `machado` no acervo: só 2 livros. Busque `' OR 1=1 --`: nenhum.
3. Cadastre um livro com título vazio: erro, e o resto continua preenchido.
4. Edite um livro emprestado e aumente 1 exemplar: "2 de 3" vira "3 de 4".
5. Tente excluir um livro da semente: trava. Exclua o que você cadastrou: some.
6. Cadastre um leitor com o e-mail da Ana: mensagem amigável, sem tela de erro.
7. Empreste 3 livros para o mesmo leitor; o quarto é barrado e o acervo não muda.
8. Devolva o atrasado; ele some do filtro *Atrasados* e o livro recupera o exemplar.
9. Aperte Voltar no navegador e clique *Devolver* de novo: recusado, exemplar não soma.
10. Volte ao painel: os números batem com as telas de acervo e empréstimos.

---

## 7. Extras (versão 2)

Ideias para continuar, um prompt por vez: renovar empréstimo (+7 dias, uma vez, só se não
estiver atrasado) · ranking "mais emprestados" com `GROUP BY` · capa do livro por URL de
imagem · levar a Estante para o seu tema (barbearia = serviços + clientes + agendamentos;
petshop…) · banco fora da caixa (o próximo degrau).

---

Feito com 🌶️ no curso **Sistemas Web com Python** — programa AI.
