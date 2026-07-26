# Automação de Termos de Acordo

Este projeto é um script em Python com interface gráfica (GUI) que automatiza a geração de Termos de Acordo (documentos Word `.docx`) a partir de dados brutos enviados via WhatsApp por atendentes de negociação.

## Funcionalidades

- **Parser Inteligente**: Lê a mensagem do WhatsApp colada pelo usuário e extrai automaticamente informações como:
  - Nome do Cliente
  - CPF
  - Número do Processo Judicial
  - Matrícula
  - Endereço
  - Valor da Dívida e Valor do Acordo
  - Valor de Entrada e Parcelas
  - Datas de Vencimento e Início das Parcelas
- **Cálculo Automático**: 
  - Separa o valor total do acordo em Honorários (10%) e repasse para a GEAP.
  - Converte valores numéricos para extenso (ex: "R$ 1.000,00 (Um mil reais)").
  - Calcula automaticamente datas de vencimento de entrada e parcelas caso não sejam fornecidas.
- **Interface de Revisão**: Permite que o usuário revise e edite todos os campos antes de gerar o documento final.
- **Preservação de Formatação**: Utiliza a biblioteca `docxtpl` com um arquivo `MODELO.docx`, mantendo logos, estilos de fonte, negritos, cabeçalhos e rodapés idênticos ao padrão do escritório.

## Como Usar

1. Certifique-se de ter o Python instalado e ative o ambiente virtual (se aplicável).
2. Execute o arquivo da interface:
   ```powershell
   .\venv\Scripts\pythonw.exe interface.py
   ```
3. Na janela que abrir, cole a mensagem recebida pelo WhatsApp na área indicada.
4. Clique em **🔍 INTERPRETAR MENSAGEM**.
5. Revise os campos extraídos à direita. Os campos que o sistema não conseguir identificar ficarão destacados em vermelho para preenchimento manual.
6. Clique em **⚡ GERAR TERMO DE ACORDO**.
7. O documento será salvo na pasta `Termos Gerados/` e o sistema perguntará se você deseja abri-lo imediatamente no Word.

## Requisitos

- Python 3
- `docxtpl`
- `num2words`
- `tkinter` (geralmente incluso no Python)

Instale as dependências com:
```powershell
pip install docxtpl num2words
```
