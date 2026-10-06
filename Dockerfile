# A receita da caixa. O Render segue estas linhas para montar a imagem.
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Ao ligar: cria o banco (se não existir) e sobe o servidor de produção
# escutando em todas as entradas (0.0.0.0), na porta que o Render informa ($PORT).
CMD python criar_banco.py && gunicorn --bind 0.0.0.0:$PORT app:app
