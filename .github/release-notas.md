Use o mesmo mouse e teclado em dois computadores na mesma rede. Baixe o `MouKey.exe`, abra nos dois computadores e confirme o código de 6 dígitos.

Os dois computadores precisam estar com a mesma versão.

### O que o MouKey faz no seu computador

Para funcionar, o programa precisa ler o mouse e o teclado e mexer neles, como qualquer programa desse tipo. Então é bom saber exatamente o que ele faz:

- acompanha a posição do mouse para saber quando ele chega na borda da tela
- fica atento ao atalho de emergência `Ctrl+Alt+Shift+Esc`, que devolve o mouse na hora
- **só manda mouse e teclado para o outro computador enquanto o controle está nele**. No resto do tempo nada sai daqui
- lê a área de transferência quando você copia algo (texto, print, imagem ou arquivo), para colar no outro computador. Dá para desligar imagens e arquivos nas Configurações
- manda tudo isso **só para o computador que você pareou**, criptografado e só dentro da rede local
- **não grava nada do que você digita**, nem em arquivo nem em log. O log só tem conexões e o tamanho dos arquivos enviados
- só roda quando você abre. Iniciar com o Windows é opcional e vem desligado

O código inteiro está aqui no repositório. Detalhes em [SECURITY.md](https://github.com/Nando1N/moukey/blob/main/SECURITY.md).

### O Windows vai avisar

O exe não tem assinatura digital (custa caro para um projeto pessoal), então o SmartScreen mostra "O Windows protegeu o computador". Clique em **Mais informações** e depois em **Executar assim mesmo**.

Alguns antivírus estranham programas que leem o teclado. Se o seu reclamar, dá para conferir que o exe é este mesmo, gerado aqui no GitHub a partir do código público:

```
Get-FileHash MouKey.exe
```

O resultado tem que ser:

```
{{SHA256}}
```

Também dá para conferir pela atestação do GitHub: `gh attestation verify MouKey.exe -R Nando1N/moukey`.

### Mudanças

Veja o [CHANGELOG](https://github.com/Nando1N/moukey/blob/{{VERSAO}}/CHANGELOG.md).

---

**English:** share one mouse and keyboard between two computers on the same network. It reads mouse, keyboard and clipboard only to send them, encrypted, to the computer you paired, and never saves what you type. The exe is unsigned, so SmartScreen will warn you (More info → Run anyway). It's built by GitHub Actions from this repo, check the SHA-256 above.
