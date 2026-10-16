import { h, limpar, icone, aviso, dialogo } from './ui.js';
import { get, post } from './api.js';

const ESTADO = { rodando: 'Em andamento', aguardando: 'Esperando você', concluido: 'Concluído', falhou: 'Falhou', parado: 'Parado', interrompido: 'Interrompido' };
const ATIVOS = ['rodando', 'aguardando'];
const OPCOES = {
  auto_reemitir: ['Autorizar a reemissão do boleto vencido do mês', 'Cria 1 boleto avulso igual ao vencido, com vencimento daqui a 2 dias. Sem marcar, o robô pergunta antes de cada gravação.'],
  visivel: ['Mostrar o navegador', 'Para acompanhar ou resolver o reCAPTCHA quando o login pedir.'],
};
const EMAIL = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
const pilula = (estado) => h('span', { class: `pilula ${estado}` }, h('i'), ESTADO[estado] || estado);
const listaNomes = (texto) => texto.split('\n').map((x) => x.trim()).filter(Boolean);

export async function robos(raiz, [jobId], consulta) {
  return jobId ? verJob(raiz, jobId) : lancador(raiz, consulta);
}

// ───────────────────────── escolher e iniciar ─────────────────────────
async function lancador(raiz, consulta) {
  const [catalogo, historico] = await Promise.all([get('/api/robos'), get('/api/jobs')]);
  let sel = catalogo.find((t) => t.id === consulta.tarefa) || catalogo[0];
  const marcas = { auto_reemitir: false, visivel: false };
  const nomes = h('textarea', { id: 'nomes', rows: 8, placeholder: 'Cole aqui os nomes, um por linha, na ordem em que devem ser feitos', value: (consulta.nomes || '').split('|').join('\n') });
  const catalogoEl = h('div', { class: 'catalogo', role: 'group', 'aria-label': 'Tarefas dos robôs' });
  const formulario = h('section', { class: 'cartao' });

  const iniciar = async () => {
    const lista = listaNomes(nomes.value);
    if (!lista.length) { nomes.focus(); return aviso('Cole o nome de ao menos um cliente.', 'erro'); }
    const params = { nomes: lista };
    sel.campos.filter((c) => c in marcas).forEach((c) => { params[c] = marcas[c]; });
    try {
      const job = await post('/api/jobs', { tarefa: sel.id, params });
      location.hash = `#/robos/job/${job.id}`;
    } catch (e) {
      aviso(e.message, 'erro');
      if (e.status === 409 && e.dados?.job) location.hash = `#/robos/job/${e.dados.job.id}`;
    }
  };

  const desenhar = () => {
    limpar(catalogoEl).append(...catalogo.map((t) => h('button', { type: 'button', class: 'tarefa', 'aria-pressed': String(t.id === sel.id), onclick: () => { sel = t; desenhar(); } },
      h('b', null, t.titulo), h('small', null, t.go ? 'usa o Global Office' : 'sem abrir o Global Office'))));
    limpar(formulario).append(
      h('div', { class: 'cartao-topo' }, h('div', null, h('h2', null, sel.titulo), h('small', null, sel.descricao))),
      h('div', { class: 'cartao-corpo formulario' },
        h('label', { class: 'campo', for: 'nomes' }, 'Clientes (um por linha, na ordem)', nomes),
        sel.campos.filter((c) => c in marcas).map((c) => h('label', { class: 'marcar' },
          h('input', { type: 'checkbox', checked: marcas[c], onchange: (e) => { marcas[c] = e.target.checked; } }),
          h('span', null, OPCOES[c][0], h('small', null, OPCOES[c][1])))),
        sel.go ? h('p', { class: 'sub', style: { fontSize: '13px' } }, 'Só um robô roda por vez, e o login do Global Office não pode estar aberto em outro computador.') : null,
        h('div', null, h('button', { type: 'button', class: 'btn primario', onclick: iniciar }, icone('robos'), sel.id === 'conferir_mes' ? 'Conferir' : 'Executar'))));
  };
  desenhar();

  const recentes = historico.length
    ? h('ul', { class: 'lista-simples' }, historico.slice(0, 12).map((j) => h('li', null,
      h('a', { href: `#/robos/job/${j.id}`, style: { fontWeight: 600 } }, j.titulo), h('span', null, pilula(j.estado), ' ', h('small', null, j.inicio.slice(0, 16))))))
    : h('p', { style: { color: 'var(--texto-3)' } }, 'Nada executado ainda.');

  limpar(raiz).append(
    h('header', { class: 'topo' }, h('div', null, h('h1', null, 'Central de robôs'),
      h('p', null, 'Todos os programas num só lugar: escolha a tarefa, informe os clientes e acompanhe ao vivo.'))),
    h('div', { class: 'robos-layout' }, catalogoEl, h('div', { class: 'painel-robo' }, formulario,
      h('section', { class: 'cartao' }, h('div', { class: 'cartao-topo' }, h('h2', null, 'Últimas execuções')), h('div', { class: 'cartao-corpo' }, recentes)))));
}

