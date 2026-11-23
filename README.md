<p align="center">
  <picture>
    <source media="(prefers-color-scheme: dark)" srcset="assets/logo/svg/horizontal/moukey-horizontal-fundo-escuro.svg" />
    <img src="assets/logo/svg/horizontal/moukey-horizontal-fundo-claro.svg" alt="MouKey" width="360" />
  </picture>
</p>

<p align="center"><a href="https://github.com/Nando1N/moukey/actions/workflows/testes.yml"><img src="https://github.com/Nando1N/moukey/actions/workflows/testes.yml/badge.svg" alt="testes" /></a></p>

<p align="center"><b>Um mouse, um teclado, todos os seus computadores.</b><br />Use o mesmo mouse e teclado em dois computadores, sem configurar nada.</p>

<p align="center"><img src="assets/demo/moukey-demo.webp" alt="Os dois computadores conferem o mesmo código, o cursor do PC passa para o notebook pela borda da tela, o teclado do PC digita no notebook, o texto copiado no notebook é colado no PC e um arquivo arrastado chega no outro computador" width="880" /></p>

## Como usar

**[Baixe o MouKey.exe](https://github.com/Nando1N/moukey/releases/latest)** (Windows 10 e 11). Não precisa instalar nada, e a partir da 0.3.0 ele avisa quando sai versão nova e se atualiza com um clique.

O exe não tem assinatura digital, então na primeira vez o Windows mostra "O Windows protegeu o computador". Clique em **Mais informações** e depois em **Executar assim mesmo**. O exe é gerado aqui no GitHub a partir deste código, e o hash para conferir está na página do download.

1. Abra o MouKey nos dois computadores.
2. Em qualquer um deles, clique em **Conectar** no outro computador da lista.
3. Os dois mostram um código de 6 dígitos. Se for o mesmo nos dois, clique em **Confirmar e parear** nos dois.

Pronto. Leve o mouse até a borda da tela e ele passa para o outro computador. Funciona dos dois lados: o mouse de qualquer um dos dois controla o outro.

Se o firewall perguntar, clique em **Permitir**.

Se algo travar, aperte `Ctrl+Alt+Shift+Esc` e o mouse volta na hora.

## O que já funciona

- mouse, cliques e rodinha passando pela borda da tela, nos dois sentidos
- vários monitores: a tela **Telas** mostra todos os monitores dos dois computadores no tamanho real, e você arrasta o outro computador para onde ele fica na mesa
- teclado junto, com atalhos (Ctrl+C, Ctrl+V, Alt+Tab), acento e Ç
- Ctrl+C num computador e Ctrl+V no outro, com texto, prints, imagens e arquivos (até 200 MB por vez), e histórico do que foi copiado
- mandar arquivos de um computador para o outro arrastando para a janela, escolher a pasta onde eles chegam e abrir o arquivo recebido direto na pasta
- um acha o outro sozinho na rede, sem digitar IP (e dá para digitar o IP se a rede bloquear a busca)
- reconecta sozinho quando você abre de novo ou a rede volta
- fica no ícone perto do relógio, fechar a janela não desliga
- avisa quando sai uma versão nova e se atualiza sozinho com um clique em **Atualizar agora**

Testado entre dois computadores com Windows 11, um deles com dois monitores.

### Experimental

- **Linux com X11**: manda e recebe mouse e teclado, nos dois sentidos. Os testes rodam num X11 virtual a cada mudança, mas ainda falta gente testando em computadores de verdade. Wayland ainda não funciona.
- **macOS (experimental, Mac com chip M)**: baixe o `MouKey-macos.zip` no [release](https://github.com/Nando1N/moukey/releases/latest). Manda e recebe mouse, teclado e Ctrl+C (texto, print e arquivo) com um PC Windows. Ainda ninguém testou num Mac de verdade, então pode ter coisa estranha. Detalhes logo abaixo.

Se você testar no Linux ou no Mac, conta como foi numa issue. Ajuda muito.

### macOS

O MouKey ainda não tem a assinatura paga da Apple, então o Mac avisa que não consegue verificar o app. Ele é montado pelo GitHub a partir deste código, e o SHA-256 do zip está no release.

1. Abra o `MouKey-macos.zip` e arraste o `MouKey.app` para a pasta **Aplicativos**.
2. Abra o MouKey. Vai aparecer o aviso de que a Apple não pôde verificar o app. Clique em **OK**.
3. No macOS 15, vá em **Ajustes do Sistema > Privacidade e Segurança**, role até o fim e clique em **Abrir Mesmo Assim** ao lado de "O MouKey foi bloqueado". No macOS 14, clique no MouKey com o botão direito no Finder e escolha **Abrir**.
4. Na primeira vez ele abre **Acessibilidade**. Ligue o **MouKey** na lista. Se o mouse não passar, ligue também em **Monitoramento de Entrada**, na mesma tela.
5. Se aparecer "O MouKey quer encontrar dispositivos na rede local", clique em **Permitir**.
6. Feche e abra o MouKey de novo.

O Ctrl do Windows vira o Command do Mac, então Ctrl+C num é Command+C no outro. O Option é o Alt. O atalho de emergência no Mac é **Control + Option + Shift + Esc**, porque Command + Option + Esc é o Forçar Encerrar. No Mac não tem ícone perto do relógio, fechar a janela fecha o MouKey. A atualização com um clique é só no Windows por enquanto, no Mac é baixar o zip novo.

## As telas

| | |
|---|---|
| <img src="assets/telas/dispositivos.png" alt="Tela Dispositivos com o computador conectado e os outros da rede" /> | <img src="assets/telas/pareamento.png" alt="Pedido de conexão com o código de 6 dígitos para conferir" /> |
| **Dispositivos.** Os computadores da rede aparecem sozinhos. | **Pareamento.** O mesmo código nos dois e pronto. |
| <img src="assets/telas/telas.png" alt="Tela Telas com os monitores dos dois computadores lado a lado" /> | <img src="assets/telas/area-de-transferencia.png" alt="Histórico da área de transferência com um print, arquivos e textos" /> |
| **Telas.** Arraste o outro computador para onde ele fica na mesa. | **Área de transferência.** Texto, print e arquivo, com histórico. |
| <img src="assets/telas/transferencias.png" alt="Tela Transferências com um arquivo enviando e outros concluídos" /> | <img src="assets/telas/configuracoes.png" alt="Configurações com a pasta dos arquivos recebidos e as opções de segurança" /> |
| **Transferências.** Arraste o arquivo para a janela. | **Configurações.** Pasta dos recebidos, Ctrl+C e segurança. |

## Identidade visual

<img src="assets/marca/folha-da-marca.webp" alt="Folha da marca MouKey com o logo nas versões horizontal, vertical, ícone e nome, em fundo escuro, claro, roxo, preto e branco" />

Roxo `#8B5CF6` com `#A78BFA` e `#7C3AED`, fundo `#0B0B12` e superfície `#1A1A24`. O nome é Montserrat ExtraBold e a interface usa Inter. Todas as versões do logo, em SVG e PNG, estão em [assets/logo](assets/logo).

## Segurança

O MouKey lida com mouse e teclado, então isso foi pensado desde o começo:

- tudo que passa entre os computadores é criptografado (X25519 + ChaCha20-Poly1305)
- um computador novo só conecta depois que você confirma o mesmo código de 6 dígitos nos dois
- só aceita conexões da rede local
- não grava o que você digita, nem em arquivo nem em log
- arquivos recebidos são conferidos (SHA-256) e salvos em `Downloads\MouKey` (ou na pasta que você escolher), nunca abertos sozinhos

Detalhes e como reportar um problema em [SECURITY.md](SECURITY.md).

## Limitações conhecidas

- janelas abertas como administrador no Windows não recebem o mouse de outro programa (regra do Windows)
- o cursor pode não aparecer no computador que não tem mouse físico ligado (outra regra do Windows)
- redes de empresa, faculdade ou hotel às vezes bloqueiam a busca e o contato entre aparelhos
- os dois computadores precisam estar com a mesma versão do MouKey

## Por que fiz

Tenho um PC e um notebook na mesa e cansei de ficar trocando de mouse. As opções que achei pediam IP, arquivo de configuração ou chave pra digitar, então resolvi fazer uma que fosse só abrir e clicar.

## Rodar pelo código

Precisa de Python 3.11 ou mais novo.

```
pip install -e ".[dev]"
python -m moukey            # abre a janela
pytest                      # testes
ruff check . && ruff format --check .
```

No Linux, por enquanto, é só pelo código. Para gerar um executável só para você no Windows: `pip install pyinstaller` e depois `.\scripts\build-exe.ps1`.

Como o código está organizado em [docs/arquitetura.md](docs/arquitetura.md). Quer ajudar? Veja o [CONTRIBUTING.md](CONTRIBUTING.md).

---

**English:** share one mouse and keyboard between your computers on the same network. [Download MouKey.exe](https://github.com/Nando1N/moukey/releases/latest) (unsigned, so SmartScreen will warn you: More info → Run anyway) or run it from source (`python -m moukey`) on both, click **Conectar** on one and confirm the same 6 digit code on both. Multiple monitors, shared clipboard and file transfer included. Copy text, screenshots, images or files on one and paste on the other. Windows for now, Linux (X11) works as an experiment (text only on the clipboard).

Licença MIT.
