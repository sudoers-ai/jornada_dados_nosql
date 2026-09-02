# -*- coding: utf-8 -*-
"""
Painel Liga Sudoers NoSQL - a MESMA pergunta, nos 5 paradigmas.

A ideia do painel nao e ser bonito. E ser HONESTO: cada aba faz a mesma
pergunta de negocio no banco correspondente, mostra a consulta que foi
usada e cronometra. Assim voce ve, com numero na tela, onde cada
paradigma brilha e onde ele sofre.

Sobe com:
    docker compose --profile viz up -d
    http://localhost:8501
"""
import os
import time
from contextlib import contextmanager

import pandas as pd
import plotly.express as px
import streamlit as st

st.set_page_config(page_title="Liga Sudoers NoSQL", page_icon="🗄️", layout="wide")

CORES = ["#4C6EF5", "#F76707", "#0CA678", "#F03E3E", "#7048E8", "#1098AD"]


@contextmanager
def cronometro(rotulo: str):
    ini = time.perf_counter()
    caixa = {}
    yield caixa
    caixa["ms"] = (time.perf_counter() - ini) * 1000
    st.caption(f"⏱️ {rotulo}: **{caixa['ms']:.1f} ms**")


def consulta(texto: str, linguagem: str = "sql"):
    with st.expander("ver a consulta que gerou isto"):
        st.code(texto.strip(), language=linguagem)


# --------------------------------------------------------------- conexoes
@st.cache_resource
def con_mongo():
    from pymongo import MongoClient
    return MongoClient(os.getenv("MONGO_URI"), serverSelectionTimeoutMS=5000)


@st.cache_resource
def con_redis():
    import redis
    return redis.Redis(host=os.getenv("REDIS_HOST", "redis"),
                       password=os.getenv("REDIS_PASS", "sudoers"), decode_responses=True)


@st.cache_resource
def con_neo4j():
    from neo4j import GraphDatabase
    return GraphDatabase.driver(os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
                                auth=(os.getenv("NEO4J_USER", "neo4j"),
                                      os.getenv("NEO4J_PASS", "sudoers123")))


@st.cache_resource
def con_cassandra():
    from cassandra.cluster import Cluster
    return Cluster([os.getenv("CASSANDRA_HOST", "cassandra")], connect_timeout=20).connect("liga_sudoers")


@st.cache_resource
def con_clickhouse():
    import clickhouse_connect
    return clickhouse_connect.get_client(host=os.getenv("CLICKHOUSE_HOST", "clickhouse"),
                                         username=os.getenv("CLICKHOUSE_USER", "sudoers"),
                                         password=os.getenv("CLICKHOUSE_PASS", "sudoers"))


def indisponivel(nome: str, erro: Exception):
    st.warning(f"**{nome}** nao esta acessivel agora.\n\n`{type(erro).__name__}: {str(erro)[:200]}`")
    st.info(f"Suba o profile correspondente e rode o seed. Veja o README da pasta `{nome.lower()}/`.")


# ============================================================== cabecalho
st.title("🗄️ Liga Sudoers — o lado NoSQL")
st.markdown(
    "Cinco paradigmas, **o mesmo universo de dados** (mesma semente). "
    "Cada aba responde a uma pergunta que aquele banco resolve melhor que os outros."
)

abas = st.tabs(["📊 Visão geral", "📄 Documento", "🔑 Chave-valor",
                "🕸️ Grafo", "🏛️ Wide-column", "📈 Colunar", "⚖️ Comparativo"])

