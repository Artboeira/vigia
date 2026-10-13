// Vigia — interface. Recebe o estado completo a cada 0,5 s e atualiza o DOM no lugar
// (sem redesenhar tudo, para não perder hover, foco e edição de nome).

import { canCommand, post, subscribe } from './api.js';
import { icon, paintIcons } from './icons.js';
import { EVENT_KINDS, GROUPS, KEYS, LEVELS, STATES, clock, duration, fmtNum, t } from './strings.js';

// --- utilidades --------------------------------------------------------------
const $ = (sel, root = document) => root.querySelector(sel);
const $$ = (sel, root = document) => [...root.querySelectorAll(sel)];

function h(tag, cls, text) {
  const node = document.createElement(tag);
  if (cls) node.className = cls;
  if (text != null) node.textContent = text;
  return node;
}

function setText(node, text) {
  const value = String(text ?? '');
  if (node.textContent !== value) node.textContent = value;
}

function setAttr(node, name, value) {
  if (value == null) node.removeAttribute(name);
  else if (node.getAttribute(name) !== String(value)) node.setAttribute(name, value);
}

const store = {
  get(k) { try { return localStorage.getItem('vigia.' + k); } catch { return null; } },
  set(k, v) { try { localStorage.setItem('vigia.' + k, v); } catch { /* sem armazenamento */ } },
};

// --- estado da interface -----------------------------------------------------
const S = {
  data: null,
  sel: store.get('sel'),
  view: store.get('vista') || 'detalhe',
  connected: false,
  lastSeq: null,
  alerts: [],
  unseen: 0,
  filtro: 'todas',
  editing: null,
  logMsg: null,
  sound: store.get('som') === '1',
  sparkHover: null,
  confirmMac: null,
  labelOff: new Set(),
  keys: {},
};

const dacs = () => S.data?.dacs ?? [];
const byMac = (mac) => dacs().find((d) => d.mac === mac);
const selected = () => byMac(S.sel);
const readOnly = () => !canCommand() || !!S.data?.app?.somente_leitura;

// --- entrada -----------------------------------------------------------------
function onState(data) {
  S.data = data;
  if (!byMac(S.sel)) S.sel = data.dacs[0]?.mac ?? null;
  $('#app').classList.toggle('somente-leitura', readOnly());
  handleEvents(data.eventos);
  render();
}

function onConnection(ok) {
  S.connected = ok;
  if (S.data) { renderRail(); renderLog(); }
}

function handleEvents(events) {
  const max = events.length ? events[events.length - 1].seq : 0;
  if (S.lastSeq === null || max < S.lastSeq) { S.lastSeq = max; return; } // 1ª carga ou núcleo reiniciado
  const fresh = events.filter((e) => e.seq > S.lastSeq);
  S.lastSeq = max;
  if (fresh.length && !S.editing) S.logMsg = null; // o resultado de um comando aparece logo no rodapé
  const alerts = fresh.filter((e) => e.alerta);
  if (!alerts.length) return;
  S.alerts.push(...alerts);
  if (S.view !== 'registro') S.unseen += alerts.length;
  if (S.sound) beep();
}

// --- desenho -----------------------------------------------------------------
function render() {
  renderRail();
  renderList();
  renderDetail();
  renderAlert();
  renderLog();
  renderButtons();
  if (S.view === 'painel') renderPanel();
  if (S.view === 'registro') renderRegistro();
}

