# Integração contínua

O workflow `.github/workflows/ci.yml` roda em cada pull request e em cada push para `main`. Ele executa os mesmos comandos do desenvolvimento local e não publica nada.

## Etapas

1. `uv sync --frozen`
2. `ruff format --check`, `ruff check`, `mypy --strict host src` e `pytest tests/host tests/conformance`
3. `kernel-tool verify-interfaces`
4. `kernel-tool toolchain`
5. `kernel-tool native-check`
6. `kernel-tool replay-corpus --all` e `kernel-tool fuzz --all --budget-hours 0.05`, que dá três minutos a cada família
7. `kernel-tool build`
8. `kernel-tool test --suite bootstrap`
9. `kernel-tool test` com as suítes `memory`, `processes`, `capabilities`, `ipc`, `scheduling`, `devices`, `vfs`, `storage`, `network`, `network-interop`, `applications`, `supervision`, `system-journey` e `release-journey`, uma etapa para cada
10. `kernel-tool repeat-boot --count 25`, `kernel-tool benchmark` e `kernel-tool soak --hours 0.05`
11. `kernel-tool fault-test` com as suítes `device-reset`, `storage-crash` e `network-faults`, uma etapa para cada. A segunda roda as 1.000 sequências padrão, a partir da seed 1
12. `kernel-tool verify-filesystem --corpus tests/faults/storage`
13. `kernel-tool verify-artifacts` e `kernel-tool reproduce-build`

Nenhuma etapa é opcional e nenhuma usa `continue-on-error`. Os relatórios de `build/qemu-riscv64/reports/` e de `build/qemu-riscv64/qualification/`, o `build/fuzz/report.json` e as falhas de `build/fuzz/findings/` são anexados ao run mesmo quando uma etapa falha. As capturas de tráfego das suítes de rede vão junto, em `reports/captures/`.

O workflow não homologa um release. As etapas 6 e 10 rodam versões curtas do fuzzing, do boot repetido e do soak, para que uma regressão apareça no pull request. Os gates de 1.000 boots, de 24 horas de soak e de 24 horas de fuzzing por família não cabem no limite de tempo de um job e rodam na máquina de quem prepara o release, como descreve `release-procedure.md`. O workflow também não roda `release-check`: sem esses gates ele terminaria sempre com falha.

`tests/host/test_ci_workflow.py` lê o workflow e reprova quando uma suíte registrada no `kernel-tool`, de cenários ou de falhas, não tem exatamente uma etapa, ou quando alguma etapa usa `continue-on-error`. Uma suíte nova entra no `kernel-tool` e no workflow na mesma mudança.

## Rede isolada

As suítes `network`, `network-interop`, `network-faults`, `applications` e `system-journey` ligam o convidado a uma estação de teste que roda no host, dentro de um namespace de rede próprio, com uma interface TAP e a pilha TCP/IP do Linux. Nada sai desse namespace: ele não tem rota para o runner nem para a internet.

Um namespace novo herda do host o encaminhamento IPv4, e um host que roda Docker costuma deixá-lo ligado. Com ele ligado, o peer responde com um erro ICMP a um pacote para fora da rede, e a suíte `network` espera silêncio. Por isso a estação desliga o encaminhamento no namespace antes de criar a interface, e não sobe quando não consegue.

O `kernel-tool` cria o namespace de três jeitos, nesta ordem: direto, quando já roda como root; em um user namespace sem privilégio, quando o host permite e `/dev/net/tun` está acessível; com `sudo -n`, quando o sudo não pede senha. O runner `ubuntu-24.04` tem sudo sem senha, e por isso o terceiro caso está disponível mesmo quando a imagem restringe user namespaces. Se nenhum dos três funciona, a etapa termina com status 3 e a anotação `Infrastructure unavailable`.

Os dois sockets que ligam o emulador à estação ficam em um diretório temporário próprio de cada enlace, e não no diretório de build. O endereço de um socket guarda 107 bytes, e abaixo de `/home/runner/work/Kernel/Kernel` o caminho do build não deixava espaço para o nome de um cenário de 27 caracteres ou mais.

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
