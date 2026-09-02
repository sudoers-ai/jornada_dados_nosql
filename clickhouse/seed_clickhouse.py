#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Popula o ClickHouse (COLUNAR ANALITICO) com o universo Liga Sudoers.

QUAL O PAPEL DELE NA ARQUITETURA?
---------------------------------
Os outros quatro bancos deste repo sao ORIGENS: eles atendem a aplicacao,
cada um resolvendo um problema operacional.

O ClickHouse e o oposto: e o DESTINO. E a camada onde a pergunta de negocio
e respondida - "qual o faturamento por UF por dia?", "qual a taxa de fraude
por categoria?". E e ele que alimenta o dashboard.

Na arquitetura do jornada_dados, ele ocupa o mesmo lugar do PostgreSQL OLAP
(star schema) - com uma diferenca: agrega ordens de magnitude mais rapido,
porque le colunas em vez de linhas.

Uso:
    docker compose run --rm seeder python clickhouse/seed_clickhouse.py
"""
import os
import sys
from datetime import datetime

sys.path.insert(0, "/app")

import clickhouse_connect

from comum import conectar, parametros
from gerador.liga_sudoers_gen import gerar_universo

HOST = os.getenv("CLICKHOUSE_HOST", "clickhouse")
USER = os.getenv("CLICKHOUSE_USER", "sudoers")
SENHA = os.getenv("CLICKHOUSE_PASS", "sudoers")
BANCO = "liga_sudoers"


def aplicar_schema(cli, caminho: str) -> None:
    with open(caminho, encoding="utf-8") as fh:
        bruto = fh.read()
    limpo = "\n".join(l for l in bruto.splitlines() if not l.strip().startswith("--"))
    for cmd in (c.strip() for c in limpo.split(";")):
        if cmd:
            cli.command(cmd)


def main() -> int:
    u = gerar_universo(**parametros())

    def _abrir():
        c = clickhouse_connect.get_client(host=HOST, username=USER,
                                          password=SENHA, connect_timeout=5)
        c.query("SELECT 1")
        return c

    cli = conectar("ClickHouse", _abrir)
    print(f"conectado no ClickHouse {HOST} | versao {cli.server_version} | semente={u.semente}")

    aplicar_schema(cli, "/app/clickhouse/schema.sql")
    print("  schema aplicado (4 tabelas + 1 MV)")

    # ------------------------------------------------------------- dimensoes
    cli.insert(f"{BANCO}.dim_pessoas", [
        [p["id"], p["nome"], p["sexo"], datetime.fromisoformat(p["dt_nasc"]).date(),
         p["cpf"], p["email"], p["uf"], p["cidade"], p["device_id"], p["dispositivo_padrao"]]
        for p in u.pessoas
    ], column_names=["id_pessoa", "nome", "sexo", "dt_nasc", "cpf", "email",
                     "uf", "cidade", "device_id", "dispositivo"])
    print(f"  dim_pessoas .......... {len(u.pessoas):>6}")

    cli.insert(f"{BANCO}.dim_produtos", [
        [p["id"], p["descricao"], p["categoria"], p["valor_unit"], p["estoque"], int(p["ativo"])]
        for p in u.produtos
    ], column_names=["id_produto", "descricao", "categoria", "valor_unit", "estoque", "ativo"])
    print(f"  dim_produtos ......... {len(u.produtos):>6}")

    # ------------------------------------------------------------------ fatos
    # A MV mv_vendas_dia dispara AUTOMATICAMENTE neste insert.
    cli.insert(f"{BANCO}.fato_pedidos", [
        [ped["id"], ped["id_pessoa"], datetime.fromisoformat(ped["dt_venda"]),
         ped["valor_total"], len(ped["itens"]), int(ped["fraude"]),
         ped["motivo_fraude"] or "", ped["auditoria"]["uf"], ped["auditoria"]["geohash"],
         ped["auditoria"]["lat"], ped["auditoria"]["lon"], ped["auditoria"]["device_id"],
         ped["auditoria"]["dispositivo"], ped["auditoria"]["telefone"]]
        for ped in u.pedidos
    ], column_names=["id_pedido", "id_pessoa", "dt_venda", "valor_total", "qtd_itens",
                     "fraude", "motivo_fraude", "uf", "geohash", "lat", "lon",
                     "device_id", "dispositivo", "telefone"])
    print(f"  fato_pedidos ......... {len(u.pedidos):>6}")

    itens = []
    for ped in u.pedidos:
        dt = datetime.fromisoformat(ped["dt_venda"])
        for it in ped["itens"]:
            itens.append([ped["id"], ped["id_pessoa"], dt, it["id_produto"],
                          it["categoria"], it["qtde"], it["valor_unit"],
                          it["valor_total"], int(ped["fraude"]), ped["auditoria"]["uf"]])
    cli.insert(f"{BANCO}.fato_itens", itens,
               column_names=["id_pedido", "id_pessoa", "dt_venda", "id_produto", "categoria",
                             "qtde", "valor_unit", "valor_total", "fraude", "uf"])
    print(f"  fato_itens ........... {len(itens):>6}")

    cli.insert(f"{BANCO}.eventos", [
        [e["id_pessoa"], datetime.fromisoformat(e["ts"]), e["tipo_evento"], e["id_produto"],
         e["categoria"], e["id_sessao"], e["device_id"], e["geohash"], e["duracao_ms"]]
        for e in u.eventos
    ], column_names=["id_pessoa", "ts", "tipo_evento", "id_produto", "categoria",
                     "id_sessao", "device_id", "geohash", "duracao_ms"])
    print(f"  eventos .............. {len(u.eventos):>6}")

    # ------------------------------------------------------------- validacao
    print("\nconferindo:")
    mv = cli.query(f"SELECT count() FROM {BANCO}.agg_vendas_dia").result_rows[0][0]
    print(f"  agg_vendas_dia (MV preenchida sozinha) .. {mv}")

    # system.parts (nao system.columns): so os "parts" ativos conhecem o
    # tamanho real em disco depois da compressao.
    comp = cli.query(f"""
        SELECT
            formatReadableSize(sum(data_uncompressed_bytes)) AS cru,
            formatReadableSize(sum(data_compressed_bytes))   AS comprimido,
            round(sum(data_uncompressed_bytes) / sum(data_compressed_bytes), 1) AS fator
        FROM system.parts WHERE database = '{BANCO}' AND active
    """).result_rows[0]
    print(f"  tamanho cru ............................. {comp[0]}")
    print(f"  tamanho comprimido ...................... {comp[1]}")
    print(f"  fator de compressao ..................... {comp[2]}x")

    print("\n✅ ClickHouse populado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
