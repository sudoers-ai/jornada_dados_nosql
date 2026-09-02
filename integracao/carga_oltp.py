#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Carrega o universo Liga Sudoers no PostgreSQL OLTP do repo `jornada_dados`.

ESTE E O SCRIPT QUE FECHA O CIRCUITO ENTRE OS DOIS REPOSITORIOS.
----------------------------------------------------------------
O repo `jornada_dados` cita um `liga_sudoers_historico.py` que popula o
Postgres transacional, mas esse script nunca foi versionado la. Aqui ele
existe - e melhor: ele usa a MESMA semente que popula o Mongo, o Redis,
o Neo4j, o Cassandra e o ClickHouse.

Resultado: `pessoas.id = 1` no Postgres e a MESMA pessoa que o `_id: 1` do
Mongo e o `(:Pessoa {id: 1})` do Neo4j. Sem isso, os dois repos seriam dois
mundos paralelos e nenhum exercicio de cruzamento faria sentido.

E a partir daqui o pipeline do outro repo roda sozinho:
    Postgres -> Debezium -> Kafka -> Spark -> Delta Lake -> DW

Uso:
    # 1) confira o que seria feito (nao escreve nada)
    docker compose -f docker-compose.yml -f docker-compose.lake.yml \
      run --rm seeder python integracao/carga_oltp.py

    # 2) carregue de verdade (APAGA os dados atuais das 6 tabelas)
    docker compose -f docker-compose.yml -f docker-compose.lake.yml \
      run --rm seeder python integracao/carga_oltp.py --limpar
