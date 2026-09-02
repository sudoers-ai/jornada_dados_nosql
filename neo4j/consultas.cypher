// ==========================================================================
// Neo4j - consultas guiadas da Liga Sudoers
//
//   docker exec -it sudoers_neo4j cypher-shell -u neo4j -p sudoers123 \
//     -f /scripts/consultas.cypher
//
// Interativo (recomendado para explorar):
//   docker exec -it sudoers_neo4j cypher-shell -u neo4j -p sudoers123
//
// Visual (o "aha" da aula): http://localhost:7474
// ==========================================================================

// --------------------------------------------------------------------------
// 1. O ANEL DE FRAUDE - a query que justifica o banco de grafos existir
// --------------------------------------------------------------------------
// Leia o padrao como um desenho:
//   uma Pessoa fez um Pedido que USOU um Dispositivo
//   ...que foi usado por Pedido de OUTRA Pessoa.
// Se o mesmo aparelho fisico atende varias contas, isso e um anel.
MATCH (d:Dispositivo)<-[:USOU]-(:Pedido)<-[:FEZ]-(p:Pessoa)
WITH d, collect(DISTINCT p.id) AS pessoas, count(DISTINCT p) AS qtd
WHERE qtd > 1
RETURN d.device_id AS dispositivo, d.modelo AS modelo, qtd AS contas, pessoas
ORDER BY qtd DESC;

// --------------------------------------------------------------------------
// 2. Quem sao essas pessoas? (nomes, CPFs e UFs diferentes - todas "normais")
// --------------------------------------------------------------------------
MATCH (d:Dispositivo)<-[:USOU]-(:Pedido)<-[:FEZ]-(p:Pessoa)
WITH d, count(DISTINCT p) AS qtd
WHERE qtd > 1
WITH d LIMIT 1
MATCH (d)<-[:USOU]-(ped:Pedido)<-[:FEZ]-(p:Pessoa)
RETURN d.device_id AS dispositivo, p.id AS id_pessoa, p.nome AS nome,
       p.cpf AS cpf, p.uf AS uf,
       count(ped) AS pedidos, round(sum(ped.valor_total), 2) AS total
ORDER BY total DESC;

// >>> Repare: CPFs diferentes, nomes diferentes, UFs validas (SP/MG/RJ).
// >>> Nenhuma regra de linha do jornada_dados pegaria isso.

// --------------------------------------------------------------------------
// 3. O SEGUNDO SINAL: telefone compartilhado
// --------------------------------------------------------------------------
MATCH (t:Telefone)<-[:VIA_TELEFONE]-(:Pedido)<-[:FEZ]-(p:Pessoa)
WITH t, count(DISTINCT p) AS contas
WHERE contas > 1
RETURN t.numero AS telefone, contas
ORDER BY contas DESC;

// --------------------------------------------------------------------------
// 4. CAMINHO MAIS CURTO entre duas contas "sem relacao nenhuma"
// --------------------------------------------------------------------------
// Esta e a consulta que e praticamente impossivel em SQL.
// Pegamos duas pessoas de um mesmo anel e perguntamos: como elas se conectam?
MATCH (d:Dispositivo)<-[:USOU]-(:Pedido)<-[:FEZ]-(p:Pessoa)
WITH d, collect(DISTINCT p) AS ps, count(DISTINCT p) AS qtd
WHERE qtd > 1
WITH ps[0] AS a, ps[1] AS b LIMIT 1
// Filtramos os TIPOS de aresta de proposito: sem isso o caminho mais curto
// pode passar por um produto que as duas compraram por coincidencia - o que
// e verdade, mas nao e o que estamos investigando.
MATCH caminho = shortestPath((a)-[:FEZ|USOU|VIA_TELEFONE*..6]-(b))
RETURN a.nome AS de, b.nome AS para, length(caminho) AS saltos,
       [n IN nodes(caminho) |
          labels(n)[0] + ": " + coalesce(n.nome, n.device_id, n.numero, toString(n.id))
       ] AS rota;

