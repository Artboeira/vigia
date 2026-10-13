# Vigia — monitor de DACs Ether Dream

Monitor de rede para as DACs de laser **Ether Dream** (ED2, ED3, ED4), do Estúdio AB. Lista toda DAC que anuncia na rede, mostra o estado de cada uma pela leitura do protocolo, avisa sobre faixa de IP errada e IP duplicado, registra cada queda e cada E-stop com horário, e limpa o E-stop. Roda em macOS, Windows e Linux, com interface em português no modo escuro do design system do estúdio.

O ponto de partida foi o [Ether Dream Sitter — edição Feitiçaria Industrial](https://github.com/MatheusMeM/etherdream-sitter-fi). O Vigia mantém todas as funções dele e acrescenta as melhorias listadas abaixo.

## Rodar

Python 3.10 ou mais novo. O núcleo usa só a biblioteca padrão.

```bash
python3 -m vigia
```

Abre a interface no navegador (`http://127.0.0.1:7680`). Para abrir numa janela própria, instale o pywebview uma vez:

```bash
pip install pywebview
```

| Opção | O que faz |
|---|---|
| `--demo` | frota simulada com seis DACs e seus problemas típicos, sem rede |
| `--rede` | libera a interface para tablet e celular na mesma rede, **somente leitura** |
| `--sem-janela` | só o serviço, para máquina de show ou acesso remoto |
| `--porta N` | porta da interface (padrão 7680; se estiver ocupada, usa outra) |
| `--navegador` | abre no navegador mesmo com o pywebview instalado |

No macOS, aceite o pedido de **Rede Local**: sem ele o sistema esconde os anúncios das DACs.

## Funções herdadas do original

- **Passivo:** o estado vem só do anúncio UDP 7654. Na ED4 qualquer conexão TCP nova interrompe o stream, então o Vigia só conecta com a DAC comprovadamente parada (para ler o firmware) ou quando o operador manda limpar o E-stop, e pede confirmação se ela puder estar tocando.
- **Estados:** operacional, tocando, preparada, E-stop com a causa (interlock, temperatura, link, comando de rede), ocupada, sem controle, offline. O flag de rede que o MadMapper deixa ligado durante o stream não aparece como falha.
- **Rede:** placa do PC que recebe cada DAC, faixa errada, IP duplicado, atalho para os ajustes de rede e guia para trocar o IP da ED4 por `ip.txt`.
- **Nomes** por DAC, guardados no computador (duplo clique, F2 ou o lápis).
- **Etiquetas** com nome, MAC e IP para imprimir; **guia do LED** da ED4; versão do firmware e aviso de atualização.

## Melhorias

| | Original | Vigia |
|---|---|---|
| Histórico | uma linha de status, sobrescrita a cada mensagem | **registro** com horário de tudo: DAC encontrada, caiu, voltou, trocou de IP, mudou de estado, resultado de cada comando; filtros e exportação em CSV |
| Alerta | nenhum | **faixa de alerta** quando uma DAC cai ou entra em E-stop, contador na aba, título da janela e **som** opcional |
| Visão geral | só a lista lateral | aba **Painel** com todas as DACs em blocos grandes, legível de longe; E-stop vira bloco sólido em ember |
| Qualidade do sinal | só "último sinal há X s" | **% dos anúncios recebidos** nos últimos 30 s: mostra Wi-Fi ruim ou switch descartando broadcast antes da DAC cair; contador de **quedas** por DAC |
| Saída | texto do buffer | **gráfico de pontos por segundo** dos últimos 60 s, barra do buffer, taxa máxima da DAC |
| Acesso remoto | não | `--rede`: tablet no FOH acompanha tudo; comandos só no computador do Vigia |
| Firmware antigo | mostrava "em dia" para firmware antigo sem consulta | "provavelmente desatualizado" |
| IP sugerido para o PC | sempre `.10` (ou `.11`) e /24 | pula IPs em uso e usa /16 em link-local (169.254) |
| Inventário | não | CSV com nome, MAC, IP, firmware, placa e quedas, para rider técnico (separador `;`, abre direto no Excel) |
| Etiquetas | todas, sempre | escolhe quais DACs vão para a folha |
| Nomes | arquivo ao lado do .exe (falha em Arquivos de Programas) | pasta do usuário, gravação atômica; **importa** os nomes do Sitter original no macOS |
| Linux | não | sim (`ip addr` + `IP_PKTINFO`) |
| Teclado | F2 | ↑ ↓ seleciona, F2 renomeia, 1 2 3 trocam a vista |
| Código | um arquivo de 1.260 linhas com tradução e cor dentro da regra de negócio | camadas separadas (abaixo), 37 testes sem rede, simulador embutido |

## Arquitetura

As dependências apontam para dentro: o domínio não conhece rede, arquivo, idioma nem cor.

```
vigia/
  domain/        protocolo (bytes ↔ valores), entidade DAC, saúde e leituras (códigos, não textos),
                 regras de rede (faixa, duplicado, sugestões de IP), tabela de firmware
  application/   ports.py: contratos (relógio, porta de controle, placas, nomes, ações do sistema)
                 monitor.py: caso de uso central — anúncios, ticks, leitura segura de firmware,
                 Clear E-Stop, nomes, registro de ocorrências, retrato da frota
  adapters/      UDP 7654, TCP 7765, placas por sistema, nomes em JSON, simulador, presenter JSON
  infra/         relógio do app (tick 0,5 s, rede a cada 5 s), servidor HTTP + SSE, interface web
  main.py        raiz de composição
```

A interface recebe o estado inteiro por Server-Sent Events a cada 0,5 s e traduz os códigos em `static/js/strings.js` — todo texto da interface está nesse arquivo.

**Segurança.** O servidor escuta só em `127.0.0.1`. Comandos exigem cliente local, cabeçalho `Host` local e o token da sessão: uma página qualquer aberta no navegador não consegue disparar um Clear E-Stop no localhost, nem por DNS rebinding. Com `--rede`, outros aparelhos só leem.

## Arquivos

| | macOS | Windows | Linux |
|---|---|---|---|
| Nomes | `~/Library/Application Support/Vigia/nomes.json` | `%APPDATA%\Vigia\nomes.json` | `~/.config/vigia/nomes.json` |
| Log | `~/Library/Logs/Vigia/vigia.log` | `%LOCALAPPDATA%\Vigia\logs\vigia.log` | `~/.local/state/vigia/vigia.log` |

## Testes

```bash
python3 -m unittest discover -s tests -t .
```

## Gerar o aplicativo

- macOS: `bash packaging/build_mac.sh` → `dist/Vigia.app` e um .zip. Assinatura ad-hoc, sem notarização: na primeira vez, clique com o botão direito → Abrir.
- Windows: `packaging\build_windows.bat` → `dist\Vigia.exe`.

## Pendências

- **Fonte:** a Neue Haas Grotesk Display vem como *trial* da Linotype no design system. Antes de distribuir o aplicativo fora do estúdio, troque por uma licença válida.
- **Hardware:** o protocolo, os estados e o Clear E-Stop foram validados com o simulador e com os mesmos casos de teste do original; falta rodar contra uma ED4 de verdade e no Windows/Linux reais.
- **Cores do guia do LED:** são as cores físicas do LED da placa (documentação de hardware), a única exceção à paleta.
- **Firmware:** a tabela de versões mais novas (`domain/firmware.py`) é manual, como no original.

## Licença

GPL-3.0 — veja [LICENSE](LICENSE). Derivado do Ether Dream Sitter (Feitiçaria Industrial, 2026), por sua vez derivado do `sitter` do [j4cDAC](https://github.com/j4cbo/j4cDAC), Copyright 2012 Jacob Potter. Protocolo: [ether-dream.com/protocol.html](https://ether-dream.com/protocol.html). Ícones: [Lucide](https://lucide.dev) (ISC).

Ether Dream é marca de seus respectivos donos; este projeto não tem vínculo com eles.
