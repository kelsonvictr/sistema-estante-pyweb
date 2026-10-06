# Estante — regras do projeto

Projeto Flask de biblioteca comunitária. Iniciante aprendendo aos poucos, uma entrega por vez.

## Regras fixas

- Stack fixa: Flask + Jinja + sqlite3. Sem ORM, sem JavaScript, sem framework de CSS, sem biblioteca nova além do Flask.
- Todo SQL fica em `banco.py`, sempre usando placeholder `?` (nunca f-string/format no SQL).
- Toda tela nova usa só as classes já existentes em `static/style.css`: nada de `style=` inline nem cor fora das variáveis do `:root`.
- Uma entrega por prompt. Não refatore o que já funciona sem pedido explícito.
- Depois da fundação, não execute scripts que alterem `estante.db` (nem `criar_banco.py` de novo, nem comandos manuais de escrita no banco). Os testes no navegador são do usuário.
- Ao terminar cada entrega: confira a sintaxe, explique o diff por arquivo, e pare — não avance para a próxima entrega sem aprovação.
