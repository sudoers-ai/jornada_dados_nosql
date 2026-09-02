#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Popula o Neo4j (paradigma GRAFO) com o universo Liga Sudoers.

POR QUE GRAFO AQUI?
-------------------
No repo `jornada_dados` a fraude e detectada por REGRA de linha: "esse pedido
saiu de fora de SP/MG/RJ" ou "essa pessoa trocou de celular". Sao regras que
olham UM registro por vez.

Existe um terceiro tipo de fraude que nenhuma regra de linha pega: o ANEL.
Cinco contas diferentes, cinco CPFs diferentes, cinco nomes diferentes,
todas comprando de dentro de SP, todas com o "seu" celular de sempre. Cada
pedido, isolado, e perfeitamente normal. O que denuncia o grupo e a LIGACAO
entre eles: e o MESMO aparelho fisico e o MESMO telefone.

Em SQL isso vira self-join sobre self-join, e piora exponencialmente a cada
salto que voce quer dar ("e quem comprou junto com quem usou esse aparelho?").
Em Cypher e um desenho: (a)-[:USOU]->(d)<-[:USOU]-(b).

MODELO DO GRAFO
---------------
  (:Pessoa)-[:FEZ]->(:Pedido)-[:CONTEM]->(:Produto)-[:PERTENCE_A]->(:Categoria)
  (:Pedido)-[:USOU]->(:Dispositivo)
  (:Pedido)-[:VIA_TELEFONE]->(:Telefone)
  (:Pedido)-[:ORIGINADO_EM]->(:Local)
  (:Pessoa)-[:DISPOSITIVO_PADRAO]->(:Dispositivo)

Repare: `Dispositivo`, `Telefone` e `Local` viram NOS, nao colunas. Essa e a
decisao de modelagem inteira. Como no, eles podem ser compartilhados - e o
compartilhamento e exatamente o que queremos enxergar.

Uso:
    docker compose run --rm seeder python neo4j/seed_neo4j.py