function renderRail() {
  const d = S.data;
  const placas = d.placas.length ? d.placas.map((p) => `${p.nome} ${p.ip}`).join(' · ') : 'SEM REDE';
  setText($('#rail-placas'), placas);
  setText($('#rail-relogio'), clock(d.agora));
  const flag = $('#rail-mode');
  const mode = !S.connected ? 'SEM CONEXÃO' : d.app.demo ? 'DEMONSTRAÇÃO' : readOnly() ? 'SOMENTE LEITURA' : '';
  flag.hidden = !mode;
  setText(flag, mode);
  setText($('#rail-info'), `VIGIA ${d.app.versao} · PORTA ${d.app.porta ?? ''}${d.app.rede ? ' · REDE ABERTA' : ''}`);
  const badge = $('#badge');
  badge.hidden = !S.unseen;
  setText(badge, S.unseen);
  const title = S.alerts.length ? `(${S.alerts.length}) Vigia` : 'Vigia';
  if (document.title !== title) document.title = title;
}

function levelCounts() {
  const counts = { ok: 0, ativo: 0, alerta: 0, erro: 0, off: 0 };
  dacs().forEach((d) => { counts[d.nivel] += 1; });
  return counts;
}

function fillLegend(node, withNames) {
  node.replaceChildren();
  Object.entries(levelCounts()).forEach(([nivel, n]) => {
    if (!n && !withNames) return;
    const span = h('span');
    const led = h('i', 'led led--sm');
    led.dataset.nivel = nivel;
    span.append(led, withNames ? `${n} ${LEVELS[nivel].toUpperCase()}` : String(n));
    node.append(span);
  });
}

// lista ------------------------------------------------------------------------
const rows = new Map();

function buildRow(mac) {
  const li = h('li', 'item');
  li.setAttribute('role', 'option');
  li.dataset.mac = mac;
  const txt = h('div', 'item__txt');
  txt.append(h('span', 'item__nome'), h('span', 'item__sub'));
  const pen = h('button', 'icone-btn');
  pen.innerHTML = icon('pencil', 14);
  pen.setAttribute('aria-label', 'Renomear');
  pen.dataset.cmd = '';
  li.append(h('span', 'led'), txt, h('span', 'item__estado'), pen);
  li.addEventListener('click', (e) => { if (!e.target.closest('input')) select(mac); });
  $('.item__nome', li).addEventListener('dblclick', () => startRename(mac, 'lista'));
  pen.addEventListener('click', (e) => { e.stopPropagation(); select(mac); startRename(mac, 'lista'); });
  return li;
}

function renderList() {
  const ul = $('#lista');
  const list = dacs();
  for (const [mac, li] of rows) {
    if (!byMac(mac)) { li.remove(); rows.delete(mac); }
  }
  list.forEach((d, i) => {
    let li = rows.get(d.mac);
    if (!li) { li = buildRow(d.mac); rows.set(d.mac, li); }
    if (ul.children[i] !== li) ul.insertBefore(li, ul.children[i] || null);
    setAttr(li, 'aria-selected', d.mac === S.sel ? 'true' : 'false');
    li.classList.toggle('item--off', !d.online);
    setAttr($('.led', li), 'data-nivel', d.nivel);
    setText($('.item__nome', li), d.rotulo);
    setText($('.item__sub', li), d.nome ? `${d.ip} · ${d.mac_texto.slice(9)}` : d.ip);
    const est = $('.item__estado', li);
    setText(est, STATES[d.estado] || d.estado);
    setAttr(est, 'data-nivel', d.nivel);
  });
  setText($('#contagem'), list.length);
  fillLegend($('#resumo'), false);
  $('#lista-vazia').hidden = list.length > 0;
  setText($('#vazio-texto'), S.data.escutando === false
    ? 'A porta UDP 7654 está indisponível ou o computador está sem rede. Confira a conexão; o Vigia tenta de novo a cada 5 s.'
    : 'Aguardando anúncios na porta UDP 7654. Ligue a Ether Dream na mesma rede deste computador.');
}

// detalhe ----------------------------------------------------------------------
let cardsSig = '';
const cardRows = new Map();

