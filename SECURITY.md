# Segurança

O MouKey mexe com mouse e teclado, então qualquer falha aqui é séria. Se achar algo, por favor **não abra uma issue pública**. Use a aba **Security → Report a vulnerability** do repositório, que manda direto e em particular pra mim.

## Como funciona

- **Pareamento.** Cada computador tem uma chave X25519 própria, criada na primeira vez e guardada em `%APPDATA%\moukey` (ou `~/.config/moukey` no Linux). Para parear, os dois trocam as chaves e um número aleatório, e cada um mostra um código de 6 dígitos tirado disso. Um dos lados se compromete com o número dele antes de ver o do outro, a mesma ideia do pareamento numérico do Bluetooth, então alguém no meio não consegue escolher chaves até os códigos baterem. A chance de acertar no chute é de 1 em 1 milhão por tentativa. O código precisa ser confirmado **nos dois computadores**, inclusive no que clicou em Conectar, para que um estranho fingindo ser o seu notebook não consiga se aprovar sozinho. Depois de cada pergunta de um computador novo, aceita ou não, ele fica 30 segundos sem poder perguntar de novo, e se ele desligar no meio a pergunta some da tela.
- **Reconexão.** A reconexão automática só conversa com computadores já pareados e nunca vira um pareamento novo. Quando você clica num computador da lista, o MouKey confere se a chave de quem respondeu é a desse computador (o id da lista é o hash da chave), então copiar o nome e o id de outro não adianta. Esquecer um computador também tira ele da reconexão automática e derruba a conexão se ele estiver conectado.
- **Conexão.** Toda conexão combina uma chave temporária (para que gravar o tráfego hoje não ajude a ler depois) com as chaves dos dois computadores (para provar quem está do outro lado). As mensagens vão com ChaCha20-Poly1305 e um contador, então mensagem repetida ou fora de ordem é recusada.
- **Rede.** Só aceita conexões de endereços de rede privada (casa, empresa, VPN). A busca automática (mDNS e um aviso por broadcast) divulga na rede o nome do computador, o sistema, a porta e um id fixo tirado da chave. Por isso, em Wi-Fi público, deixe o MouKey fechado.
- **Janela.** Nomes e textos que vêm da rede nunca viram código na janela: tudo é escapado e a página bloqueia scripts que não sejam os dela.
- **Teclas.** Nada do que é digitado vai para disco ou log. O log (`moukey.log`) só tem eventos de conexão e de arquivos (tamanho e se deu certo, nunca o nome).
- **Arquivos.** Vão em pedaços pelo mesmo canal criptografado, são conferidos com SHA-256 no fim e salvos em `Downloads\MouKey` (ou na pasta escolhida em Configurações) com o nome limpo (sem pastas e sem caracteres invisíveis que disfarçam a extensão). Ganham a mesma marca de um download da internet, então o Windows avisa antes de rodar um programa recebido. Nunca são abertos sozinhos. O lado que recebe também limita quantos arquivos chegam ao mesmo tempo e deixa espaço livre no disco.
- **Ctrl+C de imagens e arquivos.** Prints, imagens e arquivos copiados vão pelo mesmo canal, como arquivos, e do outro lado ficam numa pasta temporária (`%TEMP%\MouKey\copiados`) só para o Ctrl+V funcionar. Essa pasta é apagada toda vez que o MouKey abre. Arquivos acima de 200 MB não vão sozinhos (o lado que recebe também confere), imagens gigantes são recusadas antes de abrir, e dá para desligar tudo em **Configurações → Prints e arquivos no Ctrl+C**, para mandar e para receber.

## Atualizações

- O MouKey pergunta ao GitHub, quando abre e a cada 6 horas, qual é a versão mais nova. Isso mostra ao GitHub o seu IP, como qualquer acesso ao site. Dá para desligar em **Configurações → Atualizações**.
- A atualização só baixa do repositório oficial (`github.com/Nando1N/moukey`), só por HTTPS, e recusa qualquer redirecionamento para fora do GitHub.
- O exe novo só é usado se o SHA-256 dele bater com o publicado no release. O exe é sempre gerado pelo GitHub Actions a partir do código público, com atestação (`gh attestation verify MouKey.exe -R Nando1N/moukey`).
- Só a versão mais nova fica disponível para baixar. As antigas são apagadas quando sai uma nova.

## O que ele não protege

- Um computador que você pareou pode mandar mouse, teclado e arquivos enquanto estiver conectado. Só pareie computadores seus. Dá para esquecer um computador em **Configurações → Computadores pareados**.
- Se alguém já tem acesso ao seu usuário no Windows, consegue copiar a chave do MouKey.
