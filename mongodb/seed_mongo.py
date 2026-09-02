#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Popula o MongoDB (paradigma DOCUMENTO) com o universo Liga Sudoers.

POR QUE DOCUMENTO AQUI?
-----------------------
Um produto da categoria "Eletronicos" tem voltagem e potencia.
Um produto da categoria "Livros" tem autor, ISBN e paginas.
Um produto da categoria "Pet" tem porte do animal e sabor.

Numa tabela relacional voce teria tres saidas, todas ruins:
  1. uma coluna para cada atributo de cada categoria (tabela com 60 colunas,
     58 delas NULL em cada linha);
  2. uma tabela EAV (entidade-atributo-valor), que destroi a legibilidade e
     exige um JOIN por atributo;
  3. um blob JSON dentro de uma coluna - ou seja, um banco de documentos
     mal-feito dentro do relacional.

No MongoDB cada produto carrega exatamente os campos que fazem sentido para
ele. E voce ainda consegue indexar e consultar dentro desses campos.

DECISAO DE MODELAGEM (a parte que realmente importa):
  - `reviews` ficam EMBUTIDAS no produto  -> leitura da pagina do produto e
    UMA busca so. Preco: o documento cresce, e MongoDB tem limite de 16MB.
  - `pedidos` guardam os itens EMBUTIDOS  -> o pedido e um agregado; voce
    nunca le "meio pedido".
  - `pessoas` sao REFERENCIADAS por id     -> mudam de forma independente.

Uso:
    docker compose run --rm seeder python mongodb/seed_mongo.py