// ───────────────────────── acompanhar um robô ─────────────────────────
async function verJob(raiz, id) {
  let desde = 0, job = null, timer = null, perguntaAberta = null, sair = false, dialogoAberto = null;
  const itens = new Map(), ordem = [], logs = [];
  const cab = h('header', { class: 'topo' });
  const barra = h('i');
  const fio = h('ol', { class: 'fio' });
  const ouro = h('div', { class: 'fio-ouro' });
  const resultado = h('div', { style: { display: 'flex', flexDirection: 'column', gap: '22px' } });
  const registro = h('div', { class: 'registro', role: 'log', tabindex: '0', 'aria-label': 'Registro do robô' });
  const contador = h('small', null, '');

  const garantir = (nome) => { if (!itens.has(nome)) { itens.set(nome, { etapa: 'Na fila', estado: 'espera', detalhe: '' }); ordem.push(nome); } };
  const processar = (evs) => {
    evs.forEach((ev) => {
      if (ev.t === 'item') { garantir(ev.nome); itens.set(ev.nome, { etapa: ev.etapa, estado: ev.estado, detalhe: ev.detalhe }); }
      else if (ev.t === 'log') logs.push({ ts: ev.ts, nivel: ev.nivel, msg: ev.msg });
      else if (ev.t === 'ask') logs.push({ ts: ev.ts, nivel: 'WARNING', msg: `Pergunta: ${ev.titulo}` });
      else if (ev.t === 'resp') logs.push({ ts: ev.ts, nivel: 'INFO', msg: `Você respondeu: ${ev.resp}` });
    });
  };

  const desenharCabecalho = () => {
    const ativo = ATIVOS.includes(job.estado);
    limpar(cab).append(
      h('div', null, h('a', { class: 'voltar', href: '#/robos' }, '← Central de robôs'),
        h('h1', null, job.titulo), h('p', null, pilula(job.estado), ` iniciado às ${job.inicio.slice(11, 16)}`)),
      h('div', { class: 'topo-acoes' }, ativo ? h('button', { type: 'button', class: 'btn perigo', onclick: async () => { await post(`/api/jobs/${id}/parar`); aviso('Pedido para parar enviado.'); } }, icone('parar'), 'Parar') : null));
  };

  const desenharLista = () => {
    const feitos = ordem.filter((n) => ['ok', 'aviso', 'falhou', 'pulado'].includes(itens.get(n).estado)).length;
    barra.style.width = ordem.length ? `${(feitos / ordem.length) * 100}%` : '0%';
    contador.textContent = ordem.length ? `${feitos} de ${ordem.length}` : '';
    limpar(fio).append(ouro, ...ordem.map((n, i) => {
      const it = itens.get(n);
      const simbolo = { ok: '✓', falhou: '!', aviso: '!', pulado: '–' }[it.estado] ?? (it.estado === 'rodando' ? '' : String(i + 1));
      return h('li', { class: `passo ${it.estado}` }, h('span', { class: 'no' }, simbolo), h('b', null, n), h('span', { class: 'etapa' }, it.etapa),
        it.detalhe ? h('span', { class: 'detalhe' }, it.detalhe) : null);
    }));
    requestAnimationFrame(() => {   // o fio dourado acende até o último passo concluído
      const feitosEl = [...fio.querySelectorAll('.passo.ok, .passo.aviso, .passo.falhou, .passo.pulado')];
      const ultimo = feitosEl[feitosEl.length - 1];
      ouro.style.height = ultimo ? `${ultimo.offsetTop + 24}px` : '0px';
    });
  };

  const desenharRegistro = () => {
    const rolar = registro.scrollTop + registro.clientHeight >= registro.scrollHeight - 30;
    limpar(registro).append(...logs.slice(-400).map((l) => h('div', { class: l.nivel }, h('time', null, l.ts), l.msg)));
    if (rolar) registro.scrollTop = registro.scrollHeight;
  };

  const perguntar = async (p) => {
    perguntaAberta = p.id;
    dialogoAberto = {};
    const resp = await dialogo({
      titulo: p.titulo, corpo: [h('pre', null, p.texto)], largura: 'min(640px, calc(100vw - 32px))', ref: dialogoAberto,
      // com o diálogo aberto o botão Parar da página fica inacessível: ele também está aqui
      botoes: [...p.opcoes.map((o, i) => ({ rotulo: o, valor: o, classe: i === 0 ? 'primario' : '' })), { rotulo: 'Parar o robô', valor: '__parar__', classe: 'perigo' }],
    });
    dialogoAberto = null;
    if (resp === null) return;              // fechado de fora (o robô já seguiu em frente)
    try {
      if (resp === '__parar__') { await post(`/api/jobs/${id}/parar`); aviso('Pedido para parar enviado.'); }
      else await post(`/api/jobs/${id}/resposta`, { pergunta: p.id, resposta: resp });
    } catch (e) { aviso(e.message, 'erro'); }
  };

  const finalizar = () => {
    limpar(resultado);
    const r = job.resultado;
    if (job.estado === 'falhou') {
      resultado.append(h('section', { class: 'cartao' }, h('div', { class: 'cartao-corpo' }, h('strong', null, 'O robô parou com erro. '), r?.erro || 'Veja o registro abaixo.')));
    } else if (job.estado === 'concluido' && job.tarefa === 'conferir_mes') {
      resultado.append(planoEnvio(r));
    } else if (job.estado === 'concluido' && r?.itens) {
      resultado.append(resumoItens(job, r));
    } else if (job.estado === 'parado') {
      resultado.append(h('section', { class: 'cartao' }, h('div', { class: 'cartao-corpo' }, 'O robô foi parado. Nada foi gravado pela metade; o que já terminou está nos passos acima.')));
    }
  };

  let falhas = 0;
  const atualizar = async () => {
    if (sair) return;
    let r;
    try {
      r = await get(`/api/jobs/${id}?desde=${desde}`);
      if (falhas) { falhas = 0; aviso('Conexão com a Central restabelecida.', 'ok'); }
    } catch (e) {
      if (job === null) throw e;           // primeira leitura: o roteador mostra o erro
      if (++falhas === 3) aviso('Sem conexão com a Central. Tentando de novo… (o robô continua rodando)', 'erro');
      if (!sair) timer = setTimeout(atualizar, Math.min(8000, 800 * falhas));
      return;
    }
    if (sair) return;
    const primeira = job === null;
    job = r;
    desde += r.eventos_novos.length;
    if (primeira) (r.params.nomes || (r.params.itens || []).map((i) => i.nome) || []).forEach(garantir);
    const novos = r.eventos_novos.length > 0;
    processar(r.eventos_novos);
    desenharCabecalho();
    if (novos || primeira) { desenharLista(); desenharRegistro(); }
    if (r.estado !== 'aguardando' && dialogoAberto) { dialogoAberto.fechar?.(); dialogoAberto = null; }   // o robô seguiu/terminou
    if (ATIVOS.includes(r.estado)) {
      if (r.estado === 'aguardando' && r.pergunta && r.pergunta.id !== perguntaAberta) perguntar(r.pergunta);
      timer = setTimeout(atualizar, 800);
    } else { finalizar(); window.dispatchEvent(new Event('central:robo')); }
  };

  limpar(raiz).append(cab,
    h('section', { class: 'cartao' }, h('div', { class: 'cartao-topo' }, h('h2', null, 'Andamento'), contador),
      h('div', { class: 'cartao-corpo', style: { display: 'flex', flexDirection: 'column', gap: '16px' } }, h('div', { class: 'progresso' }, barra), fio)),
    resultado,
    h('details', { class: 'cartao', open: false }, h('summary', { style: { padding: '0 24px' } }, 'Registro detalhado do robô'),
      h('div', { class: 'cartao-corpo' }, registro)));
  await atualizar();
  return () => { sair = true; clearTimeout(timer); dialogoAberto?.fechar?.(); };
}