# ------------------------------------------------------------ visao geral
with abas[0]:
    try:
        ch = con_clickhouse()
        with cronometro("ClickHouse — KPIs"):
            kpi = ch.query("""
                SELECT count() AS pedidos, sum(fraude) AS fraudes,
                       round(sum(valor_total),2) AS faturamento,
                       uniq(id_pessoa) AS clientes
                FROM liga_sudoers.fato_pedidos
            """).result_rows[0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Pedidos", f"{kpi[0]:,}".replace(",", "."))
        c2.metric("Clientes únicos", f"{kpi[3]:,}".replace(",", "."))
        c3.metric("Faturamento", f"R$ {kpi[2]:,.0f}".replace(",", "."))
        c4.metric("Fraudes", f"{kpi[1]:,}".replace(",", "."),
                  delta=f"{100*kpi[1]/kpi[0]:.2f}% do total", delta_color="inverse")

        st.divider()
        e1, e2 = st.columns(2)
        with e1:
            st.subheader("Faturamento por dia")
            df = ch.query_df("""
                SELECT dia, toFloat64(sum(faturamento)) AS faturamento,
                       toUInt64(sum(fraudes)) AS fraudes
                FROM liga_sudoers.agg_vendas_dia GROUP BY dia ORDER BY dia
            """)
            fig = px.area(df, x="dia", y="faturamento",
                          color_discrete_sequence=[CORES[0]])
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=300)
            st.plotly_chart(fig, use_container_width=True)
        with e2:
            st.subheader("Taxa de fraude por UF")
            df = ch.query_df("""
                SELECT uf, count() AS pedidos, sum(fraude) AS fraudes,
                       round(100.0*sum(fraude)/count(),2) AS pct_fraude
                FROM liga_sudoers.fato_pedidos GROUP BY uf ORDER BY pct_fraude DESC
            """)
            fig = px.bar(df, x="uf", y="pct_fraude", color="pct_fraude",
                         color_continuous_scale=["#0CA678", "#F03E3E"],
                         labels={"pct_fraude": "% fraude", "uf": "UF"})
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=300,
                              coloraxis_showscale=False)
            st.plotly_chart(fig, use_container_width=True)
            st.caption("UFs fora de SP/MG/RJ têm 100% de fraude: é a regra do `jornada_dados`.")

        st.subheader("Onde as compras aconteceram")
        mapa = ch.query_df("""
            SELECT lat, lon, uf, fraude, toFloat64(valor_total) AS valor_total
            FROM liga_sudoers.fato_pedidos ORDER BY rand() LIMIT 3000
        """)
        mapa["tipo"] = mapa["fraude"].map({0: "legítimo", 1: "fraude"})
        fig = px.scatter_map(mapa, lat="lat", lon="lon", color="tipo",
                             color_discrete_map={"legítimo": CORES[0], "fraude": CORES[3]},
                             zoom=3, height=420, hover_data=["uf"],
                             map_style="carto-positron")
        fig.update_layout(margin=dict(l=0, r=0, t=0, b=0))
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        indisponivel("ClickHouse", e)

# -------------------------------------------------------------- documento
with abas[1]:
    st.subheader("MongoDB — o mesmo campo com chaves diferentes")
    st.markdown("Pergunta: **quais os atributos de um produto?** A resposta muda por categoria.")
    try:
        db = con_mongo()["liga_sudoers"]
        cats = sorted(db.produtos.distinct("categoria"))
        cat = st.selectbox("categoria", cats, index=cats.index("Livros") if "Livros" in cats else 0)
        with cronometro("MongoDB — find por categoria"):
            docs = list(db.produtos.find({"categoria": cat},
                                         {"descricao": 1, "valor_unit": 1,
                                          "atributos": 1, "avaliacao": 1}).limit(8))
        for d in docs[:4]:
            st.json({k: v for k, v in d.items() if k != "_id"}, expanded=False)
        consulta(f'db.produtos.find({{ categoria: "{cat}" }})', "javascript")

        st.divider()
        st.markdown("**Nota média por categoria** (reviews embutidas — nenhum JOIN)")
        with cronometro("MongoDB — aggregation"):
            agg = list(db.produtos.aggregate([
                {"$match": {"avaliacao.media": {"$ne": None}}},
                {"$group": {"_id": "$categoria", "nota": {"$avg": "$avaliacao.media"},
                            "produtos": {"$sum": 1}}},
                {"$sort": {"nota": -1}}]))
        df = pd.DataFrame(agg).rename(columns={"_id": "categoria"})
        fig = px.bar(df, x="categoria", y="nota", color_discrete_sequence=[CORES[2]])
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=320, yaxis_range=[3, 5])
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        indisponivel("MongoDB", e)

