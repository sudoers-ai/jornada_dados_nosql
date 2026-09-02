# ==========================================================================
# Liga Sudoers NoSQL - atalhos
#
#   make ajuda      lista tudo
#   make tudo       sobe a stack inteira e popula
#
# Nada aqui e obrigatorio: todo comando `make` corresponde a um
# `docker compose` que esta escrito no README da pasta correspondente.
# O Makefile so poupa digitacao.
# ==========================================================================
.DEFAULT_GOAL := ajuda
SHELL := /bin/bash
DC    := docker compose
DCL   := docker compose -f docker-compose.yml -f docker-compose.lake.yml

# Cria o .env na primeira vez. O compose ja tem valores padrao para tudo,
# entao isto e conveniencia (para voce editar), nao obrigacao.
$(shell [ -f .env ] || cp .env.example .env 2>/dev/null)

.PHONY: ajuda tudo derruba limpar status logs ferramentas \
        documento chavevalor grafo widecolumn colunar viz bi bi-driver \
        verificar consertar diagnostico aula \
        seed-mongo seed-redis seed-neo4j seed-cassandra seed-clickhouse seed \
        q-mongo q-redis q-neo4j q-cassandra q-clickhouse \
        lake-conectar lake-desconectar lake-oltp lake-export validar

ajuda:  ## mostra esta ajuda
	@echo ""
	@echo "  Liga Sudoers - o lado NoSQL"
	@echo "  ---------------------------------------------------------------"
	@grep -E '^[a-zA-Z0-9_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
	  | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[1m%-18s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ----------------------------------------------------------- subir bancos
documento:   ## sobe o MongoDB (+ Mongo Express)
	$(DC) --profile documento up -d
chavevalor:  ## sobe o Redis
	$(DC) --profile chavevalor up -d
grafo:       ## sobe o Neo4j
	$(DC) --profile grafo up -d
widecolumn:  ## sobe o Cassandra
	$(DC) --profile widecolumn up -d
colunar:     ## sobe o ClickHouse
	$(DC) --profile colunar up -d
viz:         ## sobe o painel Streamlit (http://localhost:8501)
	$(DC) --profile viz up -d
bi: bi-driver ## sobe o Metabase (http://localhost:3010)
	$(DC) --profile bi up -d

# Versao do driver ClickHouse do Metabase. Compativel com metabase v0.50.x.
# ATENCAO: nada de comentario na MESMA linha do :=, porque o Make guarda os
# espacos antes do "#" dentro do valor e a URL sai quebrada.
DRIVER_CH := 1.50.7
bi-driver:   ## baixa o driver ClickHouse do Metabase (nao vem na imagem)
	@mkdir -p metabase/plugins
	@# O Metabase roda com outro usuario dentro do container e precisa
	@# ESCREVER no diretorio de plugins (ele extrai o jar ali). Sem esta
	@# permissao ele loga "does not have permissions to write to plugins
	@# directory", cai para /tmp e o ClickHouse simplesmente nao aparece
	@# na lista de bancos - sem erro visivel na interface.
	@chmod 777 metabase/plugins
	@if [ -f metabase/plugins/clickhouse.metabase-driver.jar ]; then \
	  echo "  driver ja existe (metabase/plugins/)"; \
	else \
	  echo "  baixando driver ClickHouse $(DRIVER_CH)..."; \
	  if curl -fsSL -o metabase/plugins/clickhouse.metabase-driver.jar \
	       "https://github.com/ClickHouse/metabase-clickhouse-driver/releases/download/$(DRIVER_CH)/clickhouse.metabase-driver.jar"; then \
	    echo "  ✅ baixado ($$(du -h metabase/plugins/clickhouse.metabase-driver.jar | cut -f1))"; \
	  else \
	    rm -f metabase/plugins/clickhouse.metabase-driver.jar; \
	    echo "  ⚠️  download falhou. O Metabase sobe mesmo assim, so sem ClickHouse."; \
	    echo "     (o MongoDB continua funcionando: o driver dele ja vem na imagem)"; \
	  fi; \
	fi

ferramentas: ## constroi a imagem com os drivers
	$(DC) build seeder

aula:        ## prepara UMA aula: sobe, popula e mostra o roteiro (make aula a=grafo)
	@bash scripts/aula.sh $(a)

verificar:   ## confere Docker, portas e recursos ANTES de subir
	@bash scripts/verificar.sh

tudo: verificar ferramentas bi-driver ## sobe TUDO e popula os 5 bancos
	$(DC) --profile tudo up -d
	@echo "aguardando os bancos ficarem saudaveis..."
	@bash scripts/esperar.sh
	@$(MAKE) --no-print-directory seed

derruba:     ## para os containers (mantem os dados)
	$(DC) --profile tudo --profile ferramentas down
limpar:      ## para e APAGA os volumes (perde tudo)
	$(DC) --profile tudo --profile ferramentas down -v
status:      ## mostra o estado dos containers
	@$(DC) --profile tudo ps --format 'table {{.Name}}\t{{.Service}}\t{{.Status}}'
logs:        ## segue os logs (make logs s=neo4j)
	$(DC) logs -f $(s)

# ------------------------------------------------------------------ seeds
seed-mongo:      ## popula o MongoDB
	$(DC) run --rm seeder python mongodb/seed_mongo.py
seed-redis:      ## popula o Redis
	$(DC) run --rm seeder python redis/seed_redis.py
seed-neo4j:      ## popula o Neo4j
	$(DC) run --rm seeder python neo4j/seed_neo4j.py
seed-cassandra:  ## popula o Cassandra
	$(DC) run --rm seeder python cassandra/seed_cassandra.py
seed-clickhouse: ## popula o ClickHouse
	$(DC) run --rm seeder python clickhouse/seed_clickhouse.py
seed: seed-mongo seed-redis seed-neo4j seed-cassandra seed-clickhouse ## popula os 5

# -------------------------------------------------------------- consultas
q-mongo:      ## roda as consultas guiadas do MongoDB
	docker exec sudoers_mongo mongosh --quiet -u sudoers -p sudoers \
	  --authenticationDatabase admin liga_sudoers --file /scripts/consultas.js
q-redis:      ## roda as consultas guiadas do Redis
	docker exec sudoers_redis sh /scripts/consultas.sh
q-neo4j:      ## roda as consultas guiadas do Neo4j
	docker exec sudoers_neo4j cypher-shell -u neo4j -p sudoers123 \
	  --format plain -f /scripts/consultas.cypher
q-cassandra:  ## roda as consultas guiadas do Cassandra
	docker exec sudoers_cassandra bash /scripts/consultas.sh
q-clickhouse: ## roda as consultas guiadas do ClickHouse
	docker exec sudoers_clickhouse bash /scripts/consultas.sh

# ------------------------------------------------- integracao jornada_dados
lake-conectar:    ## liga os containers a rede do jornada_dados
	./integracao/conectar_lake.sh
lake-desconectar: ## desfaz a ligacao de rede
	./integracao/conectar_lake.sh desfazer
lake-oltp:        ## carrega o universo no Postgres OLTP do jornada_dados
	$(DCL) run --rm seeder python integracao/carga_oltp.py $(args)
lake-export:      ## exporta os 5 bancos para a zona raw do MinIO
	$(DCL) run --rm seeder python integracao/exportar_para_lake.py $(args)

# ------------------------------------------------------------------ testes
validar:     ## confere que os 5 bancos batem com o gerador
	$(DC) run --rm seeder python tests/validar.py

# --------------------------------------------------------------- socorro
consertar:   ## recria os containers quebrados (NAO apaga os dados)
	@echo "Recriando os containers. Os volumes (seus dados) sao preservados."
	$(DC) --profile tudo up -d --force-recreate
	@bash scripts/esperar.sh
	@echo
	@echo "Se ainda houver problema, rode:  make diagnostico"

diagnostico: ## junta tudo que o instrutor precisa para te ajudar
	@bash scripts/diagnostico.sh
