# Changelog

Todas as mudanças relevantes do Vigia ficam registradas aqui. O formato segue o
[Keep a Changelog](https://keepachangelog.com/pt-BR/1.1.0/) e as versões seguem o
[Versionamento Semântico](https://semver.org/lang/pt-BR/): `MAIOR.MENOR.CORREÇÃO`.

A versão do app mora em um único lugar, `vigia/__init__.py` (`__version__`), e cada
versão publicada ganha uma tag `vX.Y.Z` e uma release no GitHub com o `.zip` do macOS.

## [Não lançado]

## [1.0.0] — 2026-10-12

Primeira versão. Paridade com o Ether Dream Sitter (Feitiçaria Industrial) e as melhorias abaixo.

### Funções herdadas
- Monitor passivo dos anúncios UDP 7654 das Ether Dream ED2, ED3 e ED4.
- Estados por leitura do protocolo: operacional, tocando, preparada, E-stop com causa, ocupada, sem controle, offline; flag de rede do MadMapper tratado como não falha.
- Leitura de firmware só com a DAC comprovadamente parada; aviso de atualização.
- Limpar E-Stop com confirmação quando a DAC pode estar tocando.
- Placa do PC por DAC, faixa errada, IP duplicado, guia de IP (`ip.txt` da ED4) e atalho para os ajustes de rede.
- Nomes por DAC guardados no computador; etiquetas para impressão; guia do LED.

### Adicionado
- Registro de ocorrências com horário, filtros e exportação em CSV.
- Faixa de alerta, contador na aba, título da janela e som opcional quando uma DAC cai ou entra em E-stop.
- Vista Painel com todas as DACs em blocos grandes.
- Qualidade do sinal (% de anúncios recebidos em 30 s) e contador de quedas por DAC.
- Gráfico de pontos por segundo dos últimos 60 s, barra do buffer e taxa máxima.
- Modo `--rede`: outros aparelhos acompanham em somente leitura.
- Inventário em CSV (separador `;`, compatível com Excel em português).
- Escolha de quais DACs vão para a folha de etiquetas.
- Importação dos nomes do Ether Dream Sitter original no macOS.
- Suporte a Linux.
- Atalhos de teclado: ↑ ↓, F2, 1 2 3.
- Modo `--demo` com frota simulada de seis DACs.
- Interface web local no modo escuro do design system Estúdio AB, em janela nativa (pywebview) ou no navegador.
- Empacotamento para macOS (`packaging/build_mac.sh`) e Windows (`packaging/build_windows.bat`).

### Alterado em relação ao original
- Firmware antigo sem consulta passa a aparecer como "provavelmente desatualizado", não "em dia".
- IP sugerido para o PC pula IPs em uso e usa /16 em link-local.
- Nomes ficam na pasta do usuário, com gravação atômica.

### Segurança
- Comandos só do próprio computador, com cabeçalho `Host` local e token da sessão (protege contra CSRF e DNS rebinding).

[Não lançado]: https://github.com/Artboeira/vigia/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/Artboeira/vigia/releases/tag/v1.0.0
