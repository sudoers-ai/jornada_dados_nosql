# -*- coding: utf-8 -*-
"""
Gerador canonico do universo Liga Sudoers.

Este e o CORACAO do repositorio. Todos os bancos (MongoDB, Redis, Neo4j,
Cassandra, ClickHouse) e tambem o PostgreSQL do repo `jornada_dados` sao
populados a partir DESTE gerador, com a MESMA semente.

Consequencia pratica: `pessoa.id = 1` e a MESMA pessoa em todos os bancos.
E isso que permite ao aluno cruzar dados entre paradigmas no Data Lake.

Uso:
    python liga_sudoers_gen.py --formato json --saida ./saida
    python liga_sudoers_gen.py --formato sql  --saida ./saida
    python liga_sudoers_gen.py --resumo

Como biblioteca:
    from liga_sudoers_gen import gerar_universo
    u = gerar_universo()
    u.pessoas, u.produtos, u.pedidos, u.eventos, u.reviews
"""
from __future__ import annotations

import argparse
import json
import os
import random
from dataclasses import dataclass, field, asdict
from datetime import datetime, timedelta, date

try:
    from faker import Faker
except ImportError:  # pragma: no cover
    raise SystemExit("Faltou a lib Faker. Rode: pip install -r requirements.txt")

# --------------------------------------------------------------------------
# Parametros do universo (mude aqui e TODOS os bancos mudam juntos)
# --------------------------------------------------------------------------
SEMENTE = 42
N_PESSOAS = 500
N_PRODUTOS = 200
N_PEDIDOS = 5000
N_EVENTOS_POR_PESSOA = 12          # clickstream -> Cassandra
TAXA_REVIEW = 0.30                 # 30% dos pedidos viram review -> MongoDB
DIAS_HISTORICO = 180

# Regras de fraude (identicas as do repo jornada_dados)
TAXA_FRAUDE_GEO = 0.010            # 1% - compra fora de SP/MG/RJ
TAXA_FRAUDE_DEVICE = 0.015         # 1.5% - troca de dispositivo
N_ANEIS_FRAUDE = 6                 # aneis: varias contas no MESMO device/telefone
TAM_ANEL = 5                       # pessoas por anel

UF_LEGITIMAS = ("SP", "MG", "RJ")

# Capitais usadas para gerar geohash realista
UF_COORD = {
    "SP": (-23.5505, -46.6333),
    "MG": (-19.9167, -43.9345),
    "RJ": (-22.9068, -43.1729),
    "BA": (-12.9777, -38.5016),
    "AM": (-3.1190, -60.0217),
    "RS": (-30.0346, -51.2177),
    "PE": (-8.0476, -34.8770),
    "CE": (-3.7172, -38.5433),
    "DF": (-15.7939, -47.8828),
    "PR": (-25.4284, -49.2733),
}
UF_SUSPEITAS = tuple(uf for uf in UF_COORD if uf not in UF_LEGITIMAS)

MODELOS_DISPOSITIVO = (
    "iPhone 13", "iPhone 15", "Samsung Galaxy S23", "Samsung Galaxy A54",
    "Motorola Edge 40", "Xiaomi Redmi Note 12", "Web Chrome", "Web Firefox",
    "iPad Air", "Pixel 8",
)

# Categorias fixas + os atributos que SO existem naquela categoria.
# E exatamente isso que justifica o MongoDB: schema rigido nao acomodaria.
CATEGORIAS = {
    1:  ("Eletronicos",   ["voltagem", "garantia_meses", "potencia_w"]),
    2:  ("Vestuario",     ["tamanho", "cor", "composicao"]),
    3:  ("Livros",        ["autor", "paginas", "isbn", "editora"]),
    4:  ("Alimentos",     ["peso_g", "validade_dias", "organico"]),
    5:  ("Moveis",        ["material", "altura_cm", "largura_cm", "montagem"]),
    6:  ("Informatica",   ["garantia_meses", "interface", "capacidade_gb"]),
    7:  ("Beleza",        ["volume_ml", "tipo_pele", "vegano"]),
    8:  ("Esportes",      ["modalidade", "tamanho", "material"]),
    9:  ("Brinquedos",    ["idade_min", "pilhas", "material"]),
    10: ("Ferramentas",   ["potencia_w", "voltagem", "garantia_meses"]),
    11: ("Automotivo",    ["compatibilidade", "material", "garantia_meses"]),
    12: ("Pet",           ["porte_animal", "peso_g", "sabor"]),
}