# ------------------------------------------------------------ chave-valor
with abas[2]:
    st.subheader("Redis — o estado quente da decisão antifraude")
    try:
        r = con_redis()
        c1, c2, c3 = st.columns(3)
        c1.metric("Chaves no banco", f"{r.dbsize():,}".replace(",", "."))
        c2.metric("Memória usada", r.info("memory")["used_memory_human"])
        c3.metric("Alertas no STREAM", f"{r.xlen('stream:fraude'):,}".replace(",", "."))

        st.divider()
        pid = st.number_input("consultar a pessoa id", 1, 500, 1, step=1)
        with cronometro("Redis — GET + SMEMBERS"):
            atual = r.get(f"device:atual:{pid}")
            hist = sorted(r.smembers(f"device:hist:{pid}"))
            perfil = r.hgetall(f"pessoa:{pid}")
        a, b = st.columns([1, 2])
        with a:
            st.write("**Perfil**"); st.json(perfil, expanded=True)
        with b:
            st.write("**Dispositivos**")
            st.metric("device atual", atual or "—")
            st.write("histórico:", hist)
            if len(hist) > 1:
                st.error(f"⚠️ {len(hist)} aparelhos distintos — candidato a fraude por troca de dispositivo.")
            else:
                st.success("✅ um único aparelho — comportamento normal.")
        consulta(f"GET device:atual:{pid}\nSMEMBERS device:hist:{pid}\nHGETALL pessoa:{pid}", "bash")

        st.divider()
        st.markdown("**Top 15 produtos (ZSET — já vem ordenado)**")
        with cronometro("Redis — ZREVRANGE"):
            top = r.zrevrange("rank:produtos", 0, 14, withscores=True)
        df = pd.DataFrame(top, columns=["produto", "unidades"])
        fig = px.bar(df, x="produto", y="unidades", color_discrete_sequence=[CORES[1]])
        fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=300)
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        indisponivel("Redis", e)

# ------------------------------------------------------------------ grafo
with abas[3]:
    st.subheader("Neo4j — o anel de fraude que nenhuma regra de linha pega")
    try:
        drv = con_neo4j()
        with drv.session() as s:
            with cronometro("Neo4j — detecção de anéis"):
                aneis = [dict(x) for x in s.run("""
                    MATCH (d:Dispositivo)<-[:USOU]-(:Pedido)<-[:FEZ]-(p:Pessoa)
                    WITH d, collect(DISTINCT p.id) AS pessoas, count(DISTINCT p) AS qtd
                    WHERE qtd > 1
                    RETURN d.device_id AS dispositivo, d.modelo AS modelo,
                           qtd AS contas, pessoas ORDER BY qtd DESC
                """)]
            st.metric("Anéis de fraude encontrados", len(aneis))
            st.dataframe(pd.DataFrame(aneis), use_container_width=True, hide_index=True)
            consulta("""
MATCH (d:Dispositivo)<-[:USOU]-(:Pedido)<-[:FEZ]-(p:Pessoa)
WITH d, collect(DISTINCT p.id) AS pessoas, count(DISTINCT p) AS qtd
WHERE qtd > 1
RETURN d.device_id, d.modelo, qtd, pessoas ORDER BY qtd DESC""", "cypher")

            if aneis:
                st.divider()
                escolha = st.selectbox("investigar o anel do dispositivo",
                                       [a["dispositivo"] for a in aneis])
                with cronometro("Neo4j — membros do anel"):
                    membros = [dict(x) for x in s.run("""
                        MATCH (d:Dispositivo {device_id: $dev})<-[:USOU]-(ped:Pedido)<-[:FEZ]-(p:Pessoa)
                        RETURN p.id AS id, p.nome AS nome, p.cpf AS cpf, p.uf AS uf,
                               count(ped) AS pedidos, round(sum(ped.valor_total),2) AS total
                        ORDER BY total DESC
                    """, dev=escolha)]
                st.dataframe(pd.DataFrame(membros), use_container_width=True, hide_index=True)
                st.error("Nomes, CPFs e UFs diferentes. Um único aparelho físico. "
                         "Nenhuma dessas linhas, isolada, parece fraude.")

            st.divider()
            st.markdown("**Top 15 por score de risco** — este número volta para o DW do `jornada_dados`")
            with cronometro("Neo4j — score de risco"):
                score = [dict(x) for x in s.run("""
                    MATCH (p:Pessoa)-[:FEZ]->(ped:Pedido)
                    OPTIONAL MATCH (ped)-[:USOU]->(d:Dispositivo)
                    OPTIONAL MATCH (d)<-[:USOU]-(:Pedido)<-[:FEZ]-(o:Pessoa) WHERE o <> p
                    WITH p, count(DISTINCT ped) AS pedidos,
                         count(DISTINCT CASE WHEN ped.fraude THEN ped END) AS fraudes,
                         count(DISTINCT d) AS dispositivos, count(DISTINCT o) AS vizinhos
                    RETURN p.nome AS nome, pedidos, fraudes, dispositivos, vizinhos,
                           round(100.0*(0.4*(toFloat(fraudes)/pedidos)
                             + 0.3*(CASE WHEN dispositivos>1 THEN 1.0 ELSE 0.0 END)
                             + 0.3*(CASE WHEN vizinhos>0 THEN 1.0 ELSE 0.0 END)),1) AS score
                    ORDER BY score DESC LIMIT 15
                """)]
            st.dataframe(pd.DataFrame(score), use_container_width=True, hide_index=True)
        st.info("Para ver o grafo desenhado: **http://localhost:7474** (usuário `neo4j`, senha `sudoers123`)")
    except Exception as e:
        indisponivel("Neo4j", e)

