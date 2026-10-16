import { h, aviso, dialogo, hojeISO } from './ui.js';
import { post } from './api.js';
import { nomeDoUsuario } from './estado.js';

const hoje = hojeISO;

// Registra um contato (ligação, WhatsApp...) com lembrete opcional. `depois` roda se salvou.
export async function registrarContato(cliente, depois) {
  const canal = h('select', null, ['Telefone', 'WhatsApp', 'E-mail', 'Presencial'].map((x) => h('option', null, x)));
  const texto = h('textarea', { rows: 3, placeholder: 'Ex.: ligou, prometeu pagar dia 20' });
  const lembrar = h('input', { type: 'date', min: hoje() });
  const ok = await dialogo({
    titulo: `Registrar contato · ${cliente.nome}`,
    corpo: [h('label', { class: 'campo' }, 'Canal', canal), h('label', { class: 'campo' }, 'O que aconteceu', texto),
      h('label', { class: 'campo' }, 'Lembrar de cobrar em', lembrar)],
    botoes: [{ rotulo: 'Cancelar', valor: false }, { rotulo: 'Registrar', valor: true, classe: 'primario' }],
  });
  if (!ok) return;
  if (!texto.value.trim()) return aviso('Escreva o que aconteceu no contato.', 'erro');
  await post(`/api/clientes/${cliente.id}/contatos`, { autor: nomeDoUsuario(), canal: canal.value, texto: texto.value, lembrar_em: lembrar.value || null });
  aviso('Contato registrado.', 'ok');
  if (depois) depois();
}
