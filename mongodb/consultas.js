// ==========================================================================
// MongoDB - consultas guiadas da Liga Sudoers
//
//   docker exec -it sudoers_mongo mongosh -u sudoers -p sudoers \
//     --authenticationDatabase admin liga_sudoers
//
// Ou tudo de uma vez:
//   docker exec -i sudoers_mongo mongosh -u sudoers -p sudoers \
//     --authenticationDatabase admin liga_sudoers < mongodb/consultas.js
// ==========================================================================

print("\n=== 1. O MESMO campo `atributos` com CHAVES DIFERENTES por categoria ===");
// Isto e o paradigma documento em uma linha. Nenhuma tabela faz isso bem.
db.produtos.find(
  { categoria: { $in: ["Livros", "Eletronicos", "Pet"] } },
  { descricao: 1, categoria: 1, atributos: 1 }
).limit(3).forEach(printjson);

print("\n=== 2. Consultando DENTRO de um campo que so existe em algumas categorias ===");
// Indice esparso: so indexa os documentos que TEM o campo.
print("produtos 220V: " + db.produtos.countDocuments({ "atributos.voltagem": "220V" }));
print("livros com +500 paginas: " + db.produtos.countDocuments({ "atributos.paginas": { $gt: 500 } }));

print("\n=== 3. O indice esparso esta sendo usado? (explain) ===");
var exp = db.produtos.find({ "atributos.voltagem": "220V" }).explain("executionStats");
var vencedor = exp.queryPlanner.winningPlan;
print("estagio: " + JSON.stringify(vencedor.inputStage ? vencedor.inputStage.stage : vencedor.stage));
print("docs examinados: " + exp.executionStats.totalDocsExamined +
      " | retornados: " + exp.executionStats.nReturned);
print(">>> COLLSCAN = varreu tudo. IXSCAN = usou indice.");

print("\n=== 4. Aggregation: top 5 categorias por faturamento ===");
// $unwind abre o array de itens embutidos - cada item vira uma linha.
db.pedidos.aggregate([
  { $unwind: "$itens" },
  { $group: {
      _id: "$itens.categoria",
      faturamento: { $sum: "$itens.valor_total" },
      pedidos: { $addToSet: "$_id" }
  }},
  { $project: { faturamento: { $round: ["$faturamento", 2] }, qtde_pedidos: { $size: "$pedidos" } } },
  { $sort: { faturamento: -1 } },
  { $limit: 5 }
]).forEach(printjson);

print("\n=== 5. Produtos mais bem avaliados (reviews embutidas, ZERO join) ===");
db.produtos.find(
  { "avaliacao.qtde": { $gte: 5 } },
  { descricao: 1, categoria: 1, avaliacao: 1 }
).sort({ "avaliacao.media": -1 }).limit(5).forEach(printjson);

print("\n=== 6. Busca textual dentro dos comentarios embutidos ===");
var termo = "excelente";
print("produtos citando '" + termo + "': " +
      db.produtos.countDocuments({ $text: { $search: termo } }));

print("\n=== 7. Fraude por motivo ===");
db.pedidos.aggregate([
  { $match: { fraude: true } },
  { $group: { _id: "$motivo_fraude", qtde: { $sum: 1 },
              valor: { $sum: "$valor_total" } } },
  { $sort: { qtde: -1 } }
]).forEach(printjson);

print("\n=== 8. Dispositivos usados por MAIS DE UMA pessoa (o anel de fraude) ===");
// Da para achar aqui? Da. Mas repare no esforco: precisa agrupar tudo,
// montar conjunto de pessoas e filtrar. E isso e so o PRIMEIRO salto.
// Ir alem ("quem mais se conecta a essas pessoas?") vira um pesadelo.
// Guarde essa dor: no Neo4j isso e uma linha.
db.pedidos.aggregate([
  { $group: { _id: "$auditoria.device_id", pessoas: { $addToSet: "$id_pessoa" } } },
  { $project: { qtd_pessoas: { $size: "$pessoas" }, pessoas: 1 } },
  { $match: { qtd_pessoas: { $gt: 1 } } },
  { $sort: { qtd_pessoas: -1 } }
]).forEach(printjson);

print("\n=== 9. $lookup: o 'JOIN' do MongoDB (e por que evitar) ===");
db.pedidos.aggregate([
  { $match: { fraude: true } },
  { $lookup: { from: "pessoas", localField: "id_pessoa", foreignField: "_id", as: "cliente" } },
  { $unwind: "$cliente" },
  { $project: { _id: 1, valor_total: 1, motivo_fraude: 1,
                nome: "$cliente.nome", uf_cliente: "$cliente.endereco.uf",
                uf_compra: "$auditoria.uf" } },
  { $limit: 3 }
]).forEach(printjson);
print(">>> Funciona, mas $lookup nao usa indice do jeito que um JOIN relacional usa.");
print(">>> Se voce precisa de $lookup toda hora, o modelo de documentos esta errado.");

print("\n=== 10. Schema validation: NoSQL TEM schema, se voce quiser ===");
var erro = null;
try {
  db.pedidos.insertOne({ _id: 999999, id_pessoa: 1 });  // faltam campos obrigatorios
} catch (e) { erro = e.code || e.codeName; }
print("insert invalido foi rejeitado? " + (erro !== null ? "SIM (" + erro + ")" : "NAO"));

print("\n=== 11. TTL: documentos que se apagam sozinhos ===");
db.sessoes_checkout.getIndexes().forEach(function (i) {
  if (i.expireAfterSeconds !== undefined)
    print("indice " + i.name + " expira em " + i.expireAfterSeconds + "s (" +
          (i.expireAfterSeconds / 86400) + " dias)");
});

print("\n=== fim ===\n");
