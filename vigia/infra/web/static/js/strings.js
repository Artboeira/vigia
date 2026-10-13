// Todos os textos da interface. O núcleo envia códigos + argumentos; aqui eles viram português.

const num = new Intl.NumberFormat('pt-BR');
const dec = new Intl.NumberFormat('pt-BR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });

export const fmtNum = (n) => num.format(n);

export const STATES = {
  operacional: 'OPERACIONAL', tocando: 'TOCANDO', preparada: 'PREPARADA', estop: 'E-STOP',
  faixa: 'FAIXA ERRADA', duplicado: 'IP DUPLICADO', ocupada: 'OCUPADA', sem_controle: 'SEM CONTROLE',
  offline: 'OFFLINE',
};

export const LEVELS = { ok: 'pronta', ativo: 'em uso', alerta: 'alerta', erro: 'erro', off: 'sem sinal' };

export const GROUPS = { rede: 'REDE', laser: 'LASER', saida: 'SAÍDA', dispositivo: 'DISPOSITIVO' };

export const KEYS = {
  ip: 'IP', ultimo_sinal: 'Último sinal', sinal: 'Qualidade do sinal', placa_pc: 'Placa do PC', faixa: 'Faixa',
  conexao_tcp: 'Conexão TCP', laser: 'Laser', interlock: 'Interlock', temperatura: 'Temperatura',
  link_ethernet: 'Link Ethernet', saida: 'Saída', buffer: 'Buffer', ultimo_stream: 'Último stream',
  fonte: 'Fonte', taxa_maxima: 'Taxa máxima', firmware: 'Firmware', atualizacao: 'Atualização',
  hardware: 'Hardware', mac: 'MAC',
};

const CAUSES = {
  interlock_aberto: 'interlock aberto', temperatura_alta: 'temperatura alta',
  disparado_interlock: 'disparado pelo interlock', disparado_temperatura: 'disparado por temperatura',
  link_caiu: 'link Ethernet caiu', comando_rede: 'comando de rede',
};

const CONTROL = {
  nao_testada: 'não testada', livre: 'livre', recusada: 'recusada', sem_resposta: 'sem resposta', falha: 'falha',
};

const state = (s) => STATES[s] || s;

// cada código: texto com {0}, {1}... ou função dos argumentos
const M = {
  // motivo do estado geral
  sem_sinal: (a) => `sem sinal há ${a[0]} s — energia, cabo ou rede`,
  laser_bloqueado: (a) => 'laser bloqueado — ' + (a.length ? a.map((c) => CAUSES[c] || c).join(', ') : 'causa não informada'),
  estop_software: 'comando de software, não é falha física',
  faixa_errada: 'o computador não alcança a DAC: o IP está em outra faixa',
  ip_duplicado: 'outra DAC na rede usa o mesmo IP',
  outro_software: 'outro software está preso à DAC',
  tcp_sem_resposta: 'na rede, mas a porta TCP {0} não responde',
  transmitindo: (a) => `software transmitindo a ${fmtNum(a[0])} pps`,
  conectado_sem_stream: 'software conectado, o stream ainda não começou',
  pronta: 'pronta para receber stream',

  // valores dos parâmetros
  segundos: (a) => `${dec.format(a[0])} s`,
  medindo: 'medindo…',
  sinal_pct: '{0}% dos anúncios · {1} s',
  fora_faixa: 'fora · PC em {0}',
  na_faixa: 'ok · {0}',
  ...CONTROL,
  liberado_flag: 'liberado · flag de rede',
  estop_software_curto: 'E-STOP (software)',
  estop: 'E-STOP',
  liberado: 'liberado',
  aberto: 'ABERTO',
  disparou_fechado: 'disparou, já fechado',
  fechado: 'fechado',
  alta: 'ALTA',
  disparou_normal: 'disparou, já normal',
  normal: 'normal',
  caiu_stream: 'caiu durante o stream',
  ok: 'ok',
  tocando_pps: (a) => `tocando · ${fmtNum(a[0])} pps`,
  preparada: 'preparada',
  ociosa: 'ociosa',
  buffer: (a) => `${fmtNum(a[0])} / ${fmtNum(a[1])} · ${a[2]}%`,
  parou_estop: 'parou por E-stop',
  underflow: 'underflow (o software parou de enviar)',
  fonte_rede: 'rede', fonte_cartao: 'cartão (arquivo ILDA)', fonte_gerador: 'gerador interno',
  fonte_n: 'fonte {0}',
  pps: (a) => `${fmtNum(a[0])} pps`,
  fw_antigo: 'antigo, sem consulta',
  fw_sem_v: 'não informa a versão',
  nao_lido: (a) => `não lido (${CONTROL[a[0]] || a[0]})`,
  aguardando_parada: 'aguardando a DAC parar',
  consultando: 'consultando…',
  disponivel: '{0} disponível',
  em_dia: 'em dia',
  provavel_desatualizado: 'provavelmente desatualizado',
  hw_sw: 'hw {0} · sw {1}',

  // avisos de rede
  banner_faixa: 'DAC em {0} · PC ({1}) em {2}',
  banner_duplicado: 'IP {0} usado por mais de uma DAC',

  // registro
  ev_encontrada: '{0} encontrada em {1}',
  ev_voltou: '{0} voltou em {1}',
  ev_offline: '{0} saiu da rede',
  ev_estado: (a) => `${a[0]}: ${state(a[1])} → ${state(a[2])}`,
  ev_ip_mudou: '{0} trocou de IP: {1} → {2}',
  ev_enviando_clear: 'Clear E-Stop enviado para {0} ({1})',
  ev_clear_falhou: (a) => `Clear E-Stop em ${a[0]} falhou: ${CONTROL[a[1]] || a[1]} — feche o software de laser e tente de novo`,
  clear_limpo: '{0}: E-stop limpo',
  clear_nao_estava: '{0}: não estava em E-stop',
  clear_continua: '{0}: ACK, mas continua em E-stop',
  clear_nak_causa_ativa: '{0}: recusado — a causa continua ativa (interlock ou temperatura)',
  clear_nak_invalido: '{0}: recusado — comando inválido',
  clear_nak_buffer: '{0}: recusado — buffer cheio',
  clear_desconhecida: '{0}: resposta desconhecida (0x{1})',
  ev_nome: '{0} agora se chama {1}',
  ev_esquecida: '{0} removida da lista',
  escutando: 'escutando os anúncios na porta UDP 7654',
  porta_indisponivel: 'porta UDP 7654 indisponível ou computador sem rede',
};

export const EVENT_KINDS = {
  encontrada: 'ENCONTRADA', voltou: 'VOLTOU', offline: 'CAIU', estado: 'ESTADO', ip_mudou: 'IP',
  comando: 'COMANDO', nome: 'NOME', esquecida: 'REMOVIDA', escuta: 'ESCUTA',
};

export function t(msg) {
  if (!msg) return '';
  const { c, a = [] } = msg;
  if (c === 'raw') return String(a[0]);
  const entry = M[c];
  if (typeof entry === 'function') return entry(a);
  if (typeof entry === 'string') return entry.replace(/\{(\d)\}/g, (_, i) => (a[i] ?? ''));
  return c;
}

export function duration(seconds) {
  const s = Math.max(0, Math.floor(seconds));
  if (s < 60) return `${s} s`;
  const m = Math.floor(s / 60);
  if (m < 60) return `${m} min`;
  return `${Math.floor(m / 60)} h ${String(m % 60).padStart(2, '0')} min`;
}

export function clock(epoch) {
  return new Date(epoch * 1000).toLocaleTimeString('pt-BR', { hour12: false });
}