TIPOS_EVENTO = ("page_view", "busca", "ver_produto", "add_carrinho",
                "remove_carrinho", "checkout", "compra")

# Reviews em portugues de verdade (nada de lorem ipsum): sem isso a busca
# textual e a analise de sentimento nao tem o que encontrar.
FRASES_REVIEW = {
    5: ["Produto excelente, superou minhas expectativas.",
        "Entrega rapida e produto de otima qualidade.",
        "Recomendo demais, custo beneficio imbativel.",
        "Perfeito, exatamente como descrito no anuncio.",
        "Melhor compra que fiz esse ano, qualidade impecavel."],
    4: ["Bom produto, entrega dentro do prazo.",
        "Gostei bastante, so a embalagem que veio amassada.",
        "Atende bem ao que promete, recomendo.",
        "Qualidade boa pelo preco pago.",
        "Produto bom, mas o manual poderia ser mais claro."],
    3: ["Produto mediano, nada excepcional.",
        "Cumpre o basico, mas esperava mais pelo preco.",
        "Entrega demorou, produto e razoavel.",
        "Serve, mas o acabamento deixa a desejar.",
        "Nem bom nem ruim, e o que da pra pagar."],
    2: ["Produto fraco, qualidade abaixo do esperado.",
        "Chegou com defeito, tive que acionar a garantia.",
        "Nao recomendo, material muito fragil.",
        "Demorou muito para chegar e veio errado.",
        "Decepcionante, a foto nao corresponde ao produto."],
    1: ["Pessimo, nao funcionou de jeito nenhum.",
        "Produto quebrou no primeiro uso, dinheiro jogado fora.",
        "Nunca chegou, tive que pedir reembolso.",
        "Horrivel, propaganda enganosa total.",
        "Pior compra da minha vida, fujam desse produto."],
}

TITULOS_REVIEW = {
    5: ["Excelente!", "Muito satisfeito", "Recomendo", "Nota 10", "Perfeito"],
    4: ["Bom produto", "Gostei", "Vale a pena", "Cumpre o prometido", "Satisfeito"],
    3: ["Razoavel", "Mediano", "Da pro gasto", "Esperava mais", "Ok"],
    2: ["Deixou a desejar", "Nao gostei", "Fraco", "Problemas na entrega", "Decepcionou"],
    1: ["Pessimo", "Nao comprem", "Terrivel", "Dinheiro perdido", "Fuja"],
}

_BASE32 = "0123456789bcdefghjkmnpqrstuvwxyz"


def geohash_encode(lat: float, lon: float, precisao: int = 7) -> str:
    """Codifica lat/lon em geohash. Implementacao propria para nao criar
    dependencia externa - e ~25 linhas e ensina o algoritmo."""
    lat_int = (-90.0, 90.0)
    lon_int = (-180.0, 180.0)
    gh, bits, bit, par = [], 0, 0, True
    while len(gh) < precisao:
        if par:
            meio = (lon_int[0] + lon_int[1]) / 2
            if lon > meio:
                bits = bits * 2 + 1
                lon_int = (meio, lon_int[1])
            else:
                bits = bits * 2
                lon_int = (lon_int[0], meio)
        else:
            meio = (lat_int[0] + lat_int[1]) / 2
            if lat > meio:
                bits = bits * 2 + 1
                lat_int = (meio, lat_int[1])
            else:
                bits = bits * 2
                lat_int = (lat_int[0], meio)
        par = not par
        bit += 1
        if bit == 5:
            gh.append(_BASE32[bits])
            bits, bit = 0, 0
    return "".join(gh)