// >>> Em SQL: 6 self-joins encadeados, um por salto possivel, e voce ainda
// >>> precisaria saber ANTES quantos saltos procurar.

// --------------------------------------------------------------------------
// 5. RAIO DE CONTAMINACAO: quem esta a 2 saltos de uma conta suspeita
// --------------------------------------------------------------------------
MATCH (d:Dispositivo)<-[:USOU]-(:Pedido)<-[:FEZ]-(p:Pessoa)
WITH d, count(DISTINCT p) AS qtd WHERE qtd > 1
WITH d LIMIT 1
MATCH (d)<-[:USOU]-(:Pedido)<-[:FEZ]-(suspeito:Pessoa)
MATCH (suspeito)-[:FEZ]->(:Pedido)-[:VIA_TELEFONE]->(:Telefone)<-[:VIA_TELEFONE]-(:Pedido)<-[:FEZ]-(vizinho:Pessoa)
WHERE vizinho <> suspeito
RETURN DISTINCT vizinho.id AS id, vizinho.nome AS nome, vizinho.uf AS uf
LIMIT 15;

// --------------------------------------------------------------------------
// 6. SCORE DE RISCO - o grafo devolve um numero para o DW do jornada_dados
// --------------------------------------------------------------------------
// Este resultado e o que sai daqui e volta para a camada gold do outro repo.
MATCH (p:Pessoa)-[:FEZ]->(ped:Pedido)
OPTIONAL MATCH (ped)-[:USOU]->(d:Dispositivo)
WITH p, ped, d
OPTIONAL MATCH (d)<-[:USOU]-(:Pedido)<-[:FEZ]-(outro:Pessoa)
WHERE outro <> p
WITH p,
     count(DISTINCT ped)                                   AS pedidos,
     count(DISTINCT CASE WHEN ped.fraude THEN ped END)     AS fraudes,
     count(DISTINCT d)                                     AS dispositivos,
     count(DISTINCT outro)                                 AS contas_vizinhas
RETURN p.id AS id_pessoa, p.nome AS nome, pedidos, fraudes,
       dispositivos, contas_vizinhas,
       // score simples e explicavel: e didatico, nao e producao
       round(100.0 * (
            0.4 * (toFloat(fraudes) / pedidos) +
            0.3 * (CASE WHEN dispositivos > 1 THEN 1.0 ELSE 0.0 END) +
            0.3 * (CASE WHEN contas_vizinhas > 0 THEN 1.0 ELSE 0.0 END)
       ), 1) AS score_risco
ORDER BY score_risco DESC, fraudes DESC
LIMIT 10;

// --------------------------------------------------------------------------
// 7. RECOMENDACAO: "quem comprou X tambem comprou Y"
// --------------------------------------------------------------------------
// O mesmo grafo que acha fraude tambem faz recomendacao. E o mesmo padrao:
// dois nos ligados por um terceiro.
MATCH (alvo:Produto {id: 42})<-[:CONTEM]-(:Pedido)-[:CONTEM]->(outro:Produto)
WHERE outro <> alvo
RETURN alvo.descricao AS comprou, outro.descricao AS tambem_comprou,
       count(*) AS vezes
ORDER BY vezes DESC
LIMIT 5;

// --------------------------------------------------------------------------
// 8. O grafo tambem agrega (nao e so caminho)
// --------------------------------------------------------------------------
MATCH (ped:Pedido)-[:ORIGINADO_EM]->(l:Local)
RETURN l.uf AS uf,
       count(ped) AS pedidos,
       count(CASE WHEN ped.fraude THEN 1 END) AS fraudes,
       round(100.0 * count(CASE WHEN ped.fraude THEN 1 END) / count(ped), 2) AS pct_fraude
ORDER BY pct_fraude DESC;

// --------------------------------------------------------------------------
// 9. Tamanho do grafo
// --------------------------------------------------------------------------
MATCH (n) RETURN labels(n)[0] AS tipo, count(*) AS qtde ORDER BY qtde DESC;
