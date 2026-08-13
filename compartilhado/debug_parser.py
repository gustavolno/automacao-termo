from parser_acordo import interpretar_mensagem

texto = """Fechamento de Acordo

PROCESSO: 0738721-38.2026.8.02.0001
Beneficiario: Selmann de Carvalho
CPF: 209.198.914-20
Telefone: (82) 99810137
E-mail: selmanncarvalho7862@gmail.com
Endereco com CEP: Rua doutor Augusto Cardoso- 63- Edificio Aquamare/ Apto: 608- Bairro Jatiuca..
CEP: 57035590
Valor da causa: R$ 2.406,30
Matricula: 498300
Competencias negociadas: 10/09/2024
Acordo fechado no valor de R$1973,17 sendo o pagamento a vista via boleto bancario."""

d = interpretar_mensagem(texto)
print("valor_acordo:", repr(d["valor_acordo"]))
print("valor_original:", repr(d["valor_original"]))
print("nome:", repr(d["nome"]))
