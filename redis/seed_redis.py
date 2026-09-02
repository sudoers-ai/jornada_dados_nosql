#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Popula o Redis (paradigma CHAVE-VALOR) com o universo Liga Sudoers.

POR QUE CHAVE-VALOR AQUI?
-------------------------
A regra antifraude do repo `jornada_dados` diz: "se o cliente mudou de
dispositivo, marque como suspeito". Para aplicar essa regra NO MOMENTO do
checkout, voce precisa saber, em menos de 1 milissegundo, qual era o
dispositivo anterior daquela pessoa.

Ir ao Postgres, ao Data Lake ou ao DW para isso e inviavel: o cliente esta
esperando a tela carregar. Esse estado quente vive no Redis.

O ERRO MAIS COMUM: achar que Redis e "so cache". Aqui voce vai usar SETE
estruturas de dados diferentes, cada uma resolvendo um problema que seria
caro em qualquer outro banco:

  STRING          contadores atomicos de metrica
  HASH            carrinho e sessao (campos independentes, sem reserializar)
  LIST            ultimos pedidos da pessoa (fila com tamanho fixo)
  SET             historico de dispositivos (deduplicacao automatica)
  ZSET            ranking de produtos (ordenado, sempre)
  HYPERLOGLOG     visitantes unicos por dia usando 12KB fixos
  GEO             busca por proximidade geografica
  STREAM          fila de alertas de fraude (a ponte para o Kafka)

Uso:
    docker compose run --rm seeder python redis/seed_redis.py
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, "/app")

import redis

from comum import conectar, parametros
from gerador.liga_sudoers_gen import gerar_universo

HOST = os.getenv("REDIS_HOST", "redis")
SENHA = os.getenv("REDIS_PASS", "sudoers")
TTL_CARRINHO = 3600          # 1h: carrinho abandonado morre sozinho
TTL_SESSAO = 1800            # 30min
MAX_ULTIMOS_PEDIDOS = 10