# Prefixo de 3 caracteres do geohash da capital de cada UF.
# A regra antifraude do repo jornada_dados classifica pela REGIAO do geohash,
# entao esse prefixo precisa ser estavel: um pedido legitimo de SP nao pode
# cair num prefixo diferente so por causa do sorteio de coordenada.
PREFIXO_UF = {uf: geohash_encode(lat, lon)[:3] for uf, (lat, lon) in UF_COORD.items()}


def _geo_da_uf(uf: str, rnd: random.Random) -> tuple:
    """Devolve (geohash, lat, lon) de um ponto sorteado dentro da UF.

    O sorteio e refeito ate o prefixo de 3 caracteres bater com o da capital.
    Sem isso, ~3% dos pedidos de SP caiam no prefixo '6gz' em vez de '6gy' e
    seriam marcados como fraude geografica por engano no outro repositorio -
    falso positivo puro, causado pelo gerador e nao pelo pipeline.

    lat/lon vao junto porque o Redis (GEOADD), o ClickHouse e o mapa da
    dataviz precisam de coordenada, nao de hash.
    """
    base_lat, base_lon = UF_COORD[uf]
    alvo = PREFIXO_UF[uf]
    raio = 0.25
    for _ in range(8):
        lat = base_lat + rnd.uniform(-raio, raio)
        lon = base_lon + rnd.uniform(-raio, raio)
        gh = geohash_encode(lat, lon)
        if gh[:3] == alvo:
            return gh, round(lat, 6), round(lon, 6)
        raio /= 2          # aperta o cerco em volta da capital
    # ultimo recurso: a propria capital, que por definicao tem o prefixo certo
    return geohash_encode(base_lat, base_lon), base_lat, base_lon


@dataclass
class Universo:
    """Tudo que existe no mundo Liga Sudoers, ja materializado."""
    semente: int
    categorias: list = field(default_factory=list)
    produtos: list = field(default_factory=list)
    pessoas: list = field(default_factory=list)
    dispositivos: list = field(default_factory=list)
    pedidos: list = field(default_factory=list)
    eventos: list = field(default_factory=list)
    reviews: list = field(default_factory=list)
    aneis_fraude: list = field(default_factory=list)

    def resumo(self) -> dict:
        fraudes = [p for p in self.pedidos if p["fraude"]]
        motivos = {}
        for p in fraudes:
            motivos[p["motivo_fraude"]] = motivos.get(p["motivo_fraude"], 0) + 1
        return {
            "semente": self.semente,
            "categorias": len(self.categorias),
            "produtos": len(self.produtos),
            "pessoas": len(self.pessoas),
            "dispositivos": len(self.dispositivos),
            "pedidos": len(self.pedidos),
            "itens_pedidos": sum(len(p["itens"]) for p in self.pedidos),
            "eventos_clickstream": len(self.eventos),
            "reviews": len(self.reviews),
            "pedidos_fraudulentos": len(fraudes),
            "taxa_fraude_pct": round(100 * len(fraudes) / max(len(self.pedidos), 1), 2),
            "fraude_por_motivo": motivos,
            "aneis_fraude": len(self.aneis_fraude),
        }