// ───────────────────────── plano de envio (aprovar antes de enviar) ─────────────────────────
function planoEnvio(res) {
  const linhas = res.itens.map((i) => ({ ...i, marcado: i.marcar, texto: i.emails.join(', ') }));
  const marcas = { auto_reemitir: false, visivel: false };
  const resumo = h('span', null);
  const botao = h('button', { type: 'button', class: 'btn primario', onclick: () => enviar() }, icone('boleto'), 'Enviar');
  const atualizar = () => {
    const sel = linhas.filter((l) => l.marcado && !l.bloqueado);
    const go = sel.filter((l) => l.baixar).length;
    resumo.textContent = `${sel.length} marcado${sel.length === 1 ? '' : 's'}` + (go ? ` · o Global Office abrirá para ${go} (boleto ausente ou vencido)` : '');
    botao.disabled = sel.length === 0;
    limpar(botao).append(icone('boleto'), `Enviar ${sel.length} e-mail${sel.length === 1 ? '' : 's'}`);
  };
  const enviar = async () => {
    const itens = [];
    for (const l of linhas.filter((x) => x.marcado && !x.bloqueado)) {
      const emails = l.texto.split(/[,;\s]+/).map((e) => e.trim().toLowerCase()).filter(Boolean);
      if (!emails.length || emails.some((e) => !EMAIL.test(e))) { aviso(`E-mail inválido para ${l.nome}.`, 'erro'); return; }
      itens.push({ nome: l.nome, emails, baixar: l.baixar, pasta: l.pasta, reenviar: !!l.reenviar });
    }
    try {
      const job = await post('/api/jobs', { tarefa: 'enviar_mes', params: { itens, mes_ref: res.mes_ref, ...marcas } });
      location.hash = `#/robos/job/${job.id}`;
    } catch (e) { aviso(e.message, 'erro'); }
  };

  const corpo = h('tbody', null, linhas.map((l) => h('tr', { class: 'plano' },
    h('td', { style: { width: '44px' } }, h('input', { type: 'checkbox', checked: l.marcado, disabled: l.bloqueado, 'aria-label': `Enviar para ${l.nome}`,
      style: { width: '18px', height: '18px', accentColor: 'var(--ouro-escuro)' },
      onchange: async (e) => {
        const caixa = e.target;
        l.marcado = caixa.checked;
        l.reenviar = false;
        if (caixa.checked && l.ja_enviado) {     // repetir um envio é uma escolha explícita, não um efeito colateral de marcar a linha
          const certo = await dialogo({ titulo: 'Enviar de novo?', botoes: [{ rotulo: 'Não enviar', valor: false }, { rotulo: 'Reenviar', valor: true, classe: 'primario' }],
            corpo: [h('p', null, `${l.nome} já recebeu o boleto deste mês. Reenviar manda outro e-mail com o mesmo boleto.`),
              h('pre', null, l.alertas.filter((a) => a.msg.includes('já foi enviado')).map((a) => a.msg).join('\n'))] });
          if (!certo) { caixa.checked = false; l.marcado = false; } else l.reenviar = true;
        }
        atualizar();
      } })),
    h('td', null, h('b', null, l.nome), h('div', { class: 'avisos' }, l.alertas.map((a) => h('span', { class: `ficha-aviso ${a.nivel}` }, a.msg)))),
    h('td', null, l.arquivos.length ? `${l.arquivos.length} arquivo${l.arquivos.length === 1 ? '' : 's'}` : 'sem boleto do mês', l.baixar ? h('span', { class: 'sub' }, 'será baixado/reemitido') : null),
    h('td', null, h('input', { class: 'entrada', value: l.texto, disabled: l.bloqueado, 'aria-label': `E-mails de ${l.nome}`, placeholder: 'e-mail do cliente', oninput: (e) => { l.texto = e.target.value; } })))));

  const sec = h('section', { class: 'cartao' },
    h('div', { class: 'cartao-topo' }, h('div', null, h('h2', null, `Plano de envio · boleto de ${res.mes}`),
      h('small', null, 'Itens com aviso amarelo vêm desmarcados: confira e marque se estiver certo. Você pode corrigir o e-mail na própria linha.'))),
    h('div', { class: 'tabela-rolagem' }, h('table', null, h('thead', null, h('tr', null,
      h('th', null, h('span', { class: 'so-leitor' }, 'Enviar')), h('th', null, 'Cliente'), h('th', null, `Boleto de ${res.mes}`), h('th', null, 'E-mail'))), corpo)),
    h('div', { class: 'rodape-plano' }, h('div', null,
      Object.keys(marcas).map((k) => h('label', { class: 'marcar' }, h('input', { type: 'checkbox', onchange: (e) => { marcas[k] = e.target.checked; } }), h('span', null, OPCOES[k][0], h('small', null, OPCOES[k][1])))),
      h('small', { style: { color: 'var(--texto-3)' } }, resumo)), botao));
  atualizar();
  return sec;
}