def main() -> int:
    u = gerar_universo(**parametros())

    def _abrir():
        c = redis.Redis(host=HOST, password=SENHA, decode_responses=True,
                        socket_timeout=5)
        c.ping()
        return c

    r = conectar("Redis", _abrir)
    print(f"conectado no Redis {HOST} | semente={u.semente}")

    r.flushdb()

    pipe = r.pipeline(transaction=False)

    # ---------------------------------------------------- STRING + HASH
    # Cadastro leve da pessoa: HASH permite ler/escrever UM campo sem
    # desserializar o objeto inteiro (diferente de guardar um JSON em STRING).
    for p in u.pessoas:
        pipe.hset(f"pessoa:{p['id']}", mapping={
            "nome": p["nome"], "uf": p["uf"], "cidade": p["cidade"],
            "email": p["email"], "telefone": p["telefone"],
        })
        # <<< A REGRA ANTIFRAUDE MORA AQUI: estado quente do dispositivo
        pipe.set(f"device:atual:{p['id']}", p["device_id"])
        pipe.sadd(f"device:hist:{p['id']}", p["device_id"])
    pipe.execute()
    print(f"  pessoas (HASH) ................. {len(u.pessoas):>6}")

    # ---------------------------------------------------------- catalogo
    pipe = r.pipeline(transaction=False)
    for p in u.produtos:
        pipe.hset(f"produto:{p['id']}", mapping={
            "descricao": p["descricao"], "categoria": p["categoria"],
            "valor_unit": p["valor_unit"], "estoque": p["estoque"],
        })
    pipe.execute()
    print(f"  produtos (HASH) ................ {len(u.produtos):>6}")

    # ----------------------------------------- LIST / SET / ZSET / HLL / GEO
    vendas = defaultdict(float)
    vendas_cat = defaultdict(lambda: defaultdict(float))
    pipe = r.pipeline(transaction=False)

    for ped in u.pedidos:
        pid = ped["id_pessoa"]
        dia = ped["dt_venda"][:10]
        aud = ped["auditoria"]

        # LIST com tamanho fixo: "os ultimos N pedidos". LPUSH + LTRIM.
        pipe.lpush(f"pessoa:ultimos_pedidos:{pid}", ped["id"])
        pipe.ltrim(f"pessoa:ultimos_pedidos:{pid}", 0, MAX_ULTIMOS_PEDIDOS - 1)

        # SET: historico de dispositivos. Deduplicacao e de graca.
        pipe.sadd(f"device:hist:{pid}", aud["device_id"])

        # STRING atomico: metricas do dia. INCR nao precisa de transacao.
        pipe.incr(f"metrica:pedidos:{dia}")
        pipe.incrbyfloat(f"metrica:faturamento:{dia}", ped["valor_total"])
        if ped["fraude"]:
            pipe.incr(f"metrica:fraudes:{dia}")
            pipe.incr(f"metrica:fraude_motivo:{ped['motivo_fraude']}")

        # HYPERLOGLOG: visitantes unicos por dia em 12KB, com ~0.81% de erro.
        # Um SET com os mesmos ids custaria centenas de vezes mais memoria.
        pipe.pfadd(f"hll:visitantes:{dia}", pid)

        # GEO: o Redis indexa coordenadas nativamente (usando geohash por baixo)
        pipe.geoadd("geo:pedidos", (aud["lon"], aud["lat"], f"ped:{ped['id']}"))

        for it in ped["itens"]:
            vendas[it["id_produto"]] += it["qtde"]
            vendas_cat[it["categoria"]][it["id_produto"]] += it["qtde"]

    pipe.execute()
    print(f"  pedidos processados ............ {len(u.pedidos):>6}")

    # ZSET: ranking sempre ordenado, com leitura O(log N)
    pipe = r.pipeline(transaction=False)
    pipe.zadd("rank:produtos", {f"produto:{k}": v for k, v in vendas.items()})
    for cat, prods in vendas_cat.items():
        pipe.zadd(f"rank:categoria:{cat}", {f"produto:{k}": v for k, v in prods.items()})
    pipe.execute()
    print(f"  ranking (ZSET) ................. {r.zcard('rank:produtos'):>6}")

    # ------------------------------------------------- carrinhos vivos (TTL)
    # Estes expiram sozinhos. Nao existe job de limpeza.
    pipe = r.pipeline(transaction=False)
    abertos = 0
    for ped in u.pedidos[-120:]:
        pid = ped["id_pessoa"]
        chave = f"carrinho:{pid}"
        pipe.hset(chave, mapping={str(i["id_produto"]): i["qtde"] for i in ped["itens"]})
        pipe.expire(chave, TTL_CARRINHO)
        pipe.hset(f"sessao:tok-{ped['id']}", mapping={
            "id_pessoa": pid,
            "device_id": ped["auditoria"]["device_id"],
            "uf": ped["auditoria"]["uf"],
        })
        pipe.expire(f"sessao:tok-{ped['id']}", TTL_SESSAO)
        abertos += 1
    pipe.execute()
    print(f"  carrinhos/sessoes com TTL ...... {abertos:>6}")

    # ------------------------------------------------------------ STREAM
    # A ponte com o mundo do jornada_dados: cada fraude vira um evento numa
    # fila durável. Um consumidor leva isso para o Kafka -> MinIO.
    pipe = r.pipeline(transaction=False)
    n_alertas = 0
    for ped in u.pedidos:
        if not ped["fraude"]:
            continue
        pipe.xadd("stream:fraude", {
            "id_pedido": str(ped["id"]),
            "id_pessoa": str(ped["id_pessoa"]),
            "motivo": ped["motivo_fraude"],
            "valor": str(ped["valor_total"]),
            "device_id": ped["auditoria"]["device_id"],
            "uf": ped["auditoria"]["uf"],
            "dt_venda": ped["dt_venda"],
        })
        n_alertas += 1
    pipe.execute()
    print(f"  alertas de fraude (STREAM) ..... {n_alertas:>6}")

    info = r.info("memory")
    print(f"\n  chaves totais .................. {r.dbsize():>6}")
    print(f"  memoria usada .................. {info['used_memory_human']:>6}")
    print("\n✅ Redis populado.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
