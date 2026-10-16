// Utilitários de interface. Tudo que vem de planilha/termo entra como TEXTO (nunca innerHTML).

export function h(tag, attrs, ...filhos) {
  const el = document.createElement(tag);
  let valor;
  for (const [k, v] of Object.entries(attrs || {})) {
    if (v == null || v === false) continue;
    if (k === 'class') el.className = v;
    else if (k === 'value') valor = v;
    else if (k.startsWith('on')) el.addEventListener(k.slice(2).toLowerCase(), v);
    else if (k === 'dataset') Object.assign(el.dataset, v);
    else if (k === 'style' && typeof v === 'object') Object.assign(el.style, v);
    else if (k in el && k !== 'list' && k !== 'form') el[k] = v;
    else el.setAttribute(k, v === true ? '' : v);
  }
  const por = (f) => {
    if (f == null || f === false) return;
    if (Array.isArray(f)) f.forEach(por);
    else el.append(f instanceof Node ? f : document.createTextNode(String(f)));
  };
  filhos.forEach(por);
  if (valor !== undefined) el.value = valor;   // depois dos <option>
  return el;
}

export const limpar = (el) => { while (el.firstChild) el.removeChild(el.firstChild); return el; };
export const reduzMovimento = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

// ── formatação ──
const nf = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
export const brl = (n) => (n == null ? '—' : nf.format(n));
export const num = (n) => new Intl.NumberFormat('pt-BR').format(n);
export const pct = (n) => new Intl.NumberFormat('pt-BR', { style: 'percent', maximumFractionDigits: 0 }).format(n);
export function dataBR(iso) {
  if (!iso) return '—';
  const [a, m, d] = String(iso).slice(0, 10).split('-');
  return `${d}/${m}/${a}`;
}
export function quando(iso) {            // 'AAAA-MM-DD HH:MM:SS' -> 'há 3 dias' / 'hoje 14:30'
  if (!iso) return 'sem contato';
  const t = new Date(iso.replace(' ', 'T'));
  const dias = Math.floor((Date.now() - t) / 864e5);
  if (dias <= 0) return 'hoje ' + iso.slice(11, 16);
  if (dias === 1) return 'ontem';
  return `há ${dias} dias`;
}
export function cpfMascarado(cpf, revelar) {
  const d = String(cpf || '').replace(/\D/g, '');
  if (d.length !== 11) return d || 'sem CPF';
  const f = `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
  return revelar ? f : `•••.${d.slice(3, 6)}.•••-${d.slice(9)}`;
}
export function hojeISO() {              // data LOCAL (toISOString usaria UTC e viraria o dia às 21h)
  const d = new Date();
  const dois = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}-${dois(d.getMonth() + 1)}-${dois(d.getDate())}`;
}
export const primeiroNome = (n) => String(n || '').split(' ')[0];

// ── situação do cliente ──
export const SITUACAO = {
  ADIMPLENTE: { rotulo: 'Adimplente', classe: 'ok' },
  INADIMPLENTE: { rotulo: 'Inadimplente', classe: 'risco' },
  SEM_REGISTRO: { rotulo: 'Sem registro', classe: 'atencao' },
  EM_ANALISE: { rotulo: 'Em análise', classe: 'neutro' },
  SEM_CONCILIACAO: { rotulo: 'Não conciliado', classe: 'neutro' },
  NAO_PARCELADO: { rotulo: 'À vista', classe: 'neutro' },
};
export const selo = (status) => {
  const s = SITUACAO[status] || { rotulo: status, classe: 'neutro' };
  return h('span', { class: `selo ${s.classe}` }, s.rotulo);
};

// ── animação de número (um momento orquestrado na carga da carteira) ──
export function contar(el, alvo, formato = num, ms = 900) {
  if (reduzMovimento() || !alvo) { el.textContent = formato(alvo); return; }
  const ini = performance.now();
  const passo = (agora) => {
    const t = Math.min(1, (agora - ini) / ms);
    el.textContent = formato(Math.round(alvo * (1 - Math.pow(1 - t, 4))));
    if (t < 1) requestAnimationFrame(passo);
  };
  requestAnimationFrame(passo);
}

// ── avisos ──
export function aviso(texto, tipo = 'info') {
  const el = h('div', { class: `toast ${tipo}`, role: 'status' }, texto);
  document.getElementById('toasts').append(el);
  setTimeout(() => { el.classList.add('saindo'); setTimeout(() => el.remove(), 300); }, tipo === 'erro' ? 7000 : 3500);
}

// ── janela de diálogo ──
export function dialogo({ titulo, corpo, botoes, largura, ref }) {
  return new Promise((resolve) => {
    const d = h('dialog', { class: 'dialogo', style: largura ? { width: largura } : null },
      h('h2', null, titulo), h('div', { class: 'dialogo-corpo' }, corpo),
      h('div', { class: 'dialogo-botoes' }, botoes.map((b) =>
        h('button', { type: 'button', class: `btn ${b.classe || ''}`, onclick: () => { d.close(); resolve(b.valor); } }, b.rotulo))));
    d.addEventListener('cancel', (e) => { e.preventDefault(); });   // só fecha por um botão
    document.body.append(d);
    d.addEventListener('close', () => d.remove());
    if (ref) ref.fechar = () => { if (d.open) { d.close(); resolve(null); } };   // quem chamou pode fechar de fora
    d.showModal();
  });
}

export const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

// ── ícones (SVG estático, nunca com dado de cliente) ──
const ICONES = {
  carteira: '<path d="M3 12l9-8 9 8"/><path d="M5 10v10h14V10"/>',
  robos: '<rect x="4" y="7" width="16" height="12" rx="3"/><path d="M12 3v4M9 12h.01M15 12h.01M9 16h6"/>',
  pessoa: '<circle cx="12" cy="8" r="4"/><path d="M4 21c1.5-4 4.5-6 8-6s6.5 2 8 6"/>',
  pasta: '<path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2z"/>',
  contato: '<path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12z"/>',
  boleto: '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="M3 7l9 6 9-6"/>',
  parar: '<rect x="6" y="6" width="12" height="12" rx="2"/>',
  ok: '<path d="M5 12l5 5 9-10"/>',
};
export function icone(nome) {
  const s = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  s.setAttribute('viewBox', '0 0 24 24');
  s.setAttribute('aria-hidden', 'true');
  s.innerHTML = ICONES[nome] || '';
  return s;
}