// ───────────────────────── resumo de uma execução ─────────────────────────
function resumoItens(job, r) {
  const linhas = r.itens.map((i) => {
    const estado = i.estado || (i.ok ? 'ok' : (i.erro ? 'falhou' : 'aviso'));
    const texto = i.erro || (i.estado === 'enviado' ? `enviado para ${(i.para || []).join(', ')}` : i.baixados != null ? `${i.baixados} boleto(s) baixado(s)${i.reemitido?.length ? ' · vencido reemitido para ' + i.reemitido[0] : ''}${i.acordo ? ' · acordo ' + i.acordo : ''}` : '');
    return { nome: i.nome, estado, texto };
  });
  const classe = { ok: 'ok', enviado: 'ok', falhou: 'risco', aviso: 'atencao', pulado: 'neutro' };
  const rotulo = { ok: 'Pronto', enviado: 'Enviado', falhou: 'Não feito', aviso: 'Conferir', pulado: 'Pulado' };
  const copiar = async () => {
    const t = linhas.map((l) => `${l.nome}: ${rotulo[l.estado] || l.estado}${l.texto ? ' (' + l.texto + ')' : ''}`).join('\n');
    try { await navigator.clipboard.writeText(t); aviso('Resumo copiado.', 'ok'); } catch { aviso('Não consegui copiar; selecione o texto.', 'erro'); }
  };
  const prontos = (r.nomes || []);
  return h('section', { class: 'cartao' },
    h('div', { class: 'cartao-topo' }, h('h2', null, 'Resultado'),
      h('div', { class: 'topo-acoes' }, h('button', { type: 'button', class: 'btn pequeno', onclick: copiar }, 'Copiar resumo'),
        prontos.length && job.tarefa !== 'enviar_mes' ? h('a', { class: 'btn ouro', href: `#/robos?tarefa=conferir_mes&nomes=${encodeURIComponent(prontos.join('|'))}` }, icone('boleto'), 'Conferir e enviar o boleto do mês') : null)),
    h('div', { class: 'tabela-rolagem' }, h('table', null, h('thead', null, h('tr', null, h('th', null, 'Cliente'), h('th', null, 'Resultado'), h('th', null, 'Detalhe'))),
      h('tbody', null, linhas.map((l) => h('tr', null, h('td', null, h('b', null, l.nome)), h('td', null, h('span', { class: `selo ${classe[l.estado] || 'neutro'}` }, rotulo[l.estado] || l.estado)), h('td', null, l.texto || '—')))))));
}
