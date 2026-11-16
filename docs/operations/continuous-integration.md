# Integração contínua

O workflow `.github/workflows/ci.yml` roda em cada pull request e em cada push para `main`. Ele executa os mesmos comandos do desenvolvimento local e não publica nada.

## Etapas

1. `uv sync --frozen`
2. `ruff format --check`, `ruff check`, `mypy --strict host src` e `pytest tests/host tests/conformance`
3. `kernel-tool toolchain`
4. `kernel-tool native-check`
5. `kernel-tool build`
6. `kernel-tool test --suite bootstrap`
7. `kernel-tool test` com as suítes `memory`, `processes`, `capabilities`, `ipc`, `scheduling`, `devices`, `vfs`, `storage`, `network`, `network-interop`, `applications`, `supervision` e `system-journey`, uma etapa para cada
8. `kernel-tool fault-test` com as suítes `device-reset`, `storage-crash` e `network-faults`, uma etapa para cada. A segunda roda as 1.000 sequências padrão, a partir da seed 1
9. `kernel-tool verify-filesystem --corpus tests/faults/storage`
10. `kernel-tool verify-artifacts --reproduce`

Nenhuma etapa é opcional e nenhuma usa `continue-on-error`. Os relatórios de `build/qemu-riscv64/reports/` são anexados ao run mesmo quando uma etapa falha. As capturas de tráfego das suítes de rede vão junto, em `reports/captures/`.

`tests/host/test_ci_workflow.py` lê o workflow e reprova quando uma suíte registrada no `kernel-tool`, de cenários ou de falhas, não tem exatamente uma etapa, ou quando alguma etapa usa `continue-on-error`. Uma suíte nova entra no `kernel-tool` e no workflow na mesma mudança.

## Rede isolada

As suítes `network`, `network-interop`, `network-faults`, `applications` e `system-journey` ligam o convidado a uma estação de teste que roda no host, dentro de um namespace de rede próprio, com uma interface TAP e a pilha TCP/IP do Linux. Nada sai desse namespace: ele não tem rota para o runner nem para a internet.

O `kernel-tool` cria o namespace de três jeitos, nesta ordem: direto, quando já roda como root; em um user namespace sem privilégio, quando o host permite e `/dev/net/tun` está acessível; com `sudo -n`, quando o sudo não pede senha. O runner `ubuntu-24.04` tem sudo sem senha, e por isso o terceiro caso está disponível mesmo quando a imagem restringe user namespaces. Se nenhum dos três funciona, a etapa termina com status 3 e a anotação `Infrastructure unavailable`.

O sudo só inicia a estação. Build, QEMU e o resto do `kernel-tool` continuam com o usuário do runner. O workflow não instala pacotes para isso e não muda as permissões do job.

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
