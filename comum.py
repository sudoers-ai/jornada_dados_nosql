# -*- coding: utf-8 -*-
"""
Utilidades compartilhadas pelos seeds.

Existe por um motivo so: quando o aluno roda o seed antes de o banco
terminar de subir, ele NAO pode receber um traceback de 30 linhas. Ele
precisa receber "esperando o Cassandra... (12s)" e, se falhar mesmo, uma
mensagem que diga exatamente o que fazer.
"""
import os
import sys
import time

V, A, R, C, F = "\033[92m", "\033[93m", "\033[91m", "\033[90m", "\033[0m"

# Quanto esperar cada banco. O Cassandra e disparado o mais lento para subir.
LIMITES = {
    "MongoDB": 90,
    "Redis": 30,
    "Neo4j": 120,
    "Cassandra": 300,
    "ClickHouse": 90,
    "PostgreSQL": 60,
    "MinIO": 60,
}

# banco -> (profile do compose, nome do servico)
AJUDA = {
    "MongoDB":    ("documento",  "mongodb"),
    "Redis":      ("chavevalor", "redis"),
    "Neo4j":      ("grafo",      "neo4j"),
    "Cassandra":  ("widecolumn", "cassandra"),
    "ClickHouse": ("colunar",    "clickhouse"),
}


def conectar(banco, tentar, limite=None):
    """Tenta conectar ate dar certo ou estourar o tempo.

    `tentar` e uma funcao sem argumentos que conecta e devolve o cliente.
    Qualquer excecao dela e tratada como "ainda nao esta pronto".
    """
    limite = limite or LIMITES.get(banco, 90)
    inicio = time.time()
    ultimo_erro = None
    avisou = False

    while time.time() - inicio < limite:
        try:
            cliente = tentar()
            if avisou:
                print("\r  %s✅%s %s respondeu depois de %ds%s"
                      % (V, F, banco, int(time.time() - inicio), " " * 20))
            return cliente
        except Exception as e:                       # noqa: BLE001
            ultimo_erro = e
            if not avisou:
                print("  %s⏳%s %s ainda nao esta pronto. Esperando (ate %ds)..."
                      % (A, F, banco, limite), flush=True)
                avisou = True
            print("\r     %s%ds%s" % (C, int(time.time() - inicio), F),
                  end="", flush=True)
            time.sleep(3)

    # ------------------------------------------------ desistiu: explique bem
    print("\r%s\r" % (" " * 40), end="")
    print("\n  %s❌ Nao consegui falar com o %s em %ds.%s\n" % (R, banco, limite, F))
    perfil, servico = AJUDA.get(banco, (None, None))
    print("  %sO que costuma ser:%s" % (C, F))
    if perfil:
        print("    1. o banco nao esta no ar. Suba com:")
        print("         docker compose --profile %s up -d" % perfil)
        print("    2. ele ainda esta subindo. Veja o estado:")
        print("         make status")
        print("    3. ele subiu com erro. Veja o log:")
        print("         make logs s=%s" % servico)
    else:
        print("    1. o servico do jornada_dados nao esta no ar")
        print("    2. voce esqueceu o overlay de rede:")
        print("         -f docker-compose.yml -f docker-compose.lake.yml")
    print("\n  %sDetalhe tecnico: %s: %s%s\n"
          % (C, type(ultimo_erro).__name__, str(ultimo_erro)[:160], F))
    sys.exit(1)


def parametros():
    """Tamanho do universo, lido do ambiente com os mesmos padroes do .env."""
    return dict(
        semente=int(os.getenv("SEMENTE", 42)),
        n_pessoas=int(os.getenv("N_PESSOAS", 500)),
        n_produtos=int(os.getenv("N_PRODUTOS", 200)),
        n_pedidos=int(os.getenv("N_PEDIDOS", 5000)),
    )