def gerar_universo(semente: int = SEMENTE,
                   n_pessoas: int = N_PESSOAS,
                   n_produtos: int = N_PRODUTOS,
                   n_pedidos: int = N_PEDIDOS,
                   dias: int = DIAS_HISTORICO) -> Universo:
    """Gera o universo inteiro de forma DETERMINISTICA.

    Mesma semente => exatamente os mesmos dados, sempre. E isso que garante
    que o id 1 do Mongo e o id 1 do Neo4j sao a mesma pessoa.
    """
    rnd = random.Random(semente)
    fake = Faker("pt_BR")
    Faker.seed(semente)

    u = Universo(semente=semente)
    hoje = datetime(2026, 9, 1, 12, 0, 0)   # data fixa: determinismo total
    inicio = hoje - timedelta(days=dias)

    # ---------------- categorias ----------------
    for cid, (desc, attrs) in CATEGORIAS.items():
        u.categorias.append({
            "id": cid, "descricao": desc, "atributos_esperados": attrs,
        })

    # ---------------- produtos ----------------
    # Cada produto ganha os atributos DA SUA categoria. Produtos de categorias
    # diferentes tem chaves diferentes -> documento, nao tabela.
    for pid in range(1, n_produtos + 1):
        cid = rnd.randint(1, len(CATEGORIAS))
        cat_desc, attrs = CATEGORIAS[cid]
        u.produtos.append({
            "id": pid,
            "id_categoria": cid,
            "categoria": cat_desc,
            "descricao": f"{fake.word().capitalize()} {cat_desc[:-1] if cat_desc.endswith('s') else cat_desc} {pid}",
            "valor_unit": round(rnd.uniform(9.9, 4999.0), 2),
            "atributos": _gerar_atributos(attrs, rnd, fake),
            "estoque": rnd.randint(0, 500),
            "ativo": rnd.random() > 0.05,
        })

    # ---------------- pessoas ----------------
    for i in range(1, n_pessoas + 1):
        uf = rnd.choice(UF_LEGITIMAS)
        sexo = rnd.choice(["M", "F"])
        u.pessoas.append({
            "id": i,
            "nome": fake.name_male() if sexo == "M" else fake.name_female(),
            "sexo": sexo,
            "dt_nasc": fake.date_of_birth(minimum_age=18, maximum_age=80).isoformat(),
            "cpf": fake.cpf(),
            "email": f"usuario{i}@ligasudoers.com.br",
            "telefone": _telefone(rnd),
            "uf": uf,
            "cidade": fake.city(),
            "dispositivo_padrao": rnd.choice(MODELOS_DISPOSITIVO),
            "device_id": _device_id(rnd),
            "created_at": (inicio - timedelta(days=rnd.randint(0, 900))).isoformat(),
        })

    # ---------------- aneis de fraude ----------------
    # K pessoas compartilhando MESMO dispositivo e MESMO telefone.
    # Invisivel para uma query SQL comum. Trivial em Cypher.
    ids_disponiveis = list(range(1, n_pessoas + 1))
    rnd.shuffle(ids_disponiveis)
    membros_em_anel = {}
    for a in range(1, N_ANEIS_FRAUDE + 1):
        membros = [ids_disponiveis.pop() for _ in range(TAM_ANEL)]
        anel = {
            "id_anel": a,
            "dispositivo": rnd.choice(MODELOS_DISPOSITIVO),
            "device_id": _device_id(rnd),
            "telefone": _telefone(rnd),
            "membros": sorted(membros),
        }
        u.aneis_fraude.append(anel)
        for m in membros:
            membros_em_anel[m] = anel

    # ---------------- catalogo de dispositivos ----------------
    vistos = {}
    for p in u.pessoas:
        vistos.setdefault(p["device_id"], {"modelo": p["dispositivo_padrao"], "donos": set()})
        vistos[p["device_id"]]["donos"].add(p["id"])
    for anel in u.aneis_fraude:
        vistos.setdefault(anel["device_id"], {"modelo": anel["dispositivo"], "donos": set()})
        vistos[anel["device_id"]]["donos"].update(anel["membros"])
    for dev_id in sorted(vistos):
        info = vistos[dev_id]
        u.dispositivos.append({
            "device_id": dev_id,
            "modelo": info["modelo"],
            "so": _so_do_modelo(info["modelo"]),
            "qtd_donos": len(info["donos"]),
            "compartilhado": len(info["donos"]) > 1,
        })

    # ---------------- pedidos ----------------
    prox_pedido = 1
    for _ in range(n_pedidos):
        pessoa = rnd.choice(u.pessoas)
        dt = inicio + timedelta(seconds=rnd.randint(0, dias * 86400))
        anel = membros_em_anel.get(pessoa["id"])

        fraude, motivo = False, None
        dispositivo = pessoa["dispositivo_padrao"]
        device_id = pessoa["device_id"]
        telefone = pessoa["telefone"]
        uf = pessoa["uf"]

        sorteio = rnd.random()
        if anel and rnd.random() < 0.45:
            # membro de anel: MESMO aparelho fisico, MESMO telefone, outra conta
            dispositivo = anel["dispositivo"]
            device_id = anel["device_id"]
            telefone = anel["telefone"]
            fraude, motivo = True, "dispositivo_compartilhado"
        elif sorteio < TAXA_FRAUDE_GEO:
            uf = rnd.choice(UF_SUSPEITAS)
            fraude, motivo = True, "geolocalizacao"
        elif sorteio < TAXA_FRAUDE_GEO + TAXA_FRAUDE_DEVICE:
            outros = [m for m in MODELOS_DISPOSITIVO if m != pessoa["dispositivo_padrao"]]
            dispositivo = rnd.choice(outros)
            device_id = _device_id(rnd)
            fraude, motivo = True, "troca_dispositivo"

        itens, total = [], 0.0
        for prod in rnd.sample(u.produtos, rnd.randint(1, 5)):
            qtde = rnd.randint(1, 4)
            vt = round(prod["valor_unit"] * qtde, 2)
            total += vt
            itens.append({
                "id_produto": prod["id"],
                "descricao": prod["descricao"],
                "categoria": prod["categoria"],
                "qtde": qtde,
                "valor_unit": prod["valor_unit"],
                "valor_total": vt,
            })

        u.pedidos.append({
            "id": prox_pedido,
            "id_pessoa": pessoa["id"],
            "dt_venda": dt.isoformat(),
            "valor_total": round(total, 2),
            "itens": itens,
            "auditoria": dict(zip(("geohash", "lat", "lon"), _geo_da_uf(uf, rnd)), **{
                "dispositivo": dispositivo,
                "device_id": device_id,
                "uf": uf,
                "telefone": telefone,
            }),
            "fraude": fraude,
            "motivo_fraude": motivo,
        })
        prox_pedido += 1

    u.pedidos.sort(key=lambda p: p["dt_venda"])

    # ---------------- clickstream (Cassandra) ----------------
    for pessoa in u.pessoas:
        sessao = 0
        for _ in range(rnd.randint(1, N_EVENTOS_POR_PESSOA)):
            if rnd.random() < 0.25:
                sessao += 1
            ts = inicio + timedelta(seconds=rnd.randint(0, dias * 86400))
            prod = rnd.choice(u.produtos)
            u.eventos.append({
                "id_pessoa": pessoa["id"],
                "ts": ts.isoformat(),
                "dia": ts.date().isoformat(),
                "id_sessao": f"s{pessoa['id']}-{sessao}",
                "tipo_evento": rnd.choice(TIPOS_EVENTO),
                "id_produto": prod["id"],
                "categoria": prod["categoria"],
                "dispositivo": pessoa["dispositivo_padrao"],
                "device_id": pessoa["device_id"],
                "geohash": _geo_da_uf(pessoa["uf"], rnd)[0],
                "duracao_ms": rnd.randint(80, 45000),
            })
    u.eventos.sort(key=lambda e: (e["id_pessoa"], e["ts"]))

    # ---------------- reviews (MongoDB) ----------------
    rid = 1
    for ped in u.pedidos:
        if rnd.random() >= TAXA_REVIEW:
            continue
        item = rnd.choice(ped["itens"])
        nota = rnd.choices([1, 2, 3, 4, 5], weights=[5, 8, 15, 32, 40])[0]
        u.reviews.append({
            "id": rid,
            "id_produto": item["id_produto"],
            "id_pessoa": ped["id_pessoa"],
            "id_pedido": ped["id"],
            "nota": nota,
            "titulo": rnd.choice(TITULOS_REVIEW[nota]),
            "comentario": " ".join(rnd.sample(FRASES_REVIEW[nota], k=rnd.randint(1, 2))),
            "compra_verificada": True,
            "created_at": ped["dt_venda"],
        })
        rid += 1

    return u


