#!/bin/sh
# ==========================================================================
# Redis - consultas guiadas da Liga Sudoers
#
#   docker exec -it sudoers_redis sh /scripts/consultas.sh
#
# Ou interativo:
#   docker exec -it sudoers_redis redis-cli -a sudoers
# ==========================================================================
R="redis-cli -a sudoers --no-auth-warning"

titulo() { echo; echo "=== $1 ==="; }

titulo "1. A REGRA ANTIFRAUDE EM 1 COMANDO (o motivo de o Redis existir aqui)"
echo "Dispositivo atual da pessoa 1:"
$R GET device:atual:1
echo "Todos os dispositivos que a pessoa 1 ja usou (SET, sem duplicata):"
$R SMEMBERS device:hist:1
echo ">>> Se o device do checkout nao for o de device:atual, e suspeito."
echo ">>> Custo: O(1). Latencia: microssegundos. No Postgres seria um SELECT no meio do checkout."

titulo "2. Quem usou MAIS DE UM dispositivo? (candidatos a fraude)"
echo "pessoa | qtde de dispositivos distintos"
for i in 1 2 3 19 87 185 315 346; do
  n=$($R SCARD device:hist:$i)
  echo "  pessoa $i -> $n"
done

titulo "3. HASH: ler UM campo sem trazer o objeto inteiro"
$R HGET pessoa:1 nome
$R HGET pessoa:1 uf
echo "Objeto completo (HGETALL):"
$R HGETALL pessoa:1

titulo "4. ZSET: ranking sempre ordenado (nunca precisa de ORDER BY)"
echo "Top 5 produtos mais vendidos:"
$R ZREVRANGE rank:produtos 0 4 WITHSCORES
echo "Posicao do produto 42 no ranking:"
$R ZREVRANK rank:produtos produto:42

titulo "5. LIST: os ultimos pedidos da pessoa (fila de tamanho fixo)"
$R LRANGE pessoa:ultimos_pedidos:1 0 -1
echo ">>> LPUSH + LTRIM mantem a lista com no maximo 10 itens, para sempre."

titulo "6. STRING atomica: contadores sem race condition"
echo "Fraudes por motivo:"
$R MGET metrica:fraude_motivo:dispositivo_compartilhado \
        metrica:fraude_motivo:troca_dispositivo \
        metrica:fraude_motivo:geolocalizacao
echo ">>> INCR e atomico. Dois processos incrementando ao mesmo tempo nao se perdem."

titulo "7. HYPERLOGLOG: visitantes unicos usando 12KB fixos"
DIA=$($R --scan --pattern 'hll:visitantes:*' | head -1)
echo "chave: $DIA"
echo "cardinalidade estimada:"
$R PFCOUNT "$DIA"
echo "memoria dessa chave (bytes):"
$R MEMORY USAGE "$DIA"
echo ">>> Um SET com os mesmos ids gastaria muito mais. Erro do HLL: ~0.81%."

titulo "8. GEO: busca por proximidade (o Redis fala geohash nativamente)"
echo "Pedidos num raio de 50km do centro de Sao Paulo:"
$R GEOSEARCH geo:pedidos FROMLONLAT -46.6333 -23.5505 BYRADIUS 50 km COUNT 5 ASC
echo "Coordenada e geohash do primeiro pedido:"
$R GEOPOS geo:pedidos ped:1
$R GEOHASH geo:pedidos ped:1

titulo "9. STREAM: a fila de fraude que vai virar evento no Kafka"
echo "tamanho do stream:"
$R XLEN stream:fraude
echo "primeiros 2 alertas:"
$R XRANGE stream:fraude - + COUNT 2

titulo "10. TTL: o dado que se apaga sozinho"
CH=$($R --scan --pattern 'carrinho:*' | head -1)
echo "carrinho: $CH"
$R HGETALL "$CH"
echo "segundos restantes de vida:"
$R TTL "$CH"
echo ">>> Carrinho abandonado nao precisa de job de limpeza. Ele morre sozinho."

titulo "11. Quanto isso tudo custa de memoria?"
$R DBSIZE
$R INFO memory | grep -E "used_memory_human|used_memory_peak_human"

titulo "12. O PERIGO: nunca rode KEYS * em producao"
echo "Use SCAN (cursor, nao trava o servidor):"
$R --scan --pattern 'device:atual:*' | head -3
echo ">>> KEYS * varre TUDO e bloqueia o Redis inteiro. SCAN pagina."

echo
echo "=== fim ==="
