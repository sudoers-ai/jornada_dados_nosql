#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Exporta os 5 bancos NoSQL para a zona `raw` do Data Lake (MinIO) do
repo `jornada_dados`.

O PAPEL DESTE SCRIPT
--------------------
Ate aqui, cada banco resolveu um problema OPERACIONAL. Nenhum deles foi feito
para responder "qual o faturamento por UF no ultimo trimestre". Essa pergunta
e do Data Lake.

Este script e a ponte batch: le de cada paradigma no formato que ELE tem e
grava no lake num formato unico (Parquet), pronto para o Spark do outro repo
promover para trusted/refined.

DECISAO IMPORTANTE - por que produtos sai em JSON e nao em Parquet:
    Os produtos do Mongo tem `atributos` com chaves diferentes por categoria.
    Forcar isso em Parquet exigiria achatar tudo numa unica super-tabela
    esparsa e perder informacao. Entao a zona raw preserva o JSON como veio
    (raw = fiel a origem), e a decisao de achatar fica para a camada trusted.
    Isso e o que "raw" significa: o dado como ele e, nao como voce queria.

Uso:
    docker compose -f docker-compose.yml -f docker-compose.lake.yml \
      run --rm seeder python integracao/exportar_para_lake.py
"""
import io
import json
import os
import sys
from datetime import datetime, date
from decimal import Decimal

sys.path.insert(0, "/app")

import boto3
import pyarrow as pa
import pyarrow.parquet as pq
from botocore.client import Config
from botocore.exceptions import EndpointConnectionError

MINIO_ENDPOINT = os.getenv("MINIO_ENDPOINT", "http://minio:9000")
MINIO_KEY = os.getenv("MINIO_KEY", "sudoers123")
MINIO_SECRET = os.getenv("MINIO_SECRET", "sudoers1234")
BUCKET = os.getenv("LAKE_BUCKET", "raw")
CARIMBO = datetime.now().strftime("%Y-%m-%d")


def _s3():
    return boto3.client("s3", endpoint_url=MINIO_ENDPOINT,
                        aws_access_key_id=MINIO_KEY,
                        aws_secret_access_key=MINIO_SECRET,
                        config=Config(signature_version="s3v4"),
                        region_name="us-east-1")


def _normalizar(v):
    if isinstance(v, Decimal):
        return float(v)
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    return v


def gravar_parquet(s3, origem: str, nome: str, linhas: list) -> int:
    """Grava em raw/<origem>/<nome>/dt=<data>/<nome>.parquet"""
    if not linhas:
        print(f"    (nada a exportar em {origem}/{nome})")
        return 0
    linhas = [{k: _normalizar(v) for k, v in l.items()} for l in linhas]
    tabela = pa.Table.from_pylist(linhas)
    buf = io.BytesIO()
    pq.write_table(tabela, buf, compression="snappy")
    corpo = buf.getvalue()
    chave = f"{origem}/{nome}/dt={CARIMBO}/{nome}.parquet"
    s3.put_object(Bucket=BUCKET, Key=chave, Body=corpo)
    print(f"    s3a://{BUCKET}/{chave}  ({len(linhas)} linhas, {len(corpo)} bytes)")
    return len(linhas)


def gravar_jsonl(s3, origem: str, nome: str, docs: list) -> int:
    """JSON Lines: preserva schema variavel, que e o ponto do MongoDB."""
    if not docs:
        return 0
    corpo = "\n".join(json.dumps(d, ensure_ascii=False, default=str) for d in docs)
    chave = f"{origem}/{nome}/dt={CARIMBO}/{nome}.jsonl"
    s3.put_object(Bucket=BUCKET, Key=chave, Body=corpo.encode("utf-8"))
    print(f"    s3a://{BUCKET}/{chave}  ({len(docs)} docs, {len(corpo)} bytes)")
    return len(docs)


# --------------------------------------------------------------------------
def do_mongo(s3) -> int:
    from pymongo import MongoClient
    cli = MongoClient(os.getenv("MONGO_URI"), serverSelectionTimeoutMS=8000)
    db = cli["liga_sudoers"]
    print("  [documento] MongoDB")
    n = gravar_jsonl(s3, "mongodb", "produtos",
                     list(db.produtos.find({}, {"reviews": 0})))
    n += gravar_parquet(s3, "mongodb", "pedidos", [
        {"id_pedido": d["_id"], "id_pessoa": d["id_pessoa"],
         "dt_venda": d["dt_venda"], "valor_total": d["valor_total"],
         "qtd_itens": len(d["itens"]), "fraude": d["fraude"],
         "motivo_fraude": d.get("motivo_fraude") or "",
         "uf": d["auditoria"]["uf"], "device_id": d["auditoria"]["device_id"]}
        for d in db.pedidos.find()
    ])
    cli.close()
    return n


def do_redis(s3) -> int:
    import redis
    r = redis.Redis(host=os.getenv("REDIS_HOST", "redis"),
                    password=os.getenv("REDIS_PASS", "sudoers"), decode_responses=True)
    print("  [chave-valor] Redis")
    ranking = [{"produto": k, "unidades_vendidas": float(v)}
               for k, v in r.zrevrange("rank:produtos", 0, -1, withscores=True)]
    n = gravar_parquet(s3, "redis", "ranking_produtos", ranking)
    # o STREAM de fraude e o dado mais valioso daqui
    alertas = [{"id_stream": sid, **campos}
               for sid, campos in r.xrange("stream:fraude", count=100000)]
    n += gravar_parquet(s3, "redis", "alertas_fraude", alertas)
    return n


def do_neo4j(s3) -> int:
    from neo4j import GraphDatabase
    drv = GraphDatabase.driver(os.getenv("NEO4J_URI", "bolt://neo4j:7687"),
                               auth=(os.getenv("NEO4J_USER", "neo4j"),
                                     os.getenv("NEO4J_PASS", "sudoers123")))
    print("  [grafo] Neo4j")
    with drv.session() as s:
        # ESTE e o dado que so o grafo consegue produzir: o score de risco
        # calculado a partir das LIGACOES, nao dos atributos de cada linha.
        score = [dict(r) for r in s.run("""
            MATCH (p:Pessoa)-[:FEZ]->(ped:Pedido)
            OPTIONAL MATCH (ped)-[:USOU]->(d:Dispositivo)
            OPTIONAL MATCH (d)<-[:USOU]-(:Pedido)<-[:FEZ]-(outro:Pessoa) WHERE outro <> p
            WITH p, count(DISTINCT ped) AS pedidos,
                 count(DISTINCT CASE WHEN ped.fraude THEN ped END) AS fraudes,
                 count(DISTINCT d) AS dispositivos,
                 count(DISTINCT outro) AS contas_vizinhas
            RETURN p.id AS id_pessoa, pedidos, fraudes, dispositivos, contas_vizinhas,
                   round(100.0 * (0.4*(toFloat(fraudes)/pedidos)
                        + 0.3*(CASE WHEN dispositivos > 1 THEN 1.0 ELSE 0.0 END)
                        + 0.3*(CASE WHEN contas_vizinhas > 0 THEN 1.0 ELSE 0.0 END)), 1) AS score_risco
        """)]
        n = gravar_parquet(s3, "neo4j", "score_risco_pessoa", score)

        aneis = [dict(r) for r in s.run("""
            MATCH (d:Dispositivo)<-[:USOU]-(:Pedido)<-[:FEZ]-(p:Pessoa)
            WITH d, collect(DISTINCT p.id) AS pessoas, count(DISTINCT p) AS qtd
            WHERE qtd > 1
            RETURN d.device_id AS device_id, d.modelo AS modelo, qtd AS contas,
                   [x IN pessoas | toString(x)] AS pessoas
        """)]
        n += gravar_parquet(s3, "neo4j", "aneis_fraude", aneis)
    drv.close()
    return n


def do_cassandra(s3) -> int:
    from cassandra.cluster import Cluster
    cl = Cluster([os.getenv("CASSANDRA_HOST", "cassandra")], connect_timeout=20)
    s = cl.connect("liga_sudoers")
    print("  [wide-column] Cassandra")
    eventos = [{"id_pessoa": r.id_pessoa, "ts": r.ts, "tipo_evento": r.tipo_evento,
                "id_produto": r.id_produto, "categoria": r.categoria,
                "id_sessao": r.id_sessao, "device_id": r.device_id,
                "duracao_ms": r.duracao_ms}
               for r in s.execute("SELECT * FROM eventos_por_pessoa")]
    n = gravar_parquet(s3, "cassandra", "clickstream", eventos)
    cl.shutdown()
    return n


def do_clickhouse(s3) -> int:
    import clickhouse_connect
    cli = clickhouse_connect.get_client(host=os.getenv("CLICKHOUSE_HOST", "clickhouse"),
                                        username=os.getenv("CLICKHOUSE_USER", "sudoers"),
                                        password=os.getenv("CLICKHOUSE_PASS", "sudoers"))
    print("  [colunar] ClickHouse")
    res = cli.query("SELECT dia, uf, sum(pedidos) AS pedidos, sum(faturamento) AS faturamento, "
                    "sum(fraudes) AS fraudes FROM liga_sudoers.agg_vendas_dia GROUP BY dia, uf")
    linhas = [dict(zip(res.column_names, r)) for r in res.result_rows]
    return gravar_parquet(s3, "clickhouse", "agg_vendas_dia", linhas)


ORIGENS = {"mongodb": do_mongo, "redis": do_redis, "neo4j": do_neo4j,
           "cassandra": do_cassandra, "clickhouse": do_clickhouse}


def main() -> int:
    alvos = sys.argv[1:] or list(ORIGENS)
    desconhecidos = [a for a in alvos if a not in ORIGENS]
    if desconhecidos:
        print(f"origem desconhecida: {desconhecidos}. Validas: {list(ORIGENS)}")
        return 1

    s3 = _s3()
    try:
        s3.list_buckets()
    except EndpointConnectionError:
        print(f"❌ MinIO nao respondeu em {MINIO_ENDPOINT}.")
        print("   Suba o jornada_dados: cd ../jornada_dados && docker compose up -d minio")
        print("   E use o overlay: -f docker-compose.yml -f docker-compose.lake.yml")
        return 1

    existentes = {b["Name"] for b in s3.list_buckets()["Buckets"]}
    if BUCKET not in existentes:
        s3.create_bucket(Bucket=BUCKET)
        print(f"bucket '{BUCKET}' criado")
    print(f"exportando para s3a://{BUCKET}/ (particao dt={CARIMBO})\n")

    total, falhas = 0, []
    for nome in alvos:
        try:
            total += ORIGENS[nome](s3)
        except Exception as e:
            falhas.append((nome, type(e).__name__, str(e)[:110]))
            print(f"  ⚠️  {nome} falhou: {type(e).__name__}: {str(e)[:110]}")

    print(f"\n  registros exportados: {total}")
    if falhas:
        print("\n  origens que falharam (o banco esta no ar?):")
        for nome, tipo, msg in falhas:
            print(f"    {nome:<12} {tipo}: {msg}")
        return 2

    print("\n✅ Zona raw alimentada. No jornada_dados, siga com o Spark:")
    print("   docker exec -it spark spark-sql   ->   s3a://raw/<origem>/<tabela>/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
