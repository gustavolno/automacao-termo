export class ErroApi extends Error {
  constructor(msg, status, dados) { super(msg); this.status = status; this.dados = dados; }
}

export async function api(metodo, caminho, corpo) {
  const r = await fetch(caminho, {
    method: metodo,
    headers: { 'X-Central': '1', ...(corpo !== undefined ? { 'Content-Type': 'application/json' } : {}) },
    body: corpo !== undefined ? JSON.stringify(corpo) : undefined,
  });
  let dados = null;
  try { dados = await r.json(); } catch { /* sem corpo */ }
  if (!r.ok) {
    const det = dados && dados.detail;
    throw new ErroApi(typeof det === 'string' ? det : `Erro ${r.status}`, r.status, dados);
  }
  return dados;
}

export const get = (c) => api('GET', c);
export const post = (c, b = {}) => api('POST', c, b);
