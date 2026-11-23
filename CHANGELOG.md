# Mudanças

## 0.2.2

- segurança: o código de pareamento agora é confirmado nos dois computadores, a reconexão automática nunca faz um pareamento novo e o MouKey confere se quem respondeu é mesmo o computador clicado
- segurança: nomes vindos da rede não conseguem mais rodar código na janela
- segurança: o lado que recebe limita tamanho, quantidade e espaço em disco, recusa imagens gigantes e marca os arquivos recebidos como vindos de fora
- desligar Prints e arquivos no Ctrl+C também para de receber
- esquecer um computador tira ele da reconexão automática

## 0.2.1

- um print feito com Win+Shift+S ia duas vezes para o outro computador, agora vai uma

## 0.2.0

- Ctrl+C e Ctrl+V de prints, imagens e arquivos entre os computadores, não só texto (arquivos até 200 MB por vez)
- o histórico da área de transferência mostra a imagem e os arquivos copiados
- escolher a pasta onde chegam os arquivos recebidos
- botão Mostrar na pasta no arquivo recebido, e aviso perto do relógio quando ele chega
- a tela de Configurações não fica mais com as seções umas em cima das outras
- versão nova do protocolo, os dois computadores precisam estar na 0.2.0

## 0.1.2

- botões laterais do mouse (voltar e avançar) funcionam no outro computador
- a janela não trava mais quando a busca na rede demora para responder
- o log mostra quando um arquivo não foi enviado e por quê (sem o nome do arquivo)

## 0.1.1

- se o Windows não tiver o WebView2, o MouKey avisa e oferece baixar em vez de abrir uma janela quebrada

## 0.1.0

- os dois computadores controlam um ao outro, não importa quem clicou em Conectar
- vários monitores: a tela Telas mostra todos no tamanho real e dá para arrastar o outro computador
- conectar pelo IP quando a rede esconde o outro computador
- Linux com X11 manda e recebe mouse e teclado (experimental)
- mandar arquivos entre os computadores
- histórico da área de transferência
- ícone na bandeja, abrir de novo só mostra a janela
- aviso quando os dois estão com versões diferentes
- log só com eventos de conexão
- abrir o MouKey de novo não cria outra cópia, só mostra a janela
- desiste da conexão se o outro lado ficar mudo, em vez de travar
- executável gerado pelo GitHub a cada versão, com o SHA-256 no release

## 0.0.2

- primeira versão com janela e executável para Windows
- mouse, teclado e clipboard entre dois Windows
- pareamento com código de 6 dígitos e tudo criptografado