"""
import os
import sys

sys.path.insert(0, "/app")

from neo4j import GraphDatabase

from gerador.liga_sudoers_gen import gerar_universo

URI = os.getenv("NEO4J_URI", "bolt://neo4j:7687")
USER = os.getenv("NEO4J_USER", "neo4j")
PASS = os.getenv("NEO4J_PASS", "sudoers123")
LOTE = 1000


def em_lotes(seq, n=LOTE):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def main() -> int:
    u = gerar_universo(
        semente=int(os.getenv("SEMENTE", 42)),
        n_pessoas=int(os.getenv("N_PESSOAS", 500)),
        n_produtos=int(os.getenv("N_PRODUTOS", 200)),
        n_pedidos=int(os.getenv("N_PEDIDOS", 5000)),
    )

    drv = GraphDatabase.driver(URI, auth=(USER, PASS))
    drv.verify_connectivity()
    print(f"conectado no Neo4j {URI} | semente={u.semente}")

    with drv.session() as s:
        s.run("MATCH (n) DETACH DELETE n")

        # Constraints tambem criam indice. Sem isso o MERGE fica lentissimo.
        for c in (
            "CREATE CONSTRAINT pessoa_id IF NOT EXISTS FOR (p:Pessoa) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT produto_id IF NOT EXISTS FOR (p:Produto) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT pedido_id IF NOT EXISTS FOR (p:Pedido) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT categoria_id IF NOT EXISTS FOR (c:Categoria) REQUIRE c.id IS UNIQUE",
            "CREATE CONSTRAINT device_id IF NOT EXISTS FOR (d:Dispositivo) REQUIRE d.device_id IS UNIQUE",
            "CREATE CONSTRAINT telefone_num IF NOT EXISTS FOR (t:Telefone) REQUIRE t.numero IS UNIQUE",
            "CREATE CONSTRAINT local_gh IF NOT EXISTS FOR (l:Local) REQUIRE l.geohash IS UNIQUE",
        ):
            s.run(c)
        print("  constraints/indices criados")

        # ------------------------------------------------------------- nos
        s.run("""
            UNWIND $rows AS r
            CREATE (:Categoria {id: r.id, nome: r.descricao})
        """, rows=u.categorias)
        print(f"  (:Categoria) ......... {len(u.categorias):>6}")

        for lote in em_lotes(u.produtos):
            s.run("""
                UNWIND $rows AS r
                CREATE (p:Produto {id: r.id, descricao: r.descricao, valor_unit: r.valor_unit})
                WITH p, r
                MATCH (c:Categoria {id: r.id_categoria})
                CREATE (p)-[:PERTENCE_A]->(c)
            """, rows=lote)
        print(f"  (:Produto) ........... {len(u.produtos):>6}")

        for lote in em_lotes(u.pessoas):
            s.run("""
                UNWIND $rows AS r
                CREATE (p:Pessoa {id: r.id, nome: r.nome, sexo: r.sexo, cpf: r.cpf,
                                  email: r.email, uf: r.uf, cidade: r.cidade})
                WITH p, r
                MERGE (d:Dispositivo {device_id: r.device_id})
                  ON CREATE SET d.modelo = r.dispositivo_padrao
                MERGE (p)-[:DISPOSITIVO_PADRAO]->(d)
                WITH p, r
                MERGE (t:Telefone {numero: r.telefone})
                MERGE (p)-[:TEM_TELEFONE]->(t)
            """, rows=lote)
        print(f"  (:Pessoa) ............ {len(u.pessoas):>6}")

        # -------------------------------------------- pedidos e suas arestas
        # Aqui nasce toda a estrutura que revela os aneis.
        linhas = [{
            "id": p["id"], "id_pessoa": p["id_pessoa"], "dt_venda": p["dt_venda"],
            "valor_total": p["valor_total"], "fraude": p["fraude"],
            "motivo": p["motivo_fraude"] or "",
            "device_id": p["auditoria"]["device_id"],
            "modelo": p["auditoria"]["dispositivo"],
            "telefone": p["auditoria"]["telefone"],
            # DECISAO DE MODELAGEM: cortamos o geohash em 5 caracteres.
            # Com 7 (~150m) cada pedido virava um Local unico e o no nao
            # conectava nada. Com 5 (~5km) varios pedidos compartilham o
            # mesmo Local - e ai o no passa a ter utilidade no grafo.
            "geohash": p["auditoria"]["geohash"][:5], "uf": p["auditoria"]["uf"],
            "lat": p["auditoria"]["lat"], "lon": p["auditoria"]["lon"],
            "itens": p["itens"],
        } for p in u.pedidos]

        for lote in em_lotes(linhas, 500):
            s.run("""
                UNWIND $rows AS r
                MATCH (pes:Pessoa {id: r.id_pessoa})
                CREATE (ped:Pedido {id: r.id, dt_venda: datetime(r.dt_venda),
                                    valor_total: r.valor_total,
                                    fraude: r.fraude, motivo: r.motivo})
                CREATE (pes)-[:FEZ]->(ped)

                MERGE (d:Dispositivo {device_id: r.device_id})
                  ON CREATE SET d.modelo = r.modelo
                CREATE (ped)-[:USOU]->(d)

                MERGE (t:Telefone {numero: r.telefone})
                CREATE (ped)-[:VIA_TELEFONE]->(t)

                MERGE (l:Local {geohash: r.geohash})
                  ON CREATE SET l.uf = r.uf, l.lat = r.lat, l.lon = r.lon
                CREATE (ped)-[:ORIGINADO_EM]->(l)

                WITH ped, r
                UNWIND r.itens AS it
                MATCH (prod:Produto {id: it.id_produto})
                CREATE (ped)-[:CONTEM {qtde: it.qtde, valor_total: it.valor_total}]->(prod)
            """, rows=lote)
        print(f"  (:Pedido) ............ {len(u.pedidos):>6}")

        # ---------------------------------------------------------- resumo
        r = s.run("""
            MATCH (n) WITH count(n) AS nos
            MATCH ()-[r]->() RETURN nos, count(r) AS arestas
        """).single()
        print(f"\n  nos totais ........... {r['nos']:>6}")
        print(f"  arestas totais ....... {r['arestas']:>6}")

        det = s.run("""
            MATCH (d:Dispositivo)<-[:USOU]-(:Pedido)<-[:FEZ]-(p:Pessoa)
            WITH d, count(DISTINCT p) AS donos
            WHERE donos > 1
            RETURN count(d) AS aneis
        """).single()
        print(f"  dispositivos compartilhados (aneis): {det['aneis']}")
        print(f"  esperado pelo gerador .............. {len(u.aneis_fraude)}")

    drv.close()
    print("\n✅ Neo4j populado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
