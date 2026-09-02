# Caixa de ferramentas da Liga Sudoers.
# Um unico container com os drivers dos 5 paradigmas + dataviz.
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# cqlsh/redis-cli/mongosh nao vem aqui de proposito: para falar com cada banco
# voce usa `docker exec` no container DELE. Aqui ficam so os drivers Python.
RUN apt-get update \
 && apt-get install -y --no-install-recommends curl ca-certificates \
 && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

WORKDIR /app
CMD ["python", "-c", "print('Caixa de ferramentas pronta. Use: docker compose run --rm seeder python seeds/....py')"]