def _gerar_atributos(attrs: list, rnd: random.Random, fake) -> dict:
    """Preenche os atributos especificos da categoria."""
    out = {}
    for a in attrs:
        if a == "voltagem":
            out[a] = rnd.choice(["110V", "220V", "Bivolt"])
        elif a == "garantia_meses":
            out[a] = rnd.choice([3, 6, 12, 24, 36])
        elif a == "potencia_w":
            out[a] = rnd.choice([15, 60, 150, 800, 1500, 2200])
        elif a == "tamanho":
            out[a] = rnd.choice(["PP", "P", "M", "G", "GG", "XG"])
        elif a == "cor":
            out[a] = rnd.choice(["preto", "branco", "azul", "vermelho", "verde", "cinza"])
        elif a == "composicao":
            out[a] = rnd.choice(["100% algodao", "poliester", "algodao/elastano", "linho"])
        elif a == "autor":
            out[a] = fake.name()
        elif a == "paginas":
            out[a] = rnd.randint(80, 900)
        elif a == "isbn":
            out[a] = fake.isbn13()
        elif a == "editora":
            out[a] = fake.company()
        elif a == "peso_g":
            out[a] = rnd.choice([100, 250, 500, 1000, 2000, 5000])
        elif a == "validade_dias":
            out[a] = rnd.choice([15, 30, 90, 180, 365])
        elif a in ("organico", "vegano", "pilhas", "montagem"):
            out[a] = rnd.random() > 0.5
        elif a == "material":
            out[a] = rnd.choice(["madeira", "aco", "plastico", "vidro", "aluminio", "tecido"])
        elif a in ("altura_cm", "largura_cm"):
            out[a] = rnd.randint(20, 220)
        elif a == "interface":
            out[a] = rnd.choice(["USB-C", "USB 3.0", "HDMI", "Bluetooth", "PCIe", "SATA"])
        elif a == "capacidade_gb":
            out[a] = rnd.choice([64, 128, 256, 512, 1024, 2048])
        elif a == "volume_ml":
            out[a] = rnd.choice([30, 60, 100, 200, 500])
        elif a == "tipo_pele":
            out[a] = rnd.choice(["oleosa", "seca", "mista", "sensivel", "normal"])
        elif a == "modalidade":
            out[a] = rnd.choice(["corrida", "futebol", "natacao", "musculacao", "ciclismo"])
        elif a == "idade_min":
            out[a] = rnd.choice([0, 3, 6, 8, 12, 14])
        elif a == "compatibilidade":
            out[a] = rnd.choice(["universal", "linha leve", "linha pesada", "importados"])
        elif a == "porte_animal":
            out[a] = rnd.choice(["pequeno", "medio", "grande"])
        elif a == "sabor":
            out[a] = rnd.choice(["frango", "carne", "salmao", "vegetal"])
        else:
            out[a] = fake.word()
    return out


