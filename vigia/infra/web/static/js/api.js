// Conversa com o núcleo: fluxo SSE do estado e comandos POST com o token da sessão.

const token = document.querySelector('meta[name="vigia-token"]')?.content || '';

export function subscribe(onState, onConnection) {
  let source;
  const open = () => {
    source = new EventSource('/api/fluxo');
    source.onopen = () => onConnection(true);
    source.onmessage = (e) => onState(JSON.parse(e.data));
    source.onerror = () => onConnection(false); // o EventSource reconecta sozinho
  };
  open();
  return () => source.close();
}

export async function post(path, body = {}) {
  const res = await fetch(path, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', 'X-Vigia-Token': token },
    body: JSON.stringify(body),
  });
  let data = {};
  try { data = await res.json(); } catch { /* sem corpo */ }
  return { status: res.status, ...data };
}

export const canCommand = () => token !== '';
