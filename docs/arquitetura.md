# Como o MouKey funciona por dentro

Tudo é Python. A janela é HTML e CSS dentro de uma janela de verdade (pywebview), e o resto roda em threads no mesmo processo.

```
moukey/
  webapp.py      abre a janela, liga a página ao core e cuida da bandeja
  core.py        o estado do app: quem está na rede, conectar, parear, reconectar
  ui/            a página (index.html, style.css com as cores da marca, app.js)
  tray.py        ícone perto do relógio

  discovery.py   acha os outros computadores (mDNS + broadcast UDP de reserva)
  session.py     abre uma conexão: chaves, pareamento se precisar, hello
  pairing.py     código de 6 dígitos
  channel.py     canal criptografado em cima do socket
  wire.py        cada mensagem vai com o tamanho na frente
  protocol.py    os tipos de mensagem e a validação de tudo que chega

  remote.py      a conexão rodando: mouse e teclado nos dois sentidos, clipboard, arquivos
  edges.py       geometria das telas: onde o mouse sai e onde entra do outro lado
  clipboard.py   copiar e colar entre os computadores
  files.py       envio de arquivos em pedaços, com conferência no fim

  backends/      tudo que depende do sistema
    windows.py   captura com hooks do Windows, emulação com SendInput, monitores
    linux_x11.py só recebe por enquanto (XTest)
    scancodes.py nomes das teclas pela posição, para o layout de cada lado valer
```

## O caminho do mouse

1. O hook do Windows vê o cursor encostar numa borda (`backends/windows.py`).
2. `edges.cross()` olha se tem uma tela do outro computador encostada ali, no mapa da tela **Telas**.
3. Se tiver, o cursor daqui fica parado no meio da tela e o hook passa a mandar só o quanto o mouse andou.
4. Do outro lado, `remote.run_link()` move o cursor de verdade. Quando ele empurra uma borda que dá de volta numa tela daqui, manda `leave` com a posição, e o controle volta.

Os dois lados rodam o mesmo `run_link`, por isso qualquer um dos dois pode mandar.

## O mapa das telas

Cada computador conhece os próprios monitores (coordenadas do sistema, um monitor à esquerda do principal tem x negativo). Os monitores do outro ficam guardados nas coordenadas dele mais um deslocamento (`offset`) que diz onde eles ficam na mesa. Quem clica em Conectar manda esse deslocamento para o outro (`layout`), assim os dois enxergam a mesma mesa.
