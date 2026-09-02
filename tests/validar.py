#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Validador da Liga Sudoers NoSQL.

O QUE ELE FAZ
-------------
Regera o universo canonico em memoria e compara, banco por banco, se o que
esta gravado bate com o que o gerador produziu. Se algum numero divergir, ou
o seed nao rodou, ou alguem mexeu nos dados, ou a semente mudou.

Isso e o equivalente, neste repo, ao "Guia de Validacao por Evidencias" do
jornada_dados: cada etapa tem que deixar um rastro conferivel.

Uso:
    make validar
    docker compose run --rm seeder python tests/validar.py
"""
import logging
import os
import sys

sys.path.insert(0, "/app")

# Quando um banco esta fora do ar, os drivers cospem stack trace e mensagens
# soltas no stderr ("Unexpected Http Driver Exception"). Aqui isso e ESPERADO
# - o validador ja informa "indisponivel" de forma clara - entao calamos o
# ruido para o aluno nao achar que quebrou alguma coisa.
for _nome in ("clickhouse_connect", "cassandra", "neo4j", "pymongo", "urllib3"):
    logging.getLogger(_nome).setLevel(logging.CRITICAL)
logging.getLogger().setLevel(logging.CRITICAL)

from gerador.liga_sudoers_gen import gerar_universo

VERDE, VERMELHO, AMARELO, CINZA, FIM = "\033[92m", "\033[91m", "\033[93m", "\033[90m", "\033[0m"

resultados = []


def checar(banco: str, o_que: str, obtido, esperado) -> None:
    ok = obtido == esperado
    resultados.append((banco, o_que, ok, obtido, esperado))
    marca = f"{VERDE}✅{FIM}" if ok else f"{VERMELHO}❌{FIM}"
    extra = "" if ok else f"  {VERMELHO}(esperado {esperado}){FIM}"
    print(f"    {marca} {o_que:<44} {obtido}{extra}")


def pular(banco: str, erro: Exception) -> None:
    resultados.append((banco, "conexao", None, str(erro)[:60], ""))
    print(f"    {AMARELO}⏭️  indisponivel{FIM} {CINZA}{type(erro).__name__}: {str(erro)[:70]}{FIM}")


def main() -> int:
    u = gerar_universo(
        semente=int(os.getenv("SEMENTE", 42)),
        n_pessoas=int(os.getenv("N_PESSOAS", 500)),
        n_produtos=int(os.getenv("N_PRODUTOS", 200)),
        n_pedidos=int(os.getenv("N_PEDIDOS", 5000)),
    )
    r = u.resumo()
    print(f"\nuniverso canonico (semente={u.semente})")
    for k in ("pessoas", "produtos", "pedidos", "itens_pedidos",
              "eventos_clickstream", "reviews", "pedidos_fraudulentos", "aneis_fraude"):
        print(f"    {CINZA}{k:<24}{FIM} {r[k]}")

    fraude_motivo = r["fraude_por_motivo"]

    # ------------------------------------------------------------- MongoDB
    print(f"\n{'─'*70}\n📄 MongoDB (documento)")
    try:
        from pymongo import MongoClient
        db = MongoClient(os.getenv("MONGO_URI"), serverSelectionTimeoutMS=8000)["liga_sudoers"]
        checar("mongo", "produtos", db.produtos.count_documents({}), r["produtos"])
        checar("mongo", "pessoas", db.pessoas.count_documents({}), r["pessoas"])
        checar("mongo", "pedidos", db.pedidos.count_documents({}), r["pedidos"])
        checar("mongo", "pedidos fraudulentos", db.pedidos.count_documents({"fraude": True}),
               r["pedidos_fraudulentos"])
        for motivo, qtde in sorted(fraude_motivo.items()):
            checar("mongo", f"fraude: {motivo}",
                   db.pedidos.count_documents({"motivo_fraude": motivo}), qtde)
        checar("mongo", "nome da pessoa 1",
               db.pessoas.find_one({"_id": 1})["nome"], u.pessoas[0]["nome"])
        checar("mongo", "indice TTL em sessoes_checkout",
               any(i.get("expireAfterSeconds") is not None
                   for i in db.sessoes_checkout.list_indexes()), True)
    except Exception as e:
        pular("mongo", e)

    # --------------------------------------------------------------- Redis
    print(f"\n{'─'*70}\n🔑 Redis (chave-valor)")
    try:
        import redis
        rd = redis.Redis(host=os.getenv("REDIS_HOST", "redis"),
                         password=os.getenv("REDIS_PASS", "sudoers"),
                         decode_responses=True, socket_timeout=8)
        rd.ping()
        checar("redis", "ranking de produtos (ZSET)", rd.zcard("rank:produtos"), r["produtos"])
        checar("redis", "alertas no STREAM de fraude", rd.xlen("stream:fraude"),
               r["pedidos_fraudulentos"])
        checar("redis", "device atual da pessoa 1", rd.get("device:atual:1"),
               u.pessoas[0]["device_id"])
        for motivo, qtde in sorted(fraude_motivo.items()):
            checar("redis", f"contador: {motivo}",
                   int(rd.get(f"metrica:fraude_motivo:{motivo}") or 0), qtde)
        checar("redis", "geo:pedidos indexado", rd.zcard("geo:pedidos"), r["pedidos"])
    except Exception as e:
        pular("redis", e)

    # --------------------------------------------------------------- Neo4j
    print(f"\n{'─'*70}\n🕸️  Neo4j (grafo)")
    try:
        from neo4j import GraphDatabase
        drv = GraphDatabase.driver(os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
                                   auth=(os.getenv("NEO4J_USER", "neo4j"),
                                         os.getenv("NEO4J_PASS", "sudoers123")))
        with drv.session() as s:
            um = lambda q: s.run(q).single()[0]
            checar("neo4j", "nos (:Pessoa)", um("MATCH (n:Pessoa) RETURN count(n)"), r["pessoas"])
            checar("neo4j", "nos (:Produto)", um("MATCH (n:Produto) RETURN count(n)"), r["produtos"])
            checar("neo4j", "nos (:Pedido)", um("MATCH (n:Pedido) RETURN count(n)"), r["pedidos"])
            checar("neo4j", "arestas [:CONTEM]",
                   um("MATCH ()-[x:CONTEM]->() RETURN count(x)"), r["itens_pedidos"])
            checar("neo4j", "pedidos marcados como fraude",
                   um("MATCH (p:Pedido) WHERE p.fraude RETURN count(p)"), r["pedidos_fraudulentos"])
            # a validacao mais importante do repo:
            checar("neo4j", "ANEIS detectados por Cypher", um("""
                MATCH (d:Dispositivo)<-[:USOU]-(:Pedido)<-[:FEZ]-(p:Pessoa)
                WITH d, count(DISTINCT p) AS n WHERE n > 1 RETURN count(d)
            """), r["aneis_fraude"])
        drv.close()
    except Exception as e:
        pular("neo4j", e)

    # ----------------------------------------------------------- Cassandra
    print(f"\n{'─'*70}\n🏛️  Cassandra (wide-column)")
    try:
        from cassandra.cluster import Cluster
        cs = Cluster([os.getenv("CASSANDRA_HOST", "cassandra")], connect_timeout=25).connect("liga_sudoers")
        n = lambda t: cs.execute(f"SELECT count(*) AS n FROM {t}").one().n
        checar("cassandra", "eventos_por_pessoa", n("eventos_por_pessoa"), r["eventos_clickstream"])
        checar("cassandra", "eventos_por_dia (mesma carga)", n("eventos_por_dia"),
               r["eventos_clickstream"])
        checar("cassandra", "pedidos_por_pessoa", n("pedidos_por_pessoa"), r["pedidos"])
        checar("cassandra", "as 2 tabelas de evento batem",
               n("eventos_por_pessoa") == n("eventos_por_dia"), True)
    except Exception as e:
        pular("cassandra", e)

    # ---------------------------------------------------------- ClickHouse
    print(f"\n{'─'*70}\n📈 ClickHouse (colunar)")
    try:
        import clickhouse_connect
        ch = clickhouse_connect.get_client(host=os.getenv("CLICKHOUSE_HOST", "clickhouse"),
                                           username=os.getenv("CLICKHOUSE_USER", "sudoers"),
                                           password=os.getenv("CLICKHOUSE_PASS", "sudoers"))
        v = lambda q: ch.query(q).result_rows[0][0]
        checar("clickhouse", "fato_pedidos", v("SELECT count() FROM liga_sudoers.fato_pedidos"),
               r["pedidos"])
        checar("clickhouse", "fato_itens", v("SELECT count() FROM liga_sudoers.fato_itens"),
               r["itens_pedidos"])
        checar("clickhouse", "dim_pessoas", v("SELECT count() FROM liga_sudoers.dim_pessoas"),
               r["pessoas"])
        checar("clickhouse", "fraudes", v("SELECT sum(fraude) FROM liga_sudoers.fato_pedidos"),
               r["pedidos_fraudulentos"])
        # a MV tem que ter sido preenchida sozinha, no INSERT
        checar("clickhouse", "MV bate com a tabela fato",
               v("SELECT sum(pedidos) FROM liga_sudoers.agg_vendas_dia"), r["pedidos"])
        # e a regra de fraude do jornada_dados: fora de SP/MG/RJ = 100% fraude
        checar("clickhouse", "fora de SP/MG/RJ e 100% fraude",
               v("""SELECT count() FROM liga_sudoers.fato_pedidos
                    WHERE uf NOT IN ('SP','MG','RJ') AND fraude = 0"""), 0)
    except Exception as e:
        pular("clickhouse", e)

    # ------------------------------------------------------------- resumo
    testes = [x for x in resultados if x[2] is not None]
    ok = sum(1 for x in testes if x[2])
    falhou = [x for x in testes if not x[2]]
    ausentes = sorted({x[0] for x in resultados if x[2] is None})

    print(f"\n{'═'*70}")
    print(f"  {VERDE}{ok} passaram{FIM}   {VERMELHO}{len(falhou)} falharam{FIM}"
          f"   {AMARELO}{len(ausentes)} bancos fora do ar{FIM}")
    if ausentes:
        print(f"  {AMARELO}nao testados: {', '.join(ausentes)}{FIM}"
              f"  {CINZA}(suba o profile e rode o seed){FIM}")
    if falhou:
        print(f"\n  {VERMELHO}falhas:{FIM}")
        for banco, o_que, _, obtido, esperado in falhou:
            print(f"    {banco}: {o_que} -> obtido {obtido}, esperado {esperado}")
        print(f"\n  {CINZA}Causa mais comum: o seed nao rodou depois de mudar a semente.{FIM}")
        print(f"  {CINZA}Rode: make seed{FIM}")
    print(f"{'═'*70}\n")
    return 1 if falhou else 0


if __name__ == "__main__":
    raise SystemExit(main())
