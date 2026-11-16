# Integração contínua

O workflow `.github/workflows/ci.yml` roda em cada pull request e em cada push para `main`. Ele executa os mesmos comandos do desenvolvimento local e não publica nada.

## Etapas

1. `uv sync --frozen`
2. `ruff format --check`, `ruff check`, `mypy --strict host src` e `pytest tests/host tests/conformance`
3. `kernel-tool toolchain`
4. `kernel-tool native-check`
5. `kernel-tool build`
6. `kernel-tool test --suite bootstrap`
7. `kernel-tool test` com as suítes `memory`, `processes`, `capabilities`, `ipc`, `scheduling`, `devices`, `vfs` e `storage`, uma etapa para cada
8. `kernel-tool fault-test` com as suítes `device-reset` e `storage-crash`, uma etapa para cada. A segunda roda as 1.000 sequências padrão, a partir da seed 1
9. `kernel-tool verify-filesystem --corpus tests/faults/storage`
10. `kernel-tool verify-artifacts --reproduce`

Nenhuma etapa é opcional e nenhuma usa `continue-on-error`. Os relatórios de `build/qemu-riscv64/reports/` são anexados ao run mesmo quando uma etapa falha.

## Como ler o resultado

| Resultado | Sinal |
| --- | --- |
| Sucesso | Todas as etapas terminam com status 0 |
| Falha | Uma etapa termina com status diferente de 0; nas etapas do `kernel-tool`, a anotação é `Check failed` |
| Infraestrutura indisponível | Uma etapa do `kernel-tool` termina com status 3 e a anotação é `Infrastructure unavailable` |

O `kernel-tool` usa o status 3 quando não consegue obter ou executar uma ferramenta fixada, por exemplo um download que falha. O script `.github/scripts/classify-exit.sh` transforma o status em anotação e em uma linha do resumo do run, e devolve o mesmo status. O job fica vermelho nos dois casos: infraestrutura indisponível não conta como aprovação.

As etapas de formatação, lint, tipos e pytest não passam pelo script, porque essas ferramentas dão outro significado ao status 3.

## Ambiente fixado

| Item | Versão |
| --- | --- |
| Runner | `ubuntu-24.04` |
| uv | 0.13.5 |
| Python | 3.13, de `.python-version` |
| Toolchain do convidado | `toolchain.lock.toml`, conferida por hash. A chave do cache é a hash desse arquivo |

As actions são referenciadas pelo SHA do commit:

| Action | Versão | Commit |
| --- | --- | --- |
| `actions/checkout` | v4.2.2 | `11bd71901bbe5b1630ceea73d27597364c9af683` |
| `astral-sh/setup-uv` | v6.8.0 | `d0cc045d04ccac9d8b7881df0226f9e82c39688e` |
| `actions/cache` | v4.2.4 | `0400d5f644dc74513175e3cd8d07132dd4860809` |
| `actions/upload-artifact` | v4.6.2 | `ea165f8d65b6e75b540449e92b4886f43607fa02` |

O workflow pede só `contents: read`.