def _device_id(rnd: random.Random) -> str:
    """Fingerprint do aparelho fisico.

    Diferente do MODELO: duas pessoas podem ter o mesmo modelo de celular sem
    nenhuma relacao entre si. Mas o mesmo `device_id` significa o MESMO
    aparelho - e e esse sinal que denuncia um anel de fraude.
    """
    return "d-%08x" % rnd.getrandbits(32)


def _telefone(rnd: random.Random) -> str:
    ddd = rnd.choice([11, 21, 31, 12, 19, 22, 34])
    return f"({ddd}) 9{rnd.randint(1000, 9999)}-{rnd.randint(1000, 9999)}"


def _so_do_modelo(modelo: str) -> str:
    m = modelo.lower()
    if "iphone" in m or "ipad" in m:
        return "iOS"
    if "web" in m:
        return "Desktop"
    return "Android"


# --------------------------------------------------------------------------
# Saidas
# --------------------------------------------------------------------------
def escrever_json(u: Universo, saida: str) -> list:
    os.makedirs(saida, exist_ok=True)
    escritos = []
    for nome in ("categorias", "produtos", "pessoas", "dispositivos",
                 "pedidos", "eventos", "reviews", "aneis_fraude"):
        caminho = os.path.join(saida, f"{nome}.json")
        with open(caminho, "w", encoding="utf-8") as fh:
            json.dump(getattr(u, nome), fh, ensure_ascii=False, indent=1)
        escritos.append(caminho)
    with open(os.path.join(saida, "resumo.json"), "w", encoding="utf-8") as fh:
        json.dump(u.resumo(), fh, ensure_ascii=False, indent=1)
    escritos.append(os.path.join(saida, "resumo.json"))
    return escritos


