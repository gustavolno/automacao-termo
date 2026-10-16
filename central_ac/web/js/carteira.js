import { h, limpar, brl, num, pct, dataBR, quando, selo, contar, aviso, icone, hojeISO } from './ui.js';
import { get, post } from './api.js';
import { estado, nomeDoUsuario } from './estado.js';
import { registrarContato } from './contatos.js';

const COR = { ADIMPLENTE: 'var(--ok)', INADIMPLENTE: 'var(--risco)', SEM_REGISTRO: 'var(--ouro-escuro)', EM_ANALISE: '#6B7280', OUTROS: '#CFC6B4' };
const ROTULO_PARTE = { ADIMPLENTE: 'Adimplentes', INADIMPLENTE: 'Inadimplentes', SEM_REGISTRO: 'Sem registro', EM_ANALISE: 'Em análise', OUTROS: 'À vista / não conciliados' };
const hoje = hojeISO;

export async function carteira(raiz, [chaveUrl]) {
  const chave = chaveUrl || estado.usuario;
  const [carteiras, resumo] = await Promise.all([get('/api/carteiras'), get(`/api/resumo?carteira=${chave}`)]);
  const atual = carteiras.find((c) => c.id === chave) || carteiras[carteiras.length - 1];
  const ps = resumo.por_status;
  const n = (s) => ps[s]?.clientes || 0;
  const gestao = chave === 'TODAS' || chave === 'DISTRIBUIR' || estado.usuario === 'TODAS';
  let status = 'TODOS', busca = '', limite = 60, adiar = null;
  const selecionados = new Set();

  const titulo = chave === 'TODAS' ? 'Visão da gestão' : chave === 'DISTRIBUIR' ? 'Clientes a distribuir' : `Olá, ${atual.nome}`;
  const dataHoje = new Date().toLocaleDateString('pt-BR', { weekday: 'long', day: 'numeric', month: 'long' });

  // ── carteiras ──
  const faixa = h('div', { class: 'carteiras', role: 'group', 'aria-label': 'Escolher carteira' },
    carteiras.map((c) => h('button', {
      type: 'button', class: `carteira ${c.id === 'DISTRIBUIR' ? 'tracejada' : ''}`, 'aria-pressed': String(c.id === chave),
      onclick: () => { location.hash = `#/carteira/${c.id}`; },
    }, h('span', null, c.nome), h('b', null, num(c.clientes)),
      h('small', null, c.id === 'DISTRIBUIR' ? 'advogados e antigos' : `${c.inadimplentes} inadimplente${c.inadimplentes === 1 ? '' : 's'}`))));

  // ── indicadores: o momento animado da tela ──
  const total = resumo.total || 1;
  const partes = [['ADIMPLENTE', n('ADIMPLENTE')], ['INADIMPLENTE', n('INADIMPLENTE')], ['SEM_REGISTRO', n('SEM_REGISTRO')],
    ['EM_ANALISE', n('EM_ANALISE')], ['OUTROS', n('SEM_CONCILIACAO') + n('NAO_PARCELADO')]];
  const segmentos = partes.map(([s, q]) => h('i', { style: { background: COR[s] }, dataset: { w: `${(q / total) * 100}%` }, title: String(q) }));
  const kpi = (s, rotulo, nota) => {
    const valor = h('span', { class: 'valor' }, '0');
    contar(valor, n(s));
    return h('div', { class: 'kpi' },
      h('span', { class: 'rotulo' }, h('span', { class: 'ponto', style: { background: COR[s] } }), rotulo),
      valor, h('small', null, `${pct(n(s) / total)} da carteira${nota ? ' · ' + nota : ''}`));
  };
  const reais = (s) => (ps[s]?.valor ? brl(ps[s].valor) + ' em aberto' : '');
  const indicadores = h('section', { 'aria-label': 'Adimplência' },
    h('div', { class: 'kpis' },
      kpi('ADIMPLENTE', 'Adimplentes'), kpi('INADIMPLENTE', 'Inadimplentes', reais('INADIMPLENTE')),
      kpi('SEM_REGISTRO', 'Sem registro', reais('SEM_REGISTRO')), kpi('EM_ANALISE', 'Em análise', reais('EM_ANALISE'))),
    h('div', { style: { marginTop: '16px' } },
      h('div', { class: 'proporcao', role: 'img', 'aria-label': 'Proporção por situação' }, segmentos),
      h('div', { class: 'legenda-prop' }, partes.map(([s, q]) => h('span', null, `${ROTULO_PARTE[s]}: ${num(q)}`)))));

  // ── fila de cobrança ──
  const corpo = h('tbody');
  const rodape = h('div', { class: 'rodape-plano', style: { justifyContent: 'center' } });
  const barra = h('div', { class: 'barra-selecao', hidden: true });
  const contagem = h('small', null, '');
  const filtros = [['TODOS', 'Todos', resumo.total], ['INADIMPLENTE', 'Inadimplentes', n('INADIMPLENTE')], ['SEM_REGISTRO', 'Sem registro', n('SEM_REGISTRO')],
    ['EM_ANALISE', 'Em análise', n('EM_ANALISE')], ['LEMBRETES', 'Lembretes de hoje', resumo.lembretes_hoje]];
  const chips = h('div', { class: 'filtros', role: 'group', 'aria-label': 'Filtrar a fila' });
  const desenharChips = () => limpar(chips).append(...filtros.map(([id, rot, q]) =>
    h('button', { type: 'button', class: 'chip', 'aria-pressed': String(status === id), onclick: () => { status = id; limite = 60; desenharChips(); carregar(); } }, `${rot} (${num(q)})`)));
  const campoBusca = h('input', {
    class: 'entrada', type: 'search', placeholder: 'Buscar nome ou CPF', 'aria-label': 'Buscar cliente', style: { width: '260px', maxWidth: '100%' },
    oninput: (e) => { clearTimeout(adiar); adiar = setTimeout(() => { busca = e.target.value; limite = 60; carregar(); }, 300); },
  });

  const atualizarBarra = () => {
    barra.hidden = selecionados.size === 0;
    limpar(barra).append(h('b', null, `${selecionados.size} selecionado${selecionados.size === 1 ? '' : 's'}`), 'Atribuir a:',
      estado.negociadoras.map((neg) => h('button', {
        type: 'button', class: 'btn pequeno',
        onclick: async () => {
          await post('/api/atribuir', { ids: [...selecionados], carteira: neg.id, por: nomeDoUsuario() });
          aviso(`${selecionados.size} cliente(s) atribuído(s) a ${neg.nome}.`, 'ok');
          carteira(raiz, [chaveUrl]);
        },
      }, neg.nome)),
      h('button', { type: 'button', class: 'btn pequeno', onclick: () => { selecionados.clear(); atualizarBarra(); carregar(); } }, 'Limpar seleção'));
  };

  const linha = (c) => {
    const lembre = c.lembrar_em && c.lembrar_em <= hoje();
    return h('tr', null,
      gestao ? h('td', { style: { width: '44px' } }, h('input', {
        type: 'checkbox', 'aria-label': `Selecionar ${c.nome}`, checked: selecionados.has(c.id), style: { width: '18px', height: '18px', accentColor: 'var(--ouro-escuro)' },
        onchange: (e) => { e.target.checked ? selecionados.add(c.id) : selecionados.delete(c.id); atualizarBarra(); },
      })) : null,
      h('td', null, h('a', { class: 'nome-cliente', href: `#/cliente/${encodeURIComponent(c.id)}` }, c.nome),
        h('span', { class: 'sub' },
          c.parcelado ? `${c.qtd_parcelas}x de ${brl(c.valor_parcela)}${c.proximo_venc ? ' · próximo vencimento ' + dataBR(c.proximo_venc) : ''}` : (c.condicao || 'sem condição informada'),
          gestao ? ` · ${c.carteira === 'DISTRIBUIR' ? 'operador ' + (c.operador || '—').toLowerCase() : c.carteira_nome}` : '')),
      h('td', null, h('span', { title: c.motivo || '' }, selo(c.status))),
      h('td', { class: 'num' }, c.dias_atraso ? `${c.dias_atraso} dias` : '—'),
      h('td', { class: 'num' }, c.valor_pendente ? h('b', null, brl(c.valor_pendente)) : '—'),
      h('td', null, quando(c.ultimo_contato), lembre ? h('span', { class: 'sub', style: { color: 'var(--risco)', fontWeight: 700 } }, 'lembrar hoje') : null),
      h('td', null, h('div', { class: 'acoes' },
        h('button', { type: 'button', class: 'btn pequeno', 'aria-label': `Registrar contato com ${c.nome}`, title: 'Registrar contato', onclick: () => registrarContato(c, carregar) }, icone('contato')),
        h('a', { class: 'btn pequeno', 'aria-label': `Enviar o boleto do mês de ${c.nome}`, title: 'Boleto do mês', href: `#/robos?tarefa=conferir_mes&nomes=${encodeURIComponent(c.nome)}` }, icone('boleto')))));
  };

  let token = 0;
  async function carregar() {
    const meu = ++token;
    const r = await get(`/api/clientes?carteira=${chave}&status=${status}&q=${encodeURIComponent(busca)}&limite=${limite}`);
    if (meu !== token) return;
    limpar(corpo);
    if (!r.itens.length) {
      corpo.append(h('tr', null, h('td', { colSpan: 7 }, h('div', { class: 'vazio' }, h('strong', null, 'Ninguém por aqui'),
        status === 'LEMBRETES' ? 'Nenhum lembrete de cobrança para hoje.' : 'Nenhum cliente com este filtro. Mude o filtro ou a busca.'))));
    } else corpo.append(...r.itens.map(linha));
    contagem.textContent = `Mostrando ${r.itens.length} de ${num(r.total)} · mais atrasados primeiro`;
    limpar(rodape);
    rodape.hidden = r.total <= r.itens.length;
    if (!rodape.hidden) rodape.append(h('button', { type: 'button', class: 'btn', onclick: () => { limite += 60; carregar(); } }, `Mostrar mais ${Math.min(60, r.total - r.itens.length)}`));
  }

  const fila = h('section', { class: 'cartao', 'aria-labelledby': 'fila' },
    h('div', { class: 'cartao-topo' }, h('div', null, h('h2', { id: 'fila' }, 'Fila de cobrança'), contagem), h('div', { class: 'topo-acoes' }, campoBusca)),
    h('div', { class: 'cartao-corpo', style: { paddingBottom: '8px' } }, chips),
    h('div', { class: 'tabela-rolagem' }, h('table', null,
      h('thead', null, h('tr', null, gestao ? h('th', null, h('span', { class: 'so-leitor' }, 'Selecionar')) : null,
        h('th', null, 'Cliente'), h('th', null, 'Situação'), h('th', { class: 'num' }, 'Atraso'), h('th', { class: 'num' }, 'Em aberto'),
        h('th', null, 'Último contato'), h('th', { class: 'num' }, h('span', { class: 'so-leitor' }, 'Ações')))),
      corpo)),
    rodape);

  limpar(raiz).append(
    h('header', { class: 'topo' },
      h('div', null, h('h1', null, titulo), h('p', null, dataHoje.charAt(0).toUpperCase() + dataHoje.slice(1) + ' · veja quem precisa de contato hoje')),
      h('a', { class: 'btn ouro', href: '#/robos' }, icone('robos'), 'Central de robôs')),
    faixa, indicadores, fila, barra);
  desenharChips();
  carregar();
  requestAnimationFrame(() => requestAnimationFrame(() => segmentos.forEach((s) => { s.style.width = s.dataset.w; })));
}
