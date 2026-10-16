import { h, limpar, brl, dataBR, quando, selo, icone, aviso } from './ui.js';
import { get, post, api } from './api.js';
import { estado, nomeDoUsuario } from './estado.js';
import { registrarContato } from './contatos.js';
import { cpfMascarado } from './ui.js';

const CLASSE_PARCELA = (s) => (s.startsWith('ADIMP') ? 'ok' : s.startsWith('INADIMP') ? 'risco' : s.startsWith('SEM') ? 'atencao' : 'neutro');
const ROTULO_PARCELA = { ok: 'paga', risco: 'vencida', atencao: 'sem registro', neutro: 'em análise' };

export async function ficha(raiz, [idCodificado]) {
  const id = decodeURIComponent(idCodificado);
  const f = await get(`/api/clientes/${encodeURIComponent(id)}`);
  const c = f.cliente;
  let cpfVisivel = false;
  const cpf = h('span', null, cpfMascarado(c.cpf, false));
  const alternarCpf = h('button', { type: 'button', class: 'btn pequeno', onclick: () => { cpfVisivel = !cpfVisivel; cpf.textContent = cpfMascarado(c.cpf, cpfVisivel); alternarCpf.textContent = cpfVisivel ? 'Ocultar CPF' : 'Mostrar CPF'; } }, 'Mostrar CPF');

  const trocarCarteira = h('select', {
    'aria-label': 'Carteira do cliente', class: 'entrada', style: { minHeight: '36px', padding: '0 10px' },
    onchange: async (e) => {
      await post('/api/atribuir', { ids: [c.id], carteira: e.target.value, por: nomeDoUsuario() });
      aviso('Carteira atualizada.', 'ok');
    },
  }, estado.negociadoras.map((n) => h('option', { value: n.id }, n.nome)), h('option', { value: 'DISTRIBUIR' }, 'A distribuir'));
  trocarCarteira.value = c.carteira;

  const dado = (rot, val) => h('div', null, h('dt', null, rot), h('dd', null, val || '—'));
  const acordo = h('dl', { class: 'dados-acordo' },
    dado('Condição', c.condicao), dado('Parcelas', c.parcelado ? `${c.qtd_parcelas}x de ${brl(c.valor_parcela)}` : '—'),
    dado('Entrada', c.valor_entrada ? `${brl(c.valor_entrada)} em ${dataBR(c.data_entrada)}` : '—'),
    dado('Valor do acordo', brl(c.valor_acordo)), dado('Primeiro vencimento', dataBR(c.primeiro_venc)),
    dado('Próximo vencimento', dataBR(c.proximo_venc)), dado('Pago até', c.pago_ate), dado('Processo', c.processo),
    dado('Acordo fechado em', c.fechado_em), dado('Envio de boletos', c.envio_boletos ? c.envio_boletos.toLowerCase() : 'ainda não marcado'));

  const parcelas = f.parcelas.length
    ? h('div', { class: 'parcelas' }, f.parcelas.map((p) => {
      const cl = CLASSE_PARCELA(p.status);
      return h('div', { class: `parcela ${cl}`, title: p.obs || '' },
        h('b', null, p.mes), h('span', null, brl(p.devido)), h('span', null, ROTULO_PARCELA[cl]), h('span', null, `vence ${dataBR(p.vencimento)}`));
    }))
    : h('div', { class: 'vazio' }, h('strong', null, 'Sem parcelas conciliadas'), 'Este cliente não está na conciliação do Sicoob.');

  // contatos
  const lista = h('ol', { class: 'linha-tempo' });
  const desenharContatos = (contatos) => {
    limpar(lista);
    if (!contatos.length) lista.append(h('li', null, h('span', { style: { color: 'var(--texto-3)' } }, 'Nenhum contato registrado ainda.')));
    contatos.forEach((x) => lista.append(h('li', null,
      h('time', { datetime: x.quando }, dataBR(x.quando)),
      h('span', null, x.texto, h('span', { class: 'meta' }, `${x.canal} · ${x.autor || 'sem autor'} · ${quando(x.quando)}`),
        x.lembrar_em ? h('label', { class: 'marcar', style: { minHeight: '32px', padding: 0 } },
          h('input', { type: 'checkbox', checked: !!x.feito, onchange: (e) => api('PATCH', `/api/contatos/${x.id}`, { feito: e.target.checked }) }),
          `Lembrar em ${dataBR(x.lembrar_em)}`) : null))));
  };
  desenharContatos(f.contatos);
  const recarregarContatos = async () => desenharContatos((await get(`/api/clientes/${encodeURIComponent(id)}`)).contatos);

  const docs = f.documentos.length
    ? h('ul', { class: 'lista-simples' }, f.documentos.map((d) => h('li', null, d.nome, h('small', null, `${d.kb} KB`))))
    : h('p', { style: { color: 'var(--texto-3)' } }, 'Pasta do cliente não encontrada no Dropbox.');
  const envios = f.emails_enviados.length
    ? h('ul', { class: 'lista-simples' }, f.emails_enviados.map((e) => h('li', null, h('span', null, e.para.join(', ')), h('small', null, `${e.data.slice(0, 10).split('-').reverse().join('/')} · ${e.arquivos} boleto(s)`))))
    : h('p', { style: { color: 'var(--texto-3)' } }, 'Nenhum e-mail de boletos enviado por esta Central.');

  limpar(raiz).append(
    h('a', { class: 'voltar', href: `#/carteira/${c.carteira}` }, '← Voltar à carteira'),
    h('header', { class: 'topo' },
      h('div', null, h('div', null, selo(c.status), c.dias_atraso ? h('span', { class: 'sub', style: { display: 'inline', marginLeft: '10px' } }, `${c.dias_atraso} dias em atraso · ${brl(c.valor_pendente)} em aberto`) : null),
        h('h1', { style: { marginTop: '10px' } }, c.nome),
        h('p', { style: { display: 'flex', flexWrap: 'wrap', alignItems: 'center', gap: '10px' } }, 'CPF ', cpf, alternarCpf, h('span', null, ' · carteira'), trocarCarteira)),
      h('div', { class: 'topo-acoes' },
        h('button', { type: 'button', class: 'btn', onclick: () => registrarContato(c, recarregarContatos) }, icone('contato'), 'Registrar contato'),
        h('button', { type: 'button', class: 'btn', disabled: !f.pasta, onclick: () => post(`/api/clientes/${encodeURIComponent(id)}/abrir-pasta`).catch((e) => aviso(e.message, 'erro')) }, icone('pasta'), 'Abrir pasta'),
        h('a', { class: 'btn ouro', href: `#/robos?tarefa=conferir_mes&nomes=${encodeURIComponent(c.nome)}` }, icone('boleto'), 'Enviar boleto do mês'))),
    h('section', { class: 'cartao' }, h('div', { class: 'cartao-topo' }, h('h2', null, 'Acordo'),
      c.motivo ? h('small', null, `Conciliação: ${c.motivo}`) : null), h('div', { class: 'cartao-corpo' }, acordo)),
    h('section', { class: 'cartao' }, h('div', { class: 'cartao-topo' }, h('h2', null, 'Parcelas'),
      h('small', null, 'abril a outubro/2026, conferidas com o Sicoob e os comprovantes')), h('div', { class: 'cartao-corpo' }, parcelas)),
    h('div', { class: 'duas-colunas' },
      h('section', { class: 'cartao larga' }, h('div', { class: 'cartao-topo' }, h('h2', null, 'Histórico de contatos')), h('div', { class: 'cartao-corpo' }, lista)),
      h('section', { class: 'cartao' }, h('div', { class: 'cartao-topo' }, h('h2', null, 'Documentos'), h('small', null, `${f.boletos_na_pasta} boleto(s) na pasta BOLETOS DO ACORDO`)),
        h('div', { class: 'cartao-corpo', style: { display: 'flex', flexDirection: 'column', gap: '18px' } }, docs, h('div', null, h('h3', { style: { fontSize: '14px', marginBottom: '8px' } }, 'E-mails de boletos enviados'), envios)))));
}