function buildCards(grupos) {
  const box = $('#cartoes');
  box.replaceChildren();
  cardRows.clear();
  grupos.forEach((g) => {
    const card = h('section', 'cartao');
    card.append(h('p', 'eyebrow cartao__titulo', GROUPS[g.id] || g.id));
    g.itens.forEach((it) => {
      const row = h('div', 'param');
      const led = h('span', 'led');
      const cell = h('div');
      const v = h('span', 'param__v');
      const bar = h('div', 'barra');
      const fill = h('i');
      bar.append(fill);
      cell.append(v, bar);
      row.append(led, h('span', 'param__k', KEYS[it.k] || it.k), cell);
      card.append(row);
      cardRows.set(`${g.id}.${it.k}`, { led, v, bar, fill });
    });
    box.append(card);
  });
}

function renderDetail() {
  const d = selected();
  $('#detalhe').classList.toggle('detalhe--off', !!d && !d.online);
  $('#d-lapis').hidden = !d;
  const est = $('#d-estado');
  if (!d) {
    setText($('#d-nome'), '—');
    setText($('#d-end'), '');
    setAttr($('#d-led'), 'data-nivel', 'off');
    setText(est, 'NENHUMA DAC');
    setAttr(est, 'data-nivel', 'off');
    setText($('#d-motivo'), 'Ligue a Ether Dream na mesma rede deste computador.');
    ['#d-desde', '#d-quedas', '#d-visto'].forEach((s) => setText($(s), '—'));
    $('#aviso').hidden = true;
    $('#cartoes').replaceChildren();
    cardsSig = '';
    $('#recentes').replaceChildren();
    renderSpark(null);
    return;
  }
  setText($('#d-nome'), d.rotulo);
  setText($('#d-end'), `${d.ip} · ${d.mac_texto}`);
  setAttr($('#d-led'), 'data-nivel', d.nivel);
  setText(est, STATES[d.estado] || d.estado);
  setAttr(est, 'data-nivel', d.nivel);
  setText($('#d-motivo'), t(d.motivo));
  setText($('#d-desde'), duration(S.data.agora - d.estado_desde));
  setText($('#d-quedas'), d.quedas);
  setText($('#d-visto'), duration(S.data.agora - d.visto_desde));

  const aviso = $('#aviso');
  aviso.hidden = !d.aviso;
  if (d.aviso) {
    setText($('#aviso-texto'), t(d.aviso));
    $('#aviso-pc').hidden = d.estado !== 'faixa'; // mudar o PC só resolve faixa errada
  }

  const sig = d.grupos.map((g) => `${g.id}:${g.itens.map((i) => i.k).join(',')}`).join('|');
  if (sig !== cardsSig) { buildCards(d.grupos); cardsSig = sig; }
  d.grupos.forEach((g) => g.itens.forEach((it) => {
    const row = cardRows.get(`${g.id}.${it.k}`);
    const nivel = d.online ? it.nivel : 'off';
    setAttr(row.led, 'data-nivel', nivel);
    setText(row.v, t(it.v));
    setAttr(row.v, 'data-nivel', nivel);
    row.bar.hidden = it.barra == null;
    if (it.barra != null) row.fill.style.width = `${(it.barra * 100).toFixed(1)}%`;
  }));

  renderRecent(d);
  renderSpark(d);
}

function eventRow(e, cls) {
  const li = h('li', cls);
  const led = h('span', 'led led--sm');
  led.dataset.nivel = e.nivel;
  li.append(h('span', 'hora', clock(e.em)), led, h('span', null, t(e.msg)));
  return li;
}

function renderRecent(d) {
  const key = `${S.lastSeq}|${d.mac}`;
  if (S.keys.recent === key) return;
  S.keys.recent = key;
  const list = S.data.eventos.filter((e) => e.mac === d.mac).slice(-6).reverse();
  $('#recentes').replaceChildren(...list.map((e) => eventRow(e)));
}

// gráfico de pontos por segundo: uma série, linha de 2 px, mira + dica no hover
const SPAN = 60;
const W = 300;
const H = 56;

