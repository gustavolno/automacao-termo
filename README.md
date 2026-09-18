# Automações Aldrigues Cândido Advocacia

Este repositório contém o conjunto de ferramentas e automações desenvolvidas para otimizar a rotina jurídica e administrativa do escritório **Aldrigues Cândido Advocacia**. Todas as automações possuem interfaces gráficas amigáveis (GUI) e executáveis independentes.

---

## 🛠 Ferramentas e Automações

### 1. Gerador de Termos de Acordo (`gerador_termos`)
Script em Python que automatiza a geração de Termos de Acordo (documentos Word `.docx`) a partir de dados brutos enviados via WhatsApp por atendentes de negociação.
- **Parser Inteligente**: Lê a mensagem do WhatsApp colada pelo usuário e extrai automaticamente informações como: Nome, CPF, Número do Processo, Matrícula, Valores, e Vencimentos.
- **Cálculo Automático**: Converte valores para extenso, calcula honorários, e gera as parcelas automaticamente.
- **Revisão Visual**: Interface gráfica para o usuário editar os dados antes de montar o `.docx` final.

### 2. Automação Juriscalc (`juriscalc`)
Automação desenvolvida para o portal Juriscalc, que realiza cálculos judiciais de forma repetitiva através de uma lista.
- **Processamento em Lote**: Carrega uma planilha de dados, preenche o sistema Juriscalc automaticamente e baixa os laudos de cálculo em PDF.
- **Monitoramento Robusto**: Sistema de logging, controle de status, interface interativa e geração de resumo de sucessos/erros.

### 3. Gerador de Boletos GEAP (`gerador_boletos`)
Robô autônomo (baseado em Playwright) que integra com o sistema Global Office para emissão automatizada de boletos de acordos.
- **Leitura Excel Inteligente**: Faz o mapeamento de CPFs, valores de honorários, valores de parcelas e datas de vencimento via tabela Excel.
- **Navegação Autônoma**: Realiza o preenchimento dos boletos via GlobalOffice, lidando com tempos de carregamento dinâmicos e salvando os boletos gerados em PDF (com nome formatado do cliente).
- **Tratamento de Sessão**: Exige login manual apenas para passar do reCAPTCHA e salva o estado de sessão para emitir múltiplos boletos sem interrupção.

### 4. Central de Download de Boletos Global Office (`baixar_boletos`)
Robô autônomo com interface gráfica para download automático de todos os boletos emitidos de um cliente no Global Office, organizando-os diretamente nas pastas do Dropbox.
- **Busca Rápida por Cliente**: O usuário digita o nome completo do cliente na interface gráfica e inicia o download.
- **Navegação Inteligente no Global Office**: Acessa a empresa `AC COBRANÇA`, entra no cadastro de boletos (`fmdBoletosCad`), ajusta paginação para 100 registros e filtra o cliente.
- **Padrão de Nomenclatura Padronizado**:
  - Boletos de parcela: `BOLETO - [MÊS ANO].pdf` (ex: `BOLETO - NOV 2027.pdf`).
  - Boletos de entrada: `BOLETO - ENTRADA - [MÊS ANO].pdf`.
- **Organização no Dropbox**: Salva os PDFs diretamente em:
  `...\Dropbox\COBRANÇA NEGOCIAÇÃO\ADMINISTRATIVO- COBRANÇA\ACOMPANHAMENTO DE ACORDOS FECHADOS\<CLIENTE>\BOLETOS DO ACORDO`
- **Botão Direto**: Botão `📁 ABRIR NO DROPBOX` para abrir a pasta local do cliente com um clique.

---

## Design System (Dark Executive)
Todas as interfaces gráficas são padronizadas sob o *Design System* do escritório:
- Modo Noturno Elegante com tons de Midnight Slate (`#0B0F17`)
- Título Escuro Nativo no Windows (DWM)
- Acentos nas cores Dourado (Luxo Jurídico) e Esmeralda.
- Fontes serifadas elegantes (Georgia) para marca, aliadas ao minimalismo da UI (Segoe UI).

---

## Como Usar / Compilação

1. Ative o ambiente virtual:
   ```cmd
   .\.venv\Scripts\activate
   ```
2. Instale as dependências:
   ```cmd
   pip install -r requirements.txt
   playwright install chromium
   ```
3. Para executar a **Central de Download de Boletos**:
   ```cmd
   python baixar_boletos_gui.py
   ```
4. Para compilar o executável `BaixarBoletos.exe`:
   ```cmd
   python build_exe.py
   ```
   O arquivo compilado estará disponível em `dist/BaixarBoletos.exe`.

