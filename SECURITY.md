# Segurança

O MouKey mexe com mouse e teclado, então qualquer falha aqui é séria. Se achar algo, por favor **não abra uma issue pública**. Use a aba **Security → Report a vulnerability** do repositório, que manda direto e em particular pra mim.

## Como funciona

- **Pareamento.** Cada computador tem uma chave X25519 própria, criada na primeira vez e guardada em `%APPDATA%\moukey` (ou `~/.config/moukey` no Linux). Para parear, os dois trocam as chaves e um número aleatório, e cada um mostra um código de 6 dígitos tirado disso. Um dos lados se compromete com o número dele antes de ver o do outro, a mesma ideia do pareamento numérico do Bluetooth, então alguém no meio não consegue escolher chaves até os códigos baterem. A chance de acertar no chute é de 1 em 1 milhão por tentativa, e cada tentativa precisa que você confirme na tela.
- **Conexão.** Toda conexão combina uma chave temporária (para que gravar o tráfego hoje não ajude a ler depois) com as chaves dos dois computadores (para provar quem está do outro lado). As mensagens vão com ChaCha20-Poly1305 e um contador, então mensagem repetida ou fora de ordem é recusada.
- **Rede.** Só aceita conexões de endereços da rede local. A busca automática (mDNS e um aviso por broadcast) só divulga nome, sistema e porta.
- **Teclas.** Nada do que é digitado vai para disco ou log. O log (`moukey.log`) só tem eventos de conexão.
- **Arquivos.** Vão em pedaços pelo mesmo canal criptografado, são conferidos com SHA-256 no fim e salvos em `Downloads\MouKey` com o nome limpo (sem pastas). Nunca são abertos sozinhos.

## O que ele não protege

- Um computador que você pareou pode mandar mouse, teclado e arquivos enquanto estiver conectado. Só pareie computadores seus. Dá para esquecer um computador em **Configurações → Computadores pareados**.
- Se alguém já tem acesso ao seu usuário no Windows, consegue copiar a chave do MouKey.