function renderSpark(d) {
  const svg = $('#spark-svg');
  const tip = $('#spark-tip');
  svg.setAttribute('viewBox', `0 0 ${W} ${H}`);
  const now = S.data.agora;
  const pts = (d?.taxa ?? []).filter((p) => now - p[0] <= SPAN);
  let html = `<line class="spark__base" x1="0" y1="${H - 0.5}" x2="${W}" y2="${H - 0.5}"/>`;
  if (!pts.length) {
    svg.innerHTML = html;
    setText($('#spark-valor'), '—');
    tip.hidden = true;
    return;
  }
  const max = Math.max(1, ...pts.map((p) => p[1]));
  const x = (time) => W - ((now - time) / SPAN) * W;
  const y = (v) => H - 2 - (v / max) * (H - 6);
  html += `<path class="spark__linha" d="${pts.map((p, i) => `${i ? 'L' : 'M'}${x(p[0]).toFixed(1)},${y(p[1]).toFixed(1)}`).join('')}"/>`;
  const last = pts[pts.length - 1][1];
  setText($('#spark-valor'), last ? `${fmtNum(last)} PPS` : 'PARADA');
  if (S.sparkHover != null) {
    const target = now - (1 - S.sparkHover) * SPAN;
    const p = pts.reduce((a, b) => (Math.abs(b[0] - target) < Math.abs(a[0] - target) ? b : a));
    const px = x(p[0]);
    html += `<line class="spark__mira" x1="${px}" y1="0" x2="${px}" y2="${H}"/>`;
    tip.hidden = false;
    tip.style.left = `${(px / W) * 100}%`;
    setText(tip, `${fmtNum(p[1])} pps · há ${Math.round(now - p[0])} s`);
  } else {
    tip.hidden = true;
  }
  svg.innerHTML = html;
}

// painel -------------------------------------------------------------------------
const tiles = new Map();

function buildTile(mac) {
  const b = h('button', 'tile');
  b.dataset.mac = mac;
  const top = h('div', 'tile__topo');
  top.append(h('span', 'led'), h('span', 'tile__estado'));
  const info1 = h('div', 'tile__info');
  info1.append(h('span', 'tile__ip'), h('span', 'tile__sinal'));
  const info2 = h('div', 'tile__info');
  info2.append(h('span', 'tile__motivo'));
  b.append(top, h('div', 'tile__nome'), info1, info2);
  b.addEventListener('click', () => { select(mac); setView('detalhe'); });
  return b;
}

function renderPanel() {
  const grid = $('#painel');
  for (const [mac, tile] of tiles) {
    if (!byMac(mac)) { tile.remove(); tiles.delete(mac); }
  }
  dacs().forEach((d, i) => {
    let tile = tiles.get(d.mac);
    if (!tile) { tile = buildTile(d.mac); tiles.set(d.mac, tile); }
    if (grid.children[i] !== tile) grid.insertBefore(tile, grid.children[i] || null);
    setAttr(tile, 'data-nivel', d.nivel);
    setAttr(tile, 'aria-current', d.mac === S.sel ? 'true' : 'false');
    setAttr($('.led', tile), 'data-nivel', d.nivel);
    const est = $('.tile__estado', tile);
    setText(est, STATES[d.estado] || d.estado);
    setAttr(est, 'data-nivel', d.nivel);
    setText($('.tile__nome', tile), d.rotulo);
    setText($('.tile__ip', tile), d.ip);
    const sinal = d.grupos[0].itens.find((i) => i.k === 'sinal');
    setText($('.tile__sinal', tile), sinal?.barra != null ? `SINAL ${Math.round(sinal.barra * 100)}%` : '');
    setText($('.tile__motivo', tile), t(d.motivo));
  });
  setText($('#painel-contagem'), dacs().length);
  fillLegend($('#painel-legenda'), true);
}

