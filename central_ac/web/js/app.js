import { h, limpar, icone } from './ui.js';
import { get } from './api.js';
import { estado, definirUsuario } from './estado.js';
import { carteira } from './carteira.js';
import { ficha } from './ficha.js';
import { robos } from './robos.js';

const ROTAS = [
  [/^#\/carteira(?:\/([A-Z]+))?$/, carteira, 'carteira'],
  [/^#\/cliente\/(.+)$/, ficha, 'carteira'],
  [/^#\/robos(?:\/job\/([\w-]+))?$/, robos, 'robos'],
];

const app = document.getElementById('app');
let principal, nav, limparTela = null, bannerRobo;

function montarCasca() {
  const link = (href, id, icon, texto) => h('a', { href, dataset: { id } }, icone(icon), texto);
  nav = h('nav', { class: 'nav', 'aria-label': 'Principal' },
    link('#/carteira', 'carteira', 'carteira', 'Carteira'),
    link('#/robos', 'robos', 'robos', 'Robôs'));
  bannerRobo = h('div', null);
  const seletor = h('select', { id: 'usuario', onchange: (e) => { definirUsuario(e.target.value); recarregar(); } },
    h('option', { value: 'TODAS' }, 'Gestão'),
    estado.negociadoras.map((n) => h('option', { value: n.id }, n.nome)));
  seletor.value = estado.usuario;
  principal = h('main', { id: 'principal', class: 'principal', tabindex: '-1' });
  limpar(app).append(h('div', { class: 'casca' },
    h('aside', { class: 'lateral' },
      h('a', { class: 'marca', href: '#/carteira' }, h('img', { src: 'img/logo.png', alt: '' }),
        h('span', null, h('b', null, 'A.C. COBRANÇA'), h('small', null, 'Central'))),
      nav, bannerRobo,
      h('div', { class: 'lateral-rodape' },
        h('label', null, 'Quem está usando', seletor),
        h('span', { id: 'fontes' }, ''))),
    principal));
}

function atualizarFontes() {
  const f = estado.info?.fontes;
  const el = document.getElementById('fontes');
  if (el && f) el.textContent = `Planilha de ${f.planilha_em} · conciliação de ${f.conciliacao_em || '—'}`;
}

async function sondarRobo() {
  try {
    estado.info = await get('/api/estado');
  } catch { return; }
  atualizarFontes();
  limpar(bannerRobo);
  const j = estado.info.robo_ativo;
  if (j) {
    bannerRobo.append(h('a', { class: `robo-ativo ${j.estado === 'aguardando' ? 'espera' : ''}`, href: `#/robos/job/${j.id}` },
      h('i'), j.estado === 'aguardando' ? 'Robô esperando você' : 'Robô trabalhando'));
  }
}

async function rotear() {
  if (limparTela) { try { limparTela(); } catch { /* tela já saiu */ } limparTela = null; }
  const [caminho, qs] = (location.hash || '#/carteira').split('?');
  const consulta = Object.fromEntries(new URLSearchParams(qs || ''));
  const rota = ROTAS.find(([re]) => re.test(caminho));
  if (!rota) { location.hash = '#/carteira'; return; }
  const [re, tela, menu] = rota;
  nav.querySelectorAll('a').forEach((a) => (a.dataset.id === menu ? a.setAttribute('aria-current', 'page') : a.removeAttribute('aria-current')));
  limpar(principal).append(h('div', { class: 'carregando' }, 'Carregando…'));
  try {
    const args = caminho.match(re).slice(1).map((x) => (x ? decodeURIComponent(x) : x));
    limparTela = (await tela(principal, args, consulta)) || null;
  } catch (e) {
    limpar(principal).append(h('div', { class: 'cartao vazio' }, h('strong', null, 'Não foi possível abrir esta tela'), e.message));
  }
  principal.focus({ preventScroll: true });
  window.scrollTo(0, 0);
}

const recarregar = () => rotear();

async function iniciar() {
  try {
    estado.info = await get('/api/estado');
  } catch {
    limpar(app).append(h('div', { class: 'cartao vazio' }, h('strong', null, 'A Central não respondeu'),
      'Confira se o programa está aberto (python -m central_ac) e atualize esta página.'));
    return;
  }
  estado.negociadoras = estado.info.negociadoras;
  montarCasca();
  atualizarFontes();
  window.addEventListener('hashchange', rotear);
  setInterval(sondarRobo, 4000);
  window.addEventListener('central:robo', sondarRobo);
  sondarRobo();
  rotear();
}

iniciar();