"""
import argparse
import io
import os
import sys

sys.path.insert(0, "/app")

import psycopg2

from gerador.liga_sudoers_gen import gerar_universo

TABELAS = ("auditoria_pedidos", "itens_pedidos", "pedidos", "produtos", "categorias", "pessoas")


def copiar(cur, tabela: str, colunas: list, linhas) -> int:
    """COPY e ordens de magnitude mais rapido que INSERT linha a linha."""
    buf = io.StringIO()
    n = 0
    for linha in linhas:
        buf.write("\t".join("\\N" if v is None else str(v).replace("\t", " ").replace("\n", " ")
                            for v in linha))
        buf.write("\n")
        n += 1
    buf.seek(0)
    cur.copy_expert(f"COPY public.{tabela} ({', '.join(colunas)}) FROM STDIN", buf)
    return n


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limpar", action="store_true",
                    help="TRUNCATE nas 6 tabelas antes de carregar")
    ap.add_argument("--host", default=os.getenv("OLTP_HOST", "postgres-oltp"))
    ap.add_argument("--banco", default=os.getenv("OLTP_DB", "liga_sudoers"))
    ap.add_argument("--usuario", default=os.getenv("OLTP_USER", "sudoers"))
    ap.add_argument("--senha", default=os.getenv("OLTP_PASS", "sudoers"))
    args = ap.parse_args()

    u = gerar_universo(
        semente=int(os.getenv("SEMENTE", 42)),
        n_pessoas=int(os.getenv("N_PESSOAS", 500)),
        n_produtos=int(os.getenv("N_PRODUTOS", 200)),
        n_pedidos=int(os.getenv("N_PEDIDOS", 5000)),
    )

    try:
        con = psycopg2.connect(host=args.host, dbname=args.banco,
                               user=args.usuario, password=args.senha, connect_timeout=15)
    except psycopg2.OperationalError as e:
        print(f"❌ Nao consegui falar com o Postgres em '{args.host}'.\n   {e}")
        print("\n   Checklist:")
        print("     1. o repo jornada_dados esta rodando?  (docker compose up -d postgres-oltp)")
        print("     2. voce usou o overlay?  -f docker-compose.yml -f docker-compose.lake.yml")
        return 1

    con.autocommit = False
    cur = con.cursor()
    print(f"conectado em {args.host}/{args.banco} | semente={u.semente}")

    cur.execute("""SELECT table_name FROM information_schema.tables
                   WHERE table_schema='public' AND table_name = ANY(%s)""", (list(TABELAS),))
    achadas = {r[0] for r in cur.fetchall()}
    faltando = set(TABELAS) - achadas
    if faltando:
        print(f"❌ Faltam tabelas no destino: {sorted(faltando)}")
        print("   Este script espera o schema de postgresql-init/oltp.sql do jornada_dados.")
        return 1

    print("\nsituacao atual do destino:")
    atuais = {}
    for t in TABELAS:
        cur.execute(f"SELECT count(*) FROM public.{t}")
        atuais[t] = cur.fetchone()[0]
        print(f"  {t:<20} {atuais[t]:>8}")

    if not args.limpar:
        if any(atuais.values()):
            print("\n⚠️  As tabelas TEM dados. Nada foi alterado.")
            print("   Para substituir pelo universo canonico, rode de novo com --limpar")
            return 0
        print("\n  (tabelas vazias, seguindo com a carga)")
    else:
        print("\nlimpando (TRUNCATE ... CASCADE)...")
        cur.execute("TRUNCATE TABLE " + ", ".join(f"public.{t}" for t in TABELAS) + " CASCADE")

    print("\ncarregando:")
    n = copiar(cur, "categorias", ["id", "descricao"],
               ((c["id"], c["descricao"]) for c in u.categorias))
    print(f"  categorias .......... {n:>6}")

    n = copiar(cur, "produtos", ["id", "id_categoria", "descricao", "valor_unit"],
               ((p["id"], p["id_categoria"], p["descricao"], p["valor_unit"]) for p in u.produtos))
    print(f"  produtos ............ {n:>6}")

    n = copiar(cur, "pessoas", ["id", "nome", "sexo", "dt_nasc"],
               ((p["id"], p["nome"], p["sexo"], p["dt_nasc"]) for p in u.pessoas))
    print(f"  pessoas ............. {n:>6}")

    n = copiar(cur, "pedidos", ["id", "id_pessoa", "dt_venda", "valor_total"],
               ((p["id"], p["id_pessoa"], p["dt_venda"], p["valor_total"]) for p in u.pedidos))
    print(f"  pedidos ............. {n:>6}")

    n = copiar(cur, "itens_pedidos", ["id_pedido", "id_produto", "qtde", "valor_total"],
               ((ped["id"], it["id_produto"], it["qtde"], it["valor_total"])
                for ped in u.pedidos for it in ped["itens"]))
    print(f"  itens_pedidos ....... {n:>6}")

    # auditoria_pedidos e a tabela que o antifraude do jornada_dados le
    n = copiar(cur, "auditoria_pedidos", ["id_pedido", "dispositivo", "geohash", "telefone"],
               ((ped["id"], ped["auditoria"]["dispositivo"], ped["auditoria"]["geohash"],
                 ped["auditoria"]["telefone"]) for ped in u.pedidos))
    print(f"  auditoria_pedidos ... {n:>6}")

    con.commit()

    print("\nconferindo o destino:")
    for t in TABELAS:
        cur.execute(f"SELECT count(*) FROM public.{t}")
        print(f"  {t:<20} {cur.fetchone()[0]:>8}")

    # prova de que os ids batem com os outros bancos
    cur.execute("SELECT id, nome FROM public.pessoas WHERE id = 1")
    p1 = cur.fetchone()
    print(f"\n  pessoa id=1 no Postgres: {p1[1]}")
    print(f"  pessoa id=1 no gerador : {u.pessoas[0]['nome']}")
    print("  ^ tem que ser a MESMA pessoa. Se bater, os dois repos estao alinhados.")

    cur.close()
    con.close()
    print("\n✅ OLTP carregado. Agora o pipeline do jornada_dados pode rodar:")
    print("   Debezium -> Kafka -> Spark -> Delta Lake -> DW")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