// registro -------------------------------------------------------------------------
function filteredEvents() {
  let list = [...S.data.eventos].reverse();
  if (S.filtro === 'alertas') list = list.filter((e) => e.alerta || e.nivel === 'erro' || e.nivel === 'alerta');
  if (S.filtro === 'dac') list = list.filter((e) => e.mac === S.sel);
  return list;
}

function renderRegistro() {
  const key = `${S.lastSeq}|${S.filtro}|${S.filtro === 'dac' ? S.sel : ''}`;
  if (S.keys.registro === key) return;
  S.keys.registro = key;
  const list = filteredEvents();
  $('#registro').replaceChildren(...list.map((e) => {
    const tr = h('tr');
    tr.dataset.alerta = e.alerta ? 'true' : 'false';
    const tipo = h('td', 'tipo');
    const led = h('span', 'led led--sm');
    led.dataset.nivel = e.nivel;
    tipo.append(led, EVENT_KINDS[e.tipo] || e.tipo);
    tr.append(h('td', 'hora', clock(e.em)), tipo, h('td', null, t(e.msg)));
    return tr;
  }));
  $('#registro-vazio').hidden = list.length > 0;
}

// alerta, rodapé, botões -------------------------------------------------------------
function renderAlert() {
  const a = S.alerts[S.alerts.length - 1];
  $('#alerta').hidden = !a;
  if (!a) return;
  setText($('#alerta-texto'), `${clock(a.em)} · ${t(a.msg)}`);
  setText($('#alerta-mais'), S.alerts.length > 1 ? `+${S.alerts.length - 1} ANTERIORES` : '');
}

function setLog(text, alert = false, ms = 6000) {
  S.logMsg = { text, alert, until: Date.now() + ms };
  renderLog();
}

function renderLog() {
  const log = $('#log');
  let text = '';
  let alert = false;
  if (!S.connected && S.data) {
    text = 'sem conexão com o núcleo do Vigia — tentando de novo…';
    alert = true;
  } else if (S.logMsg && Date.now() < S.logMsg.until) {
    ({ text, alert } = S.logMsg);
  } else {
    const e = S.data?.eventos[S.data.eventos.length - 1];
    if (e) {
      text = `${clock(e.em)} · ${t(e.msg)}`;
      alert = e.nivel === 'alerta' || e.alerta;
    }
  }
  setText(log, text);
  setAttr(log, 'data-alerta', alert ? 'true' : 'false');
}

function renderButtons() {
  const d = selected();
  const btn = $('#btn-clear');
  btn.disabled = !d || d.ocupada;
  btn.classList.toggle('is-urgente', !!d && d.estado === 'estop');
}

// --- ações -----------------------------------------------------------------------
function select(mac) {
  if (S.editing && S.editing.mac !== mac) finishRename(true);
  S.sel = mac;
  store.set('sel', mac);
  if (S.data) render();
}

function move(step) {
  const list = dacs();
  if (!list.length) return;
  const i = list.findIndex((d) => d.mac === S.sel);
  const next = list[Math.min(list.length - 1, Math.max(0, i + step))];
  select(next.mac);
  rows.get(next.mac)?.scrollIntoView({ block: 'nearest' });
}

function setView(view) {
  S.view = view;
  store.set('vista', view);
  $$('.tab').forEach((tab) => setAttr(tab, 'aria-selected', tab.dataset.view === view ? 'true' : 'false'));
  $$('.vista').forEach((sec) => { sec.hidden = sec.dataset.view !== view; });
  if (view === 'registro') S.unseen = 0;
  S.keys = {};
  if (S.data) render();
}