# ------------------------------------------------------------ wide-column
with abas[4]:
    st.subheader("Cassandra — a consulta só existe se a chave permitir")
    try:
        cs = con_cassandra()
        pid = st.number_input("timeline da pessoa id", 1, 500, 1, step=1, key="cass")
        with cronometro("Cassandra — leitura por partition key"):
            linhas = list(cs.execute(
                "SELECT ts, tipo_evento, categoria, id_produto, duracao_ms "
                "FROM eventos_por_pessoa WHERE id_pessoa = %s LIMIT 40", (pid,)))
        if linhas:
            df = pd.DataFrame(linhas)
            st.dataframe(df, use_container_width=True, hide_index=True, height=280)
            fig = px.histogram(df, x="tipo_evento", color_discrete_sequence=[CORES[4]])
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=280)
            st.plotly_chart(fig, use_container_width=True)
        else:
            st.info("Essa pessoa não gerou eventos de clickstream.")
        consulta("SELECT * FROM eventos_por_pessoa WHERE id_pessoa = ? LIMIT 40;", "sql")
        st.success("Rápido porque `id_pessoa` é a **partition key**: o coordenador "
                   "sabe exatamente em qual nó o dado está.")
        st.warning("A mesma tabela **não** responde “quais eventos do tipo compra?”. "
                   "Sem a partition key, o Cassandra recusa a consulta — por isso existe "
                   "a tabela `eventos_por_dia`, com o mesmo dado e outra chave.")
    except Exception as e:
        indisponivel("Cassandra", e)

# ---------------------------------------------------------------- colunar
with abas[5]:
    st.subheader("ClickHouse — agregação sobre tudo, em milissegundos")
    try:
        ch = con_clickhouse()
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Faturamento por categoria**")
            with cronometro("ClickHouse — GROUP BY em 14.924 itens"):
                df = ch.query_df("""
                    SELECT categoria, toFloat64(round(sum(valor_total),2)) AS faturamento,
                           toUInt64(sum(qtde)) AS unidades
                    FROM liga_sudoers.fato_itens GROUP BY categoria ORDER BY faturamento DESC
                """)
            fig = px.bar(df, x="faturamento", y="categoria", orientation="h",
                         color_discrete_sequence=[CORES[0]])
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=420,
                              yaxis={"categoryorder": "total ascending"})
            st.plotly_chart(fig, use_container_width=True)
        with c2:
            st.markdown("**Média móvel de 7 dias**")
            with cronometro("ClickHouse — window function"):
                # toFloat64: sem isso o ClickHouse devolve Decimal e o plotly
                # recusa desenhar duas series de tipos diferentes no mesmo grafico.
                df = ch.query_df("""
                    SELECT dia,
                      toFloat64(round(f,2)) AS faturamento,
                      toFloat64(round(avg(f) OVER (ORDER BY dia
                        ROWS BETWEEN 6 PRECEDING AND CURRENT ROW),2)) AS media_7d
                    FROM (SELECT dia, sum(faturamento) AS f FROM liga_sudoers.agg_vendas_dia
                          GROUP BY dia ORDER BY dia)
                """)
            fig = px.line(df, x="dia", y=["faturamento", "media_7d"],
                          color_discrete_sequence=[CORES[5], CORES[1]])
            fig.update_layout(margin=dict(l=0, r=0, t=10, b=0), height=420,
                              legend_title="", legend=dict(orientation="h", y=1.1))
            st.plotly_chart(fig, use_container_width=True)

        st.divider()
        st.markdown("**Compressão real em disco** — o motivo de o colunar ocupar menos")
        df = ch.query_df("""
            SELECT table AS tabela, sum(rows) AS linhas,
                   formatReadableSize(sum(data_uncompressed_bytes)) AS cru,
                   formatReadableSize(sum(data_compressed_bytes)) AS comprimido,
                   round(sum(data_uncompressed_bytes)/sum(data_compressed_bytes),2) AS fator
            FROM system.parts WHERE database='liga_sudoers' AND active
            GROUP BY table ORDER BY sum(rows) DESC
        """)
        st.dataframe(df, use_container_width=True, hide_index=True)
    except Exception as e:
        indisponivel("ClickHouse", e)