def _q(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, bool):
        return "TRUE" if v else "FALSE"
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"


def escrever_sql(u: Universo, saida: str) -> str:
    """Emite INSERTs compativeis com o schema OLTP do repo `jornada_dados`.

    E assim que este repo vira ORIGEM do outro: os mesmos ids, no Postgres.
    """
    os.makedirs(saida, exist_ok=True)
    caminho = os.path.join(saida, "carga_oltp.sql")
    with open(caminho, "w", encoding="utf-8") as fh:
        fh.write("-- Gerado por liga_sudoers_gen.py (semente=%d)\n" % u.semente)
        fh.write("-- Compativel com postgresql-init/oltp.sql do repo jornada_dados\n")
        fh.write("BEGIN;\n")
        for c in u.categorias:
            fh.write("INSERT INTO public.categorias (id, descricao) VALUES (%s, %s) ON CONFLICT (id) DO NOTHING;\n"
                     % (_q(c["id"]), _q(c["descricao"])))
        for p in u.produtos:
            fh.write("INSERT INTO public.produtos (id, id_categoria, descricao, valor_unit) VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING;\n"
                     % (_q(p["id"]), _q(p["id_categoria"]), _q(p["descricao"]), _q(p["valor_unit"])))
        for p in u.pessoas:
            fh.write("INSERT INTO public.pessoas (id, nome, sexo, dt_nasc) VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING;\n"
                     % (_q(p["id"]), _q(p["nome"]), _q(p["sexo"]), _q(p["dt_nasc"])))
        for ped in u.pedidos:
            fh.write("INSERT INTO public.pedidos (id, id_pessoa, dt_venda, valor_total) VALUES (%s, %s, %s, %s) ON CONFLICT (id) DO NOTHING;\n"
                     % (_q(ped["id"]), _q(ped["id_pessoa"]), _q(ped["dt_venda"]), _q(ped["valor_total"])))
            for it in ped["itens"]:
                fh.write("INSERT INTO public.itens_pedidos (id_pedido, id_produto, qtde, valor_total) VALUES (%s, %s, %s, %s);\n"
                         % (_q(ped["id"]), _q(it["id_produto"]), _q(it["qtde"]), _q(it["valor_total"])))
            a = ped["auditoria"]
            fh.write("INSERT INTO public.auditoria_pedidos (id_pedido, dispositivo, geohash, telefone) VALUES (%s, %s, %s, %s);\n"
                     % (_q(ped["id"]), _q(a["dispositivo"]), _q(a["geohash"]), _q(a["telefone"])))
        fh.write("COMMIT;\n")
    return caminho


def main() -> None:
    ap = argparse.ArgumentParser(description="Gerador canonico Liga Sudoers")
    ap.add_argument("--semente", type=int, default=SEMENTE)
    ap.add_argument("--pessoas", type=int, default=N_PESSOAS)
    ap.add_argument("--produtos", type=int, default=N_PRODUTOS)
    ap.add_argument("--pedidos", type=int, default=N_PEDIDOS)
    ap.add_argument("--formato", choices=["json", "sql", "ambos"], default="json")
    ap.add_argument("--saida", default="./saida")
    ap.add_argument("--resumo", action="store_true", help="so imprime o resumo")
    args = ap.parse_args()

    u = gerar_universo(args.semente, args.pessoas, args.produtos, args.pedidos)

    if args.resumo:
        print(json.dumps(u.resumo(), ensure_ascii=False, indent=2))
        return

    if args.formato in ("json", "ambos"):
        for c in escrever_json(u, args.saida):
            print("escrito:", c)
    if args.formato in ("sql", "ambos"):
        print("escrito:", escrever_sql(u, args.saida))
    print()
    print(json.dumps(u.resumo(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