async function clearEstop(mac, confirmed = false) {
  const d = byMac(mac);
  if (!d) { setLog('selecione uma DAC', true); return; }
  const r = await post(`/api/dacs/${mac}/limpar-estop`, { confirmado: confirmed });
  if (r.resultado === 'confirmar') {
    S.confirmMac = mac;
    setText($('#confirmar-titulo'), `${d.rotulo} pode estar tocando`);
    $('#modal-confirmar').showModal();
  } else if (r.resultado === 'ocupada') {
    setLog('aguarde: já há um comando em andamento nesta DAC', true);
  } else if (r.resultado === 'iniciado') {
    setLog(`enviando Clear E-Stop para ${d.rotulo}…`);
  } else if (r.status === 403) {
    setLog('somente leitura: comandos só no computador onde o Vigia está rodando', true);
  } else {
    setLog('não foi possível enviar o comando', true);
  }
}

function startRename(mac, where) {
  if (readOnly() || !mac) return;
  if (S.editing) finishRename(true);
  const d = byMac(mac);
  if (!d) return;
  const target = where === 'hero' ? $('#d-nome') : $('.item__nome', rows.get(mac));
  const input = h('input', 'renomear');
  input.value = d.nome || '';
  input.placeholder = d.mac_texto.replaceAll(':', '').slice(6);
  input.maxLength = 24;
  input.setAttribute('aria-label', 'Nome da DAC');
  target.hidden = true;
  target.after(input);
  input.focus();
  input.select();
  S.editing = { mac, input, target };
  input.addEventListener('keydown', (e) => {
    e.stopPropagation();
    if (e.key === 'Enter') finishRename(true);
    else if (e.key === 'Escape') { e.preventDefault(); finishRename(false); }
  });
  input.addEventListener('blur', () => finishRename(true));
  setLog('Enter salva · Esc cancela · vazio volta ao nome padrão', false, 600000);
}

async function finishRename(save) {
  const ed = S.editing;
  if (!ed) return;
  S.editing = null;
  S.logMsg = null;
  const value = ed.input.value;
  ed.input.remove();
  ed.target.hidden = false;
  if (save) {
    const r = await post(`/api/dacs/${ed.mac}/nome`, { nome: value });
    if (r.status !== 200) {
      setLog(r.erro === 'salvar_nomes' ? `não foi possível salvar os nomes: ${r.detalhe}` : 'não foi possível renomear', true);
    }
  }
  if (S.data) render();
}

// som de alerta: dois bipes curtos, só se o operador ligar
let audio;
function beep() {
  try {
    audio = audio || new AudioContext();
    [0, 0.22].forEach((offset) => {
      const osc = audio.createOscillator();
      const gain = audio.createGain();
      osc.frequency.value = 880;
      gain.gain.setValueAtTime(0.0001, audio.currentTime + offset);
      gain.gain.exponentialRampToValueAtTime(0.18, audio.currentTime + offset + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, audio.currentTime + offset + 0.16);
      osc.connect(gain).connect(audio.destination);
      osc.start(audio.currentTime + offset);
      osc.stop(audio.currentTime + offset + 0.18);
    });
  } catch { /* sem áudio */ }
}

function paintSound() {
  const b = $('#btn-som');
  b.innerHTML = icon(S.sound ? 'volume' : 'mute', 16);
  setAttr(b, 'aria-pressed', S.sound ? 'true' : 'false');
  b.title = S.sound ? 'Som de alerta ligado' : 'Som de alerta desligado';
}