# ------------------------------------------------------------- comparativo
with abas[6]:
    st.subheader("A mesma pergunta nos 5 bancos")
    st.markdown("**Pergunta:** _quantos pedidos a pessoa 1 fez?_ — a resposta é a mesma; "
                "o custo e o esforço, não.")
    linhas = []

    def medir(nome, fn, como):
        ini = time.perf_counter()
        try:
            v = fn()
            ms = (time.perf_counter() - ini) * 1000
            linhas.append({"banco": nome, "resposta": v, "tempo_ms": round(ms, 2), "como": como})
        except Exception as e:
            linhas.append({"banco": nome, "resposta": "erro", "tempo_ms": None,
                           "como": f"{type(e).__name__}"})

    medir("MongoDB (documento)",
          lambda: con_mongo()["liga_sudoers"].pedidos.count_documents({"id_pessoa": 1}),
          "count_documents com índice em id_pessoa")
    medir("Redis (chave-valor)",
          lambda: con_redis().llen("pessoa:ultimos_pedidos:1"),
          "LLEN — só os últimos 10; o Redis guarda estado quente, não histórico")
    medir("Neo4j (grafo)",
          lambda: con_neo4j().session().run(
              "MATCH (:Pessoa {id:1})-[:FEZ]->(p:Pedido) RETURN count(p) AS n").single()["n"],
          "percorre as arestas FEZ a partir do nó")
    medir("Cassandra (wide-column)",
          lambda: con_cassandra().execute(
              "SELECT count(*) AS n FROM pedidos_por_pessoa WHERE id_pessoa = 1").one().n,
          "partition key = id_pessoa: uma partição, um nó")
    medir("ClickHouse (colunar)",
          lambda: con_clickhouse().query(
              "SELECT count() FROM liga_sudoers.fato_pedidos WHERE id_pessoa = 1").result_rows[0][0],
          "varre a coluna id_pessoa (não é o ORDER BY da tabela)")

    st.dataframe(pd.DataFrame(linhas), use_container_width=True, hide_index=True)
    st.caption("O Redis responde 10 porque guarda só os últimos 10 — é a modelagem, "
               "não um erro. Cada banco responde o que foi projetado para responder.")

    st.divider()
    st.markdown("""
| Precisa de… | Use | Não use |
|---|---|---|
| schema que varia por item | **MongoDB** | Cassandra (schema fixo por tabela) |
| estado quente em < 1 ms | **Redis** | ClickHouse (é analítico, não operacional) |
| relação entre entidades, N saltos | **Neo4j** | qualquer um dos outros |
| escrita massiva ordenada por chave | **Cassandra** | MongoDB (não escala igual em escrita) |
| agregação sobre bilhões de linhas | **ClickHouse** | Cassandra (nem tenta) |
| transação com débito e crédito | **PostgreSQL** | todos os cinco acima |
""")
    st.info("A última linha é a mais importante: **NoSQL não substitui o relacional.** "
            "O `jornada_dados` continua sendo o coração transacional. Este repo são os satélites.")
