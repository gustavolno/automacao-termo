# Central AC Cobrança

Carteira e adimplência das negociadoras + central dos robôs (baixar boletos, subir acordo, enviar o boleto do mês), tudo numa tela só.

## Como abrir

Dê dois cliques em `iniciar_central.bat` (na raiz do projeto) ou rode `.venv\Scripts\python.exe -m central_ac`.
A Central abre em http://127.0.0.1:8765 e só atende **este computador**.
A primeira abertura leva ~15 s (lê a planilha da Jaci).

## O que tem

| Tela | Para quê |
|---|---|
| **Carteira** | Carteira de cada negociadora (Emília, Yanca, Litielly, Gabrielle, Luisa), "A distribuir" e visão da gestão. Indicadores de adimplência, fila de cobrança (mais atrasados primeiro), lembretes, registro de contatos e redistribuição de clientes. |
| **Ficha do cliente** | Acordo, parcelas conferidas com o Sicoob, contatos, documentos do Dropbox e e-mails já enviados. |
| **Robôs** | Conferir e enviar o boleto do mês (com plano para aprovar), processar clientes, baixar boletos e subir acordo. Andamento ao vivo, perguntas na tela e botão Parar. |

## De onde vêm os dados (somente leitura)

- Planilha da Jaci (a mais recente entre a baixada do OneDrive e a do Dropbox): acordos e **operador responsável**.
- `CONCILIACAO_ADIMPLENCIA_*.xlsx` na raiz do projeto (a mais recente): situação de cada cliente e parcelas.
- Contatos, lembretes, redistribuição de carteira e histórico de robôs ficam em SQLite local: `%LOCALAPPDATA%\BaixarBoletos\central\central.db`.

## Quando o PostgreSQL chegar

Só duas coisas trocam; telas, API e robôs não mudam:

1. `central_ac/dados.py` (`Repositorio`): hoje lê as planilhas. Vira consultas nas tabelas `clientes`, `acordos`, `parcelas`, `pagamentos`.
2. `central_ac/store.py`: hoje SQLite. Vira o mesmo esquema no Postgres (as funções já têm o formato de um repositório).

Antes de abrir para as negociadoras, falta o **login por pessoa** (hoje o seletor "Quem está usando" não tem senha) e ligar o servidor à rede interna. Dados de clientes (CPF, e-mail, valores): nunca expor à internet.

## Robôs: regras que valem sempre

- **Um robô por vez** (o Global Office aceita uma sessão por login).
- Nada é gravado no Global Office sem confirmação: ou você responde a pergunta na tela, ou autoriza antes, no plano de envio, **somente** a reemissão de 1 boleto vencido do mês (vencimento daqui a 2 dias).
- E-mail só sai com o boleto do mês **dentro da validade**; sem e-mail, e-mail do escritório ou "já enviado" ficam fora (reenviar é escolha sua, no plano).
- Itens com aviso (e-mail achado só pelo nome, e-mail de advogado, já enviado) vêm **desmarcados**.

## Testes

`.venv\Scripts\python.exe -m pytest central_ac/tests -q` (sobe um servidor de teste com banco temporário; não usa Global Office nem webmail).