// CSV com ; e BOM: abre direto no Excel em português
function downloadCsv(name, header, lines) {
  const esc = (v) => `"${String(v ?? '').replaceAll('"', '""')}"`;
  const body = [header, ...lines].map((r) => r.map(esc).join(';')).join('\r\n');
  const url = URL.createObjectURL(new Blob(['﻿' + body], { type: 'text/csv;charset=utf-8' }));
  const a = h('a');
  a.href = url;
  a.download = name;
  document.body.append(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function stamp() {
  const d = new Date();
  const p = (n) => String(n).padStart(2, '0');
  return `${d.getFullYear()}${p(d.getMonth() + 1)}${p(d.getDate())}-${p(d.getHours())}${p(d.getMinutes())}`;
}

function exportInventory() {
  if (!dacs().length) { setLog('nenhuma DAC para exportar', true); return; }
  const value = (d, k) => t(d.grupos.flatMap((g) => g.itens).find((i) => i.k === k)?.v);
  downloadCsv(`vigia-inventario-${stamp()}.csv`,
    ['nome', 'mac', 'ip', 'estado', 'firmware', 'atualizacao', 'hardware', 'placa do pc', 'faixa', 'quedas'],
    dacs().map((d) => [d.rotulo, d.mac_texto, d.ip, STATES[d.estado], value(d, 'firmware'), value(d, 'atualizacao'),
      value(d, 'hardware'), value(d, 'placa_pc'), value(d, 'faixa'), d.quedas]));
  setLog('inventário exportado');
}

function exportLog() {
  const list = filteredEvents();
  downloadCsv(`vigia-registro-${stamp()}.csv`, ['data', 'horario', 'tipo', 'mac', 'nivel', 'ocorrencia'],
    list.map((e) => [new Date(e.em * 1000).toLocaleDateString('pt-BR'), clock(e.em), EVENT_KINDS[e.tipo] || e.tipo,
      byMac(e.mac)?.mac_texto ?? '', e.nivel, t(e.msg)]));
  setLog('registro exportado');
}

// --- modais ----------------------------------------------------------------------
function openModal(name) {
  if (!S.data) return;
  if (name === 'ip') fillIpGuide();
  if (name === 'etiquetas') fillLabels();
  $(`#modal-${name}`).showModal();
}

function fillIpGuide() {
  const d = selected();
  const g = d ? d.guia : S.data.guia;
  setText($('#ip-para'), d ? d.rotulo : 'ETHER DREAM');
  const os = S.data.app.plataforma;
  setText($('#ip-passo-caminho'), os === 'darwin'
    ? 'Ajustes do Sistema → Rede → placa → Detalhes → TCP/IP → Configurar IPv4: Manualmente.'
    : os === 'win32'
      ? 'Conexões de Rede → placa → Propriedades → Protocolo IP Versão 4 (TCP/IPv4).'
      : 'Configurações de rede → placa → IPv4 → Manual.');
  setText($('#ip-pc'), g.pc ? `${g.pc.ip} · ${g.pc.mascara}` : '192.168.0.10 · 255.255.255.0');
  setText($('#ip-txt'), `ip ${g.dac.ip}\nnetmask ${g.dac.mascara}\ngateway ${g.dac.gateway}`);
  setText($('#ip-placa'), g.pc_placa ? ` (${g.pc_placa} · ${g.pc_ip})` : '');
}

async function copyIpTxt() {
  const text = `${$('#ip-txt').textContent}\n`;
  try {
    await navigator.clipboard.writeText(text);
  } catch {
    const area = h('textarea');
    area.value = text;
    document.body.append(area);
    area.select();
    document.execCommand('copy');
    area.remove();
  }
  setLog('ip.txt copiado');
}

function fillLabels() {
  const box = $('#etiquetas');
  box.replaceChildren(...dacs().map((d) => {
    const label = h('label', 'etiqueta');
    const check = h('input');
    check.type = 'checkbox';
    check.checked = !S.labelOff.has(d.mac);
    check.addEventListener('change', () => {
      if (check.checked) S.labelOff.delete(d.mac); else S.labelOff.add(d.mac);
    });
    label.append(check, h('b', null, d.rotulo), h('span', null, d.mac_texto), h('span', null, d.ip));
    return label;
  }));
  $('#etiquetas-vazio').hidden = dacs().length > 0;
  $('#etiquetas-imprimir').disabled = !dacs().length;
}

async function printLabels() {
  const macs = dacs().map((d) => d.mac).filter((m) => !S.labelOff.has(m));
  if (!macs.length) { setLog('marque ao menos uma DAC', true); return; }
  if (window.pywebview && !readOnly()) {
    // a janela nativa não imprime: a folha abre no navegador padrão
    const r = await post('/api/sistema/abrir-etiquetas', { macs });
    setLog(r.ok ? 'etiquetas abertas no navegador' : 'não foi possível abrir o navegador', !r.ok);
  } else {
    window.open(`etiquetas.html?macs=${macs.join(',')}`, '_blank');
  }
}

// --- ligações ----------------------------------------------------------------------
function bind() {
  $$('.tab').forEach((tab) => tab.addEventListener('click', () => setView(tab.dataset.view)));
  $$('[data-goto]').forEach((b) => b.addEventListener('click', () => setView(b.dataset.goto)));
  $$('[data-modal]').forEach((b) => b.addEventListener('click', () => openModal(b.dataset.modal)));
  $$('dialog').forEach((dlg) => {
    dlg.addEventListener('click', (e) => { if (e.target === dlg || e.target.closest('[data-fechar]')) dlg.close(); });
  });
  $$('.chip').forEach((chip) => chip.addEventListener('click', () => {
    S.filtro = chip.dataset.filtro;
    $$('.chip').forEach((c) => c.classList.toggle('is-on', c === chip));
    if (S.data) renderRegistro();
  }));

  $('#btn-clear').addEventListener('click', () => clearEstop(S.sel));
  $('#confirmar-ok').addEventListener('click', () => {
    $('#modal-confirmar').close();
    if (S.confirmMac) clearEstop(S.confirmMac, true);
  });
  $('#d-lapis').addEventListener('click', () => startRename(S.sel, 'hero'));
  $('#d-nome').addEventListener('dblclick', () => startRename(S.sel, 'hero'));
  $('#alerta-ok').addEventListener('click', () => { S.alerts = []; S.unseen = 0; render(); });
  $('#btn-som').addEventListener('click', () => {
    S.sound = !S.sound;
    store.set('som', S.sound ? '1' : '0');
    paintSound();
    if (S.sound) beep(); // o clique libera o áudio no navegador e serve de teste
  });
  $('#btn-inventario').addEventListener('click', exportInventory);
  $('#exportar-registro').addEventListener('click', exportLog);
  $('#ip-copiar').addEventListener('click', copyIpTxt);
  const openNet = async () => {
    const r = await post('/api/sistema/abrir-rede');
    if (!r.ok) setLog('abra os ajustes de rede pelo sistema', true);
  };
  $('#ip-abrir-rede').addEventListener('click', openNet);
  $('#aviso-pc').addEventListener('click', openNet);
  $('#etiquetas-imprimir').addEventListener('click', printLabels);
  $('#etiquetas-todas').addEventListener('click', () => { S.labelOff.clear(); fillLabels(); });

  const svg = $('#spark-svg');
  svg.addEventListener('mousemove', (e) => {
    const r = svg.getBoundingClientRect();
    S.sparkHover = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width));
    renderSpark(selected());
  });
  svg.addEventListener('mouseleave', () => { S.sparkHover = null; renderSpark(selected()); });

  document.addEventListener('keydown', (e) => {
    if (e.target.closest('input, textarea') || $('dialog[open]') || e.metaKey || e.ctrlKey || e.altKey) return;
    if (e.key === 'ArrowDown') { e.preventDefault(); move(1); }
    else if (e.key === 'ArrowUp') { e.preventDefault(); move(-1); }
    else if (e.key === 'F2') { e.preventDefault(); setView('detalhe'); startRename(S.sel, 'hero'); }
    else if (e.key === '1') setView('detalhe');
    else if (e.key === '2') setView('painel');
    else if (e.key === '3') setView('registro');
  });
}

paintIcons();
paintSound();
bind();
setView(['detalhe', 'painel', 'registro'].includes(S.view) ? S.view : 'detalhe');
subscribe(onState, onConnection);
