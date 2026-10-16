// Estado compartilhado entre as telas.
// "usuario": quem está usando este computador (negociadora ou gestão). Ainda sem senha: a Central
// só abre neste PC. Quando houver banco e login por pessoa, isto vem da sessão.
const CHAVE = 'central.usuario';

export const estado = {
  usuario: localStorage.getItem(CHAVE) || 'TODAS',
  info: null,           // /api/estado
  negociadoras: [],
};

export function definirUsuario(u) {
  estado.usuario = u;
  localStorage.setItem(CHAVE, u);
}

export const nomeDoUsuario = () =>
  estado.usuario === 'TODAS' ? 'Gestão' : (estado.negociadoras.find((n) => n.id === estado.usuario)?.nome || estado.usuario);
