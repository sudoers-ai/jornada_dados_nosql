#!/bin/bash
# ==========================================================================
# Cassandra - consultas guiadas da Liga Sudoers
#
#   docker exec -it sudoers_cassandra bash /scripts/consultas.sh
#
# Interativo:
#   docker exec -it sudoers_cassandra cqlsh
# ==========================================================================
Q() { cqlsh -k liga_sudoers -e "$1" 2>&1; }
titulo() { echo; echo "=== $1 ==="; }

titulo "1. A CONSULTA QUE O CASSANDRA AMA: com a partition key"
echo "Ultimos 5 eventos da pessoa 1 (ja vem ordenado, sem ORDER BY):"
Q "SELECT ts, tipo_evento, id_produto, categoria FROM eventos_por_pessoa WHERE id_pessoa = 1 LIMIT 5;"
echo ">>> O coordenador sabe EXATAMENTE em qual no essa particao esta."
echo ">>> Custo: 1 no consultado. Ordenacao: de graca (ja gravado ordenado)."

titulo "2. A CONSULTA QUE O CASSANDRA RECUSA (e o erro nº1 de quem vem do SQL)"
echo 'Tentando: SELECT * FROM eventos_por_pessoa WHERE tipo_evento = '"'"'compra'"'"';'
Q "SELECT * FROM eventos_por_pessoa WHERE tipo_evento = 'compra' LIMIT 3;"
echo ">>> Erro proposital. Sem partition key, o Cassandra teria que perguntar"
echo ">>> para TODOS os nos do cluster. Ele prefere te barrar a te enganar."

titulo "3. ALLOW FILTERING: a saida que voce NAO deve usar"
Q "SELECT id_pessoa, ts, tipo_evento FROM eventos_por_pessoa WHERE tipo_evento = 'compra' LIMIT 3 ALLOW FILTERING;"
echo ">>> Funcionou. Em 3 mil linhas e instantaneo."
echo ">>> Em 3 bilhoes, derruba o cluster. ALLOW FILTERING em producao e incidente."

titulo "4. A SOLUCAO CERTA: outra tabela, outra particao (mesmo dado)"
DIA=$(cqlsh -k liga_sudoers -e "SELECT dia, hora_bucket FROM eventos_por_dia LIMIT 1;" 2>/dev/null | sed -n '4p' | awk '{print $1}')
HORA=$(cqlsh -k liga_sudoers -e "SELECT dia, hora_bucket FROM eventos_por_dia LIMIT 1;" 2>/dev/null | sed -n '4p' | awk '{print $3}')
echo "Eventos do dia $DIA, faixa de hora $HORA:"
Q "SELECT ts, id_pessoa, tipo_evento FROM eventos_por_dia WHERE dia = '$DIA' AND hora_bucket = $HORA LIMIT 5;"
echo ">>> Mesma informacao da tabela 1, gravada de novo com OUTRA chave."
echo ">>> Duplicar dado no Cassandra nao e desperdicio. E o projeto."

titulo "5. Pedidos de uma pessoa (colecao congelada = o 'JOIN' que nao existe)"
Q "SELECT dt_venda, id_pedido, valor_total, fraude, qtd_itens, itens FROM pedidos_por_pessoa WHERE id_pessoa = 1 LIMIT 3;"
echo ">>> Os itens estao DENTRO da linha. Nao existe JOIN com uma tabela de itens."

titulo "6. COUNTER: coluna que so aceita incremento"
Q "SELECT dia, tipo_evento, total FROM contador_eventos LIMIT 8;"
echo "Tentando INSERT numa tabela de counter (proibido):"
Q "INSERT INTO contador_eventos (dia, tipo_evento, total) VALUES ('2026-01-01', 'teste', 5);"
echo ">>> Counter so muda com UPDATE ... SET total = total + N."

titulo "7. TTL: o dado morre sozinho"
Q "SELECT id_sessao, ts, TTL(id_pessoa) AS segundos_restantes FROM sessoes_ativas LIMIT 3;"
echo ">>> default_time_to_live = 604800s (7 dias) na tabela inteira."

titulo "8. TRACING: veja o coordenador trabalhando"
echo "--- com partition key (bom) ---"
cqlsh -k liga_sudoers -e "TRACING ON; SELECT count(*) FROM eventos_por_pessoa WHERE id_pessoa = 1;" 2>&1 | grep -iE "elapsed|Read [0-9]+ live|Request complete" | head -4
echo "--- varrendo tudo (ruim) ---"
cqlsh -k liga_sudoers -e "TRACING ON; SELECT count(*) FROM eventos_por_pessoa;" 2>&1 | grep -iE "elapsed|Request complete" | head -4
echo ">>> Compare os tempos. A segunda visitou todas as particoes."

titulo "9. token(): como o Cassandra decide em qual no o dado mora"
Q "SELECT id_pessoa, token(id_pessoa) AS particao FROM eventos_por_pessoa LIMIT 5;"
echo ">>> O token e o hash da partition key. Ele define o no. E so isso."

titulo "10. Tamanho real das particoes (o que denuncia hot partition)"
nodetool tablestats liga_sudoers.eventos_por_pessoa 2>/dev/null | grep -E "Space used \(live\)|Compacted partition maximum bytes|Number of partitions" | head -5
echo ">>> Particao gigante = hot partition = no sobrecarregado."

echo
echo "=== fim ==="