"""
import os
import sys
from collections import defaultdict
from datetime import datetime

sys.path.insert(0, "/app")

from pymongo import MongoClient, ASCENDING, DESCENDING, TEXT
from pymongo.errors import OperationFailure

from comum import conectar, parametros
from gerador.liga_sudoers_gen import gerar_universo

MONGO_URI = os.getenv("MONGO_URI", "mongodb://sudoers:sudoers@mongodb:27017/?authSource=admin&directConnection=true")
BANCO = "liga_sudoers"
MAX_REVIEWS_EMBUTIDAS = 20   # array sem limite e antipadrao. Aqui, limite explicito.


def _dt(iso: str) -> datetime:
    return datetime.fromisoformat(iso)


def main() -> int:
    u = gerar_universo(**parametros())

    def _abrir():
        c = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        c.admin.command("ping")
        return c

    cli = conectar("MongoDB", _abrir)
    db = cli[BANCO]

    print(f"conectado em {BANCO} | semente={u.semente}")

    for c in ("produtos", "pedidos", "pessoas", "sessoes_checkout"):
        db[c].drop()

    # ---------------------------------------------------------------- produtos
    # reviews entram EMBUTIDAS dentro do proprio produto
    por_produto = defaultdict(list)
    for r in u.reviews:
        por_produto[r["id_produto"]].append(r)

    docs = []
    for p in u.produtos:
        revs = sorted(por_produto[p["id"]], key=lambda r: r["created_at"], reverse=True)
        notas = [r["nota"] for r in revs]
        docs.append({
            "_id": p["id"],
            "categoria": p["categoria"],
            "id_categoria": p["id_categoria"],
            "descricao": p["descricao"],
            "valor_unit": p["valor_unit"],
            "estoque": p["estoque"],
            "ativo": p["ativo"],
            # <<< o coracao do paradigma documento: chaves que variam por categoria
            "atributos": p["atributos"],
            "avaliacao": {
                "qtde": len(notas),
                "media": round(sum(notas) / len(notas), 2) if notas else None,
            },
            "reviews": [
                {
                    "id_pessoa": r["id_pessoa"],
                    "id_pedido": r["id_pedido"],
                    "nota": r["nota"],
                    "titulo": r["titulo"],
                    "comentario": r["comentario"],
                    "compra_verificada": r["compra_verificada"],
                    "created_at": _dt(r["created_at"]),
                }
                for r in revs[:MAX_REVIEWS_EMBUTIDAS]
            ],
        })
    db.produtos.insert_many(docs, ordered=False)
    print(f"  produtos ............ {db.produtos.count_documents({}):>6}")

    # ----------------------------------------------------------------- pessoas
    db.pessoas.insert_many([
        {
            "_id": p["id"],
            "nome": p["nome"], "sexo": p["sexo"],
            "dt_nasc": p["dt_nasc"], "cpf": p["cpf"],
            "email": p["email"], "telefone": p["telefone"],
            "endereco": {"uf": p["uf"], "cidade": p["cidade"]},
            "dispositivo_padrao": {"modelo": p["dispositivo_padrao"], "device_id": p["device_id"]},
            "created_at": _dt(p["created_at"]),
        } for p in u.pessoas
    ], ordered=False)
    print(f"  pessoas ............. {db.pessoas.count_documents({}):>6}")

    # ----------------------------------------------------------------- pedidos
    # O pedido e um AGREGADO: itens + auditoria vivem dentro dele.
    db.pedidos.insert_many([
        {
            "_id": ped["id"],
            "id_pessoa": ped["id_pessoa"],
            "dt_venda": _dt(ped["dt_venda"]),
            "valor_total": ped["valor_total"],
            "itens": ped["itens"],
            "auditoria": ped["auditoria"],
            "fraude": ped["fraude"],
            "motivo_fraude": ped["motivo_fraude"],
        } for ped in u.pedidos
    ], ordered=False)
    print(f"  pedidos ............. {db.pedidos.count_documents({}):>6}")

    # -------------------------------------------------------- sessoes_checkout
    # Documento de vida curta, com TTL: o Mongo apaga sozinho depois de 7 dias.
    db.sessoes_checkout.insert_many([
        {
            "_id": f"chk-{ped['id']}",
            "id_pessoa": ped["id_pessoa"],
            "status": "concluida",
            "dispositivo": ped["auditoria"]["dispositivo"],
            "device_id": ped["auditoria"]["device_id"],
            "geohash": ped["auditoria"]["geohash"],
            "itens": [{"id_produto": i["id_produto"], "qtde": i["qtde"]} for i in ped["itens"]],
            "created_at": _dt(ped["dt_venda"]),
        } for ped in u.pedidos[-500:]
    ], ordered=False)
    print(f"  sessoes_checkout .... {db.sessoes_checkout.count_documents({}):>6}")

    # ----------------------------------------------------------------- indices
    print("\ncriando indices...")
    db.produtos.create_index([("categoria", ASCENDING)], name="ix_categoria")
    db.produtos.create_index([("valor_unit", ASCENDING)], name="ix_preco")
    db.produtos.create_index([("avaliacao.media", DESCENDING)], name="ix_nota")
    # indice em campo que SO existe em algumas categorias: indice esparso
    db.produtos.create_index([("atributos.voltagem", ASCENDING)], name="ix_voltagem", sparse=True)
    db.produtos.create_index([("atributos.autor", ASCENDING)], name="ix_autor", sparse=True)
    # busca textual dentro dos comentarios embutidos
    db.produtos.create_index([("reviews.comentario", TEXT)], name="ix_texto_review",
                             default_language="portuguese")

    db.pedidos.create_index([("id_pessoa", ASCENDING), ("dt_venda", DESCENDING)], name="ix_pessoa_data")
    db.pedidos.create_index([("fraude", ASCENDING), ("motivo_fraude", ASCENDING)], name="ix_fraude")
    db.pedidos.create_index([("auditoria.device_id", ASCENDING)], name="ix_device")
    db.pedidos.create_index([("auditoria.uf", ASCENDING)], name="ix_uf")

    db.pessoas.create_index([("endereco.uf", ASCENDING)], name="ix_uf_pessoa")
    db.pessoas.create_index([("cpf", ASCENDING)], name="ix_cpf", unique=True)

    # TTL: documento morre sozinho 7 dias depois de criado
    db.sessoes_checkout.create_index([("created_at", ASCENDING)], name="ttl_7d",
                                     expireAfterSeconds=7 * 24 * 3600)

    # -------------------------------------------------- validacao de schema
    # "NoSQL nao tem schema" e mito. Voce escolhe ONDE colocar o schema.
    try:
        db.command({
            "collMod": "pedidos",
            "validator": {"$jsonSchema": {
                "bsonType": "object",
                "required": ["id_pessoa", "dt_venda", "valor_total", "itens"],
                "properties": {
                    "id_pessoa": {"bsonType": "int"},
                    "valor_total": {"bsonType": "double", "minimum": 0},
                    "itens": {"bsonType": "array", "minItems": 1},
                },
            }},
            "validationLevel": "moderate",
        })
        print("  validacao $jsonSchema aplicada em `pedidos`")
    except OperationFailure as e:
        print(f"  aviso: validacao nao aplicada ({e})")

    idx = sum(len(list(db[c].list_indexes())) for c in ("produtos", "pedidos", "pessoas", "sessoes_checkout"))
    print(f"  indices totais ...... {idx:>6}")
    print("\n✅ MongoDB populado.")
    cli.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
