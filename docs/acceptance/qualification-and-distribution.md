# Registro de homologação: qualificação e distribuição

[English](qualification-and-distribution.en.md)

Compilação e validação do Kernel `1.0.0rc1` após as correções de primeiro uso, em Amazon Linux 2023. Os números abaixo são da execução de 17 de novembro de 2026, das 06:22:26 às 06:44:31 UTC. Os relatórios foram gerados pelas ferramentas do projeto, não por uma auditoria independente.

Dez dos doze gates passaram. O build está compilado e testado, mas **não está qualificado para release estável**: faltam o soak de 24 horas e 24 horas de fuzzing por família. `release-check` terminou com status 1, preservando `qualified: false`. A publicação deste candidato deve ser marcada como pré-release.

O [registro estruturado](amazon-linux-2023.json) guarda o ambiente, os hashes, as 28 verificações, as medições, a reprodução e o resultado dos gates. A árvore de código foi comparada byte a byte com a que executou os testes: 930 arquivos não Markdown, sem diferença. O commit de referência é `415034cc7257e668116c995d24afe8899eb7a6c6`; as traduções posteriores não alteram as imagens.

O [registro anterior](https://github.com/luas-graphicss/Kernel/blob/d851af3a8d0ab2b2c79ba2b9d1abccdb5f394739/docs/acceptance/qualification-and-distribution.md) permanece no histórico. Suas imagens `d9ac2896…` e `e8958111…` não são evidência para este build. Os ensaios históricos de assinatura e instalação continuam naquele registro; não foram repetidos nesta execução.

## Ambiente

| Item | Valor |
| --- | --- |
| Host | Amazon Linux 2023.12.20261112, Linux 6.18.56 x86_64, glibc 2.34 |
| Máquina | 2 vCPUs Intel Xeon de 2,9 GHz e aproximadamente 4 GiB de RAM |
| Convidado | QEMU 9.2.4, TCG, um hart, 256 MiB, perfil `qemu-riscv64` |
| Firmware e runtime | OpenSBI 1.5.1 e MicroPython 1.29.0 |
| Compilador do convidado | GCC 15.2.0-1, fixado em `toolchain.lock.toml` |
| Rede | Peer Linux em namespace isolado, sem rota para fora |
| Sanitizers | AddressSanitizer e UndefinedBehaviorSanitizer, com os runtimes instalados no host |

## Imagens desta execução

| Imagem | Bytes | SHA-256 |
| --- | --- | --- |
| `kernel.elf` | 1.642.912 | `efeb6d8c6fba1d0bbfb68e3b6c70ec1713fc57b220a6d73f92961fbc53076f75` |
| `kernel-selftest.elf` | 1.740.456 | `bb75b6dd173d7a50dd75d56baa51e782d3b60c6a1a647f57529e84c1461d06ca` |
| `init.img` | 433.471 | `38ce15e2e90d65c637030e660dc49de91abf7ce41614ef624e1ad42f3ca8dea0` |
| `tests.img` | 627.863 | `91acb1a8a10de6d5741c8425e399e2e48d6a2d7352e37fa97a8b0bcacffe05d3` |
| `boot.img` | 65.536 | `d676ac117840712a66ff275a6c3036c4918c562be9fb820bc790d4be7c5e7b2c` |
| `fault.img` | 74 | `12218c97e53efca26189319e060c50850fab06f93172d13e33f0b3bebe5deb96` |

Todos os relatórios de qualificação referem os mesmos hashes de `kernel.elf`, `init.img` e `boot.img`. `reproduce-build` gerou as seis imagens em dois diretórios vazios, idênticas entre si e ao build avaliado, com `SOURCE_DATE_EPOCH=1787581954`.

## Verificações executadas

Os comandos de QEMU rodaram em sequência sobre o diretório de build, sem disputar os volumes dos cenários.

| Comando | Resultado |
| --- | --- |
| `build` | Status 0; imagens geradas |
| `verify --all` | 28/28 verificações, nenhuma incompleta; aproximadamente 210 s |
| Formatação e lint, dentro de `verify` | 706 arquivos formatados; nenhuma ocorrência |
| Tipos, dentro de `verify` | 366 arquivos; nenhum erro |
| Testes do host e de conformidade | 998 testes aprovados |
| Testes nativos | 12 testes hospedados sob sanitizers e análise estática aprovados |
| QEMU | 15 suítes funcionais e 3 suítes de falha aprovadas |
| Corpus de volumes | 21 imagens com o resultado esperado |
| Interfaces congeladas | Cinco digests conferidos |
| `repeat-boot --count 1000` | 1.000 boots até o shell e parada ordenada; aproximadamente 609 s |
| `benchmark` | 8/8 budgets cumpridos; aproximadamente 102 s |
| `reproduce-build` | Duas compilações limpas idênticas; aproximadamente 69 s |
| `fuzz --all --budget-hours 0.02` | 14 alvos, quatro famílias, nenhuma falha; aproximadamente 153 s |
| `soak --hours 0.05` | Um boot de 181 s, 186 rodadas, rede ligada, nenhuma falha |
| `release-check` | Status 1; 10/12 gates, pacote não qualificado |

O soak manteve `frames-free=59676`. Esse resultado curto não substitui a evidência de estabilidade de 24 horas. O fuzzing acumulou 0,02 hora por família, não 24 horas.

## Correções de primeiro uso

| Problema | Tratamento |
| --- | --- |
| Caminho com espaço quebrava o Make com erro genérico | Preflight recusa repositório, build ou cache com espaço, cita o caminho e devolve status 3. O requisito está no README; suporte a espaços não é prometido |
| Primeiro byte perdido em entrada redirecionada antes do boot | `run` segura stdin de pipe ou arquivo até `shell: ready` |
| Mais de quatro linhas coladas sumiam sem aviso | Descarte de linhas completas gera `console: dropped-lines=N`; limite e uso por script documentados |
| Linha excessiva era executada truncada | Linha que excede 255 bytes é recusada com `MESSAGE_TOO_LARGE`; Ctrl-U permite recomeçar |
| TAB e setas contaminavam comandos | TAB vira espaço; sequências de escape são descartadas inteiras |
| Falta de `cc` ou `gcc` gerava erro genérico | Preflight confere `make`, `cc` e `gcc`, informando a ferramenta ausente com status 3 |
| `write` recusado deixava arquivo novo vazio | O shell remove o arquivo que acabou de criar quando a escrita é recusada; arquivos preexistentes não são removidos |
| `%` em `str` não era documentado | Matriz do runtime registra a ausência e indica `str.format` ou f-strings |
| Homologação citava imagens antigas como atuais | Este registro substitui os valores antigos, conserva o link histórico e liga os resultados aos hashes efetivos |

O anel serial nativo continua limitado a 256 bytes: uma rajada que o enche pode perder bytes antes do serviço de console, sem aviso ao operador. Scripts devem aguardar o status de cada comando. No terminal interativo, digite depois do prompt; a retenção de entrada antes do boot é específica de stdin redirecionado.

## Budgets medidos

| Métrica | Limite | Medido |
| --- | --- | --- |
| Boot até o shell e parada ordenada | 15 s | 0,405 s |
| Memória comprometida em repouso | 100.663.296 bytes | 24.002.560 bytes |
| Memória comprometida sob carga | 234.881.024 bytes | 32.735.232 bytes |
| Round-trip IPC, p99 | 25.000 µs | 1.585 µs |
| Resposta de tarefa pronta, p99 | 250.000 µs | 51.389 µs |
| Pausa do coletor, p99 | 25.000 µs | 2.648 µs |
| Maior pausa do coletor | 100.000 µs | 2.648 µs |
| Liberação após término, máximo | 1.000.000 µs | 1.197 µs |

As condições e as amostras estão no JSON. O coletor teve só três coletas, portanto p99 e máximo coincidem. Valores de TCG neste host não representam hardware físico.

## Gates e distribuição

Passaram `correctness`, `boot`, `lifecycle`, `isolation`, `durability`, `network`, `dependencies`, `distribution`, `interfaces` e `budgets`. Permanecem abertos `stability` e `fuzzing`.

O pacote `kernel-1.0.0rc1-qemu-riscv64` contém imagens, manifesto, perfil, toolchain lock, `SHA256SUMS`, inventário de licenças, SBOM SPDX 2.3 e relatório de release. O manifesto mantém `qualified: false`. Não há assinatura de release de produção, e nenhuma chave foi criada ou incluída no repositório para esta publicação.

Para uma versão estável, sobre as mesmas imagens:

```sh
uv run kernel-tool fuzz --all --budget-hours 24
uv run kernel-tool soak --profile qemu-riscv64 --hours 24
uv run kernel-tool release-check --profile qemu-riscv64
```

O soak precisa completar 24 horas no mesmo boot. O fuzzing acumula tempo por família e versão do código em `build/fuzz/ledger.json`. Se uma imagem mudar, os demais relatórios também precisam ser refeitos para seus novos hashes. A sequência está em [Procedimento de release](../operations/release-procedure.md).

## Limites desta evidência

- Um host Amazon Linux x86_64 e um convidado QEMU TCG; nenhum hardware físico.
- Rede contra uma única pilha externa, Linux 6.18.56.
- Sem prova de estabilidade ou fuzzing de 24 horas.
- Sem assinatura de produção; checksums detectam alteração, mas não autenticam o publicador.
- O resultado do CI no GitHub é independente desta execução e deve ser conferido no pull request.
