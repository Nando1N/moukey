# Contribuindo

Valeu por querer ajudar! O MouKey ainda é pequeno, então qualquer ajuda faz diferença, principalmente **testar em outros computadores** (Linux, monitores diferentes, redes diferentes).

## Achou um problema?

Abra uma issue contando:

- o sistema dos dois computadores (ex.: Windows 11 e Ubuntu 24.04 com X11)
- o que você fez e o que aconteceu
- o arquivo `moukey.log` se tiver erro de conexão (fica em `%APPDATA%\moukey`). Ele não tem nada do que você digitou, só eventos de conexão.

## Quer mexer no código?

```
pip install -e ".[dev]"
pytest
ruff check . && ruff format --check .
```

Como as partes se conectam está em [docs/arquitetura.md](docs/arquitetura.md).

Algumas combinações que ajudam a manter o projeto fácil de ler:

- código simples, sem abstração antes da hora
- comentário só quando explica o porquê
- teste junto com a mudança, principalmente em protocolo, bordas e criptografia
- coisa específica de sistema fica em `moukey/backends/`
- dependência nova precisa de um bom motivo

PRs pequenos são revisados mais rápido. Se for algo grande, abre uma issue antes pra gente conversar.
