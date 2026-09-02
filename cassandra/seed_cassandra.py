#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Popula o Cassandra (paradigma WIDE-COLUMN) com o universo Liga Sudoers.

POR QUE WIDE-COLUMN AQUI?
-------------------------
Clickstream. Cada pessoa navegando gera dezenas de eventos por sessao: viu a
home, buscou, abriu o produto, colocou no carrinho, tirou do carrinho.

Esse volume tem tres caracteristicas que quebram um banco relacional:
  1. escrita muito mais frequente que leitura;
  2. dado que so faz sentido em ordem cronologica, por chave;
  3. crescimento sem fim - voce nunca "termina" de gerar clickstream.

O Cassandra foi desenhado exatamente para isso: escrita append-only em
commitlog + memtable, sem leitura antes de gravar, e distribuicao por hash da
partition key.

O PRECO: nao existe JOIN, nao existe GROUP BY livre, nao existe ORDER BY
arbitrario. Voce so consulta pelo caminho que a chave primaria permite.

ATENCAO PARA O ALUNO
--------------------
Este script grava o MESMO evento em DUAS tabelas. Isso nao e bug. E o
padrao do Cassandra: uma tabela por pergunta. Compare o custo:
  - duplicar a escrita: barato (escrita e sequencial em disco)
  - varrer particoes na leitura: caro (coordenador consulta todos os nos)

Uso:
    docker compose run --rm seeder python cassandra/seed_cassandra.py
"""
import os
import sys
import uuid
from collections import defaultdict
from datetime import datetime
from decimal import Decimal

sys.path.insert(0, "/app")

from cassandra.cluster import Cluster
from cassandra.query import BatchStatement, BatchType, ConsistencyLevel

from comum import conectar, parametros
from gerador.liga_sudoers_gen import gerar_universo

HOST = os.getenv("CASSANDRA_HOST", "cassandra")
KEYSPACE = "liga_sudoers"
LOTE = 60   # batch grande no Cassandra e ANTIPADRAO. 60 e um teto seguro.


def executar_schema(sessao, caminho: str) -> None:
    """Roda o schema.cql comando a comando (o driver nao aceita script inteiro)."""
    with open(caminho, encoding="utf-8") as fh:
        bruto = fh.read()
    limpo = "\n".join(l for l in bruto.splitlines() if not l.strip().startswith("--"))
    for cmd in (c.strip() for c in limpo.split(";")):
        if not cmd:
            continue
        if cmd.upper().startswith("USE "):
            # o driver nao executa USE: trocamos o keyspace da sessao
            sessao.set_keyspace(cmd.split()[1].strip())
            continue
        sessao.execute(cmd)


def main() -> int:
    u = gerar_universo(**parametros())

    def _abrir():
        c = Cluster([HOST], connect_timeout=10)
        sessao = c.connect()
        sessao.execute("SELECT now() FROM system.local")   # prova que aceita CQL
        return sessao

    s = conectar("Cassandra", _abrir)
    cluster = s.cluster
    print(f"conectado no Cassandra {HOST} | semente={u.semente}")

    executar_schema(s, "/app/cassandra/schema.cql")
    s.set_keyspace(KEYSPACE)
    print("  schema aplicado (4 tabelas + sessoes)")

    ins_pessoa = s.prepare("""
        INSERT INTO eventos_por_pessoa (id_pessoa, ts, id_evento, tipo_evento,
            id_produto, categoria, id_sessao, dispositivo, device_id, geohash, duracao_ms)
        VALUES (?,?,?,?,?,?,?,?,?,?,?)
    """)
    ins_dia = s.prepare("""
        INSERT INTO eventos_por_dia (dia, hora_bucket, ts, id_evento, id_pessoa,
            tipo_evento, id_produto, categoria, device_id)
        VALUES (?,?,?,?,?,?,?,?,?)
    """)
    ins_ped = s.prepare("""
        INSERT INTO pedidos_por_pessoa (id_pessoa, dt_venda, id_pedido, valor_total,
            fraude, motivo_fraude, uf, geohash, device_id, dispositivo, qtd_itens, itens)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
    """)
    ins_sessao = s.prepare("""
        INSERT INTO sessoes_ativas (id_sessao, ts, id_pessoa, device_id) VALUES (?,?,?,?)
    """)
    upd_cont = s.prepare("""
        UPDATE contador_eventos SET total = total + ? WHERE dia = ? AND tipo_evento = ?
    """)

    # ------------------------------------------------- eventos (2x, de proposito)
    contadores = defaultdict(int)
    n = 0
    for ev in u.eventos:
        ts = datetime.fromisoformat(ev["ts"])
        eid = uuid.uuid4()
        s.execute_async(ins_pessoa, (
            ev["id_pessoa"], ts, eid, ev["tipo_evento"], ev["id_produto"],
            ev["categoria"], ev["id_sessao"], ev["dispositivo"], ev["device_id"],
            ev["geohash"], ev["duracao_ms"],
        ))
        s.execute_async(ins_dia, (
            ts.date(), ts.hour, ts, eid, ev["id_pessoa"], ev["tipo_evento"],
            ev["id_produto"], ev["categoria"], ev["device_id"],
        ))
        contadores[(ts.date(), ev["tipo_evento"])] += 1
        n += 1
    print(f"  eventos gravados ..... {n:>6} (x2 tabelas = {n*2} escritas)")

    # ------------------------------------------------------------- pedidos
    for ped in u.pedidos:
        a = ped["auditoria"]
        s.execute_async(ins_ped, (
            ped["id_pessoa"], datetime.fromisoformat(ped["dt_venda"]), ped["id"],
            Decimal(str(ped["valor_total"])), ped["fraude"], ped["motivo_fraude"] or "",
            a["uf"], a["geohash"], a["device_id"], a["dispositivo"],
            len(ped["itens"]),
            [(i["id_produto"], i["qtde"], Decimal(str(i["valor_total"]))) for i in ped["itens"]],
        ))
    print(f"  pedidos gravados ..... {len(u.pedidos):>6}")

    # ------------------------------------------------------------ sessoes
    vistas = set()
    for ev in u.eventos:
        if ev["id_sessao"] in vistas:
            continue
        vistas.add(ev["id_sessao"])
        s.execute(ins_sessao, (ev["id_sessao"], datetime.fromisoformat(ev["ts"]),
                               ev["id_pessoa"], ev["device_id"]))
    print(f"  sessoes (TTL 7d) ..... {len(vistas):>6}")

    # --------------------------------------------------------- contadores
    for (dia, tipo), total in contadores.items():
        s.execute(upd_cont, (total, dia, tipo))
    print(f"  contadores ........... {len(contadores):>6}")

    # ---------------------------------------------------------- validacao
    print("\nconferindo o que foi gravado:")
    for tab in ("eventos_por_pessoa", "eventos_por_dia", "pedidos_por_pessoa",
                "sessoes_ativas", "contador_eventos"):
        # COUNT(*) sem particao e caro. Aqui e so validacao de carga, com 3k linhas.
        c = s.execute(f"SELECT count(*) AS n FROM {tab}").one().n
        print(f"  {tab:<22} {c:>6}")

    cluster.shutdown()
    print("\n✅ Cassandra populado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
