# Registro de homologação: qualificação e distribuição

Resultado da execução dos comandos de homologação sobre a árvore que acrescenta o fuzzing, as medições, o boot repetido, o soak, as interfaces congeladas, o pacote de release e a instalação. Os números vêm dos relatórios que cada comando gravou em `build/qemu-riscv64/qualification/`, em `build/qemu-riscv64/reports/` e em `build/fuzz/`. O que não foi medido não aparece aqui.

O release não está qualificado. Dez dos doze gates estão cumpridos. `stability` e `fuzzing` pedem 24 horas de execução cada um, e nesta execução o soak e cada família de fuzzing rodaram por três minutos. `release-check` terminou com status 1 e montou o pacote com `"qualified": false`. O que falta está na seção [O que falta para qualificar](#o-que-falta-para-qualificar).

## A execução

| Item | Valor |
| --- | --- |
| Data | 17 de novembro de 2026, das 01:23 às 02:12 UTC |
| Árvore | Branch `feat/release-qualification-and-distribution`, sobre o commit `65cdfaf` de `main` |
| Versão | `1.0.0rc1` |
| Host | Linux 6.18.56 x86_64, 2 vCPUs Intel Xeon de 2,9 GHz e 4 GiB de RAM |
| Convidado | QEMU 9.2.4 com TCG, um hart e 256 MiB, perfil `qemu-riscv64` |
| Peer de rede | Pilha TCP/IP do Linux 6.18.56, a do próprio host, em um namespace de rede sem rota para fora |
| Build | Diretório vazio, com a toolchain de `toolchain.lock.toml` conferida por hash |

Os comandos rodaram na ordem da tabela, que não é a de `docs/operations/release-procedure.md`. A ordem não muda o resultado: cada relatório leva o hash das imagens a que se refere, e `release-check` só aceita os das imagens listadas abaixo.

| Comando | Horário (UTC) | Tempo | Resultado |
| --- | --- | --- | --- |
| Os 34 comandos do workflow de CI, na ordem do workflow | 01:23 a 01:34 | 630 s | 31 com status 0. `native-check`, `replay-corpus` e `fuzz` com status 3, repetidos depois |
| `benchmark`, entre os comandos do workflow | 01:28 a 01:30 | 100 s | 8 de 8 budgets cumpridos |
| `soak --hours 0.05`, entre os comandos do workflow | 01:30 a 01:33 | 182 s | 198 rodadas, nenhuma falha |
| `reproduce-build`, entre os comandos do workflow | 01:33 a 01:34 | 67 s | Imagens idênticas |
| `fuzz --all --budget-hours 0.05` | 01:35 a 01:41 | 383 s | 14 alvos, nenhuma falha |
| `repeat-boot --count 1000`, primeira execução | 01:35 a 01:46 | 659 s | Interrompida no boot 581, com status 3 |
| `repeat-boot --count 1000` | 01:52 a 02:05 | 791 s | 1.000 de 1.000 boots |
| `verify --all` | 02:05 a 02:08 | 207 s | 28 de 28 verificações |
| `release-check` | 02:08 | 1 s | Status 1, com 10 de 12 gates cumpridos |

### O que não rodou de primeira

Na passada pelos comandos do workflow, `native-check`, `replay-corpus` e `fuzz` terminaram com status 3 em menos de 2 s. O GCC 11 do host aceitava `-fsanitize=address,undefined`, mas o host não tinha as bibliotecas de runtime dos sanitizers. O `kernel-tool` compila e executa uma sonda antes de usar os sanitizers, e a sonda não iniciou: `libasan.so.6: cannot open shared object file`. Os três comandos ficaram como infraestrutura indisponível, e não como aprovados. Com `libasan` e `libubsan` instaladas no host, `native-check` e `replay-corpus` foram repetidos às 01:26 e passaram, e `fuzz` rodou em seguida.

A primeira execução de `repeat-boot --count 1000` parou no boot 581, com status 3. Um `verify --all` tinha sido iniciado sobre o mesmo diretório de build enquanto ela rodava, e os dois comandos disputaram o volume de dados dos cenários: o QEMU do boot 581 não conseguiu a trava de escrita de `scenarios/data.img`. Os 580 boots anteriores tinham passado. O relatório ficou com 580 de 1.000, e `release-check` reprovou o gate `boot` com essa contagem. O erro foi de operação, por rodar dois comandos sobre o mesmo diretório de build. A execução foi repetida do zero, sozinha, e é ela que este registro conta.

Aquele `verify --all`, das 01:45 às 01:49, aprovou as 28 verificações. Depois dele o instalador e o corpus de fuzzing mudaram, como contam as seções [Fuzzing](#fuzzing) e [Falhas encontradas](#falhas-encontradas). O comando foi repetido sozinho sobre a árvore final, e a tabela acima e a seção seguinte são dessa repetição.

## Imagens testadas

| Imagem | Bytes | SHA-256 |
| --- | --- | --- |
| `kernel.elf` | 1.643.184 | `d9ac28966573baedd15ed56616ae1cd378e51e8379f3171983162c45340ce834` |
| `kernel-selftest.elf` | 1.740.744 | `d98e8417791e64943daf6610c0be2941601a964d187925642548fb12b7f4d111` |
| `init.img` | 431.655 | `e8958111459302806aae8379d0926137591f86d20ea0b7bfd4fa99e236a46513` |
| `tests.img` | 626.047 | `28fffd31e6b2121c873c8b1e0a24f59ebd92c7aa807d0f8e34078182bc3a127a` |
| `boot.img` | 65.536 | `d676ac117840712a66ff275a6c3036c4918c562be9fb820bc790d4be7c5e7b2c` |

Cada relatório de `qualification/` leva o SHA-256 de `kernel.elf`, `init.img` e `boot.img`. Os cinco relatórios desta execução trazem os valores acima.

## Matriz de verificação

`verify --all` rodou as 28 verificações em 205,9 s. Todas terminaram como `passed` e nenhuma como `incomplete`.

| Área | Verificações | Quais | Tempo |
| --- | --- | --- | --- |
| Host | 5 | `format`, `lint`, `types`, `host-tests`, `frozen-interfaces` | 10,8 s |
| Nativo | 4 | `native-check`, `fuzzing-corpus`, `build`, `artifacts` | 29,4 s |
| Runtime | 1 | `suite-bootstrap` | 39,4 s |
| QEMU | 9 | `suite-applications`, `suite-capabilities`, `suite-devices`, `suite-ipc`, `suite-memory`, `suite-processes`, `suite-scheduling`, `suite-supervision`, `suite-vfs` | 77,3 s |
| Interoperabilidade | 3 | `suite-network`, `suite-network-interop`, `faults-network-faults` | 24,8 s |
| Recuperação | 6 | `suite-release-journey`, `suite-storage`, `suite-system-journey`, `faults-device-reset`, `faults-storage-crash`, `volume-corpus` | 24,2 s |

O que as verificações do host e do código nativo contaram:

| Verificação | Contagem |
| --- | --- |
| `format` e `lint` | 693 arquivos, nenhum a reformatar e nenhuma ocorrência |
| `types` | 360 arquivos, nenhum erro |
| `host-tests` | 960 testes aprovados |
| `frozen-interfaces` | 5 interfaces com o digest gravado |
| `native-check` | 12 testes nativos hospedados sob AddressSanitizer e UndefinedBehaviorSanitizer, e a análise estática do supervisor |
| `fuzzing-corpus` | Seeds e corpus dos 14 alvos repetidos sem mutação |
| `volume-corpus` | 21 imagens com o veredito esperado |

### Suítes no QEMU

| Suíte | Cenários aprovados | Casos | Verificações | Tempo no QEMU |
| --- | --- | --- | --- | --- |
| `bootstrap` | 9 de 9 | 0 | 0 | 38,7 s |
| `memory` | 1 de 1 | 7 | 78 | 0,6 s |
| `processes` | 3 de 3 | 7 | 160 | 63,3 s |
| `capabilities` | 1 de 1 | 6 | 47 | 0,2 s |
| `ipc` | 1 de 1 | 9 | 83 | 0,5 s |
| `scheduling` | 2 de 2 | 7 | 37 | 1,4 s |
| `devices` | 3 de 3 | 11 | 91 | 0,7 s |
| `vfs` | 1 de 1 | 7 | 71 | 1,6 s |
| `storage` | 8 de 8 | 3 | 14 | 4,9 s |
| `network` | 1 de 1 | 7 | 71 | 12,9 s |
| `network-interop` | 2 de 2 | 14 | 14 | 6,5 s |
| `applications` | 1 de 1 | 0 | 0 | 4,9 s |
| `supervision` | 6 de 6 | 5 | 32 | 3,5 s |
| `system-journey` | 2 de 2 | 0 | 0 | 4,0 s |
| `release-journey` | 5 de 5 | 0 | 0 | 2,3 s |
| `device-reset` | 1 de 1 | 4 | 21 | 7,2 s |
| `storage-crash` | 1 de 1 | 0 | 0 | 0,6 s |
| `network-faults` | 1 de 1 | 5 | 26 | 2,5 s |
| Total | 49 de 49 | 92 | 745 | 156,1 s |

Um caso é uma linha `test: suite=... case=... checks=N result=ok` da transcrição, e N é quantas verificações o programa de teste fez dentro do convidado. Os cenários sem casos são conferidos pelo `kernel-tool`, que exige as linhas que a transcrição precisa ter e reprova as que ela não pode ter.

### `release-journey`

Cinco boots. Os três primeiros usam o mesmo volume de dados.

| Cenário | O que a transcrição mostra |
| --- | --- |
| `first-initialization` | `cat boot/system/release` responde `version=1.0.0rc1`. Uma nota de 21 bytes é gravada em `data/site/note`, e `sync` responde `volumes=2` |
| `update-keeps-the-volume` | A imagem de boot é a de outra versão, `version=next`. A nota volta com os 21 bytes, e o sistema grava mais 28 bytes em `data/site/added` |
| `rollback-keeps-the-volume` | De volta à imagem `1.0.0rc1`. Os dois arquivos são lidos, com 21 e 28 bytes |
| `damaged-volume-stays-readable` | Com o root mais novo danificado, `data` monta como `read-only` e `write` termina com `READ_ONLY`. A imagem do volume fica byte a byte como estava |
| `unknown-format-is-not-mounted` | Com um formato desconhecido, o serviço de arquivos informa `mount=data unavailable error=UNSUPPORTED` e `write` em `data` termina com `NOT_FOUND`. A imagem do volume fica byte a byte como estava |

## Boot repetido

`repeat-boot --count 1000` iniciou a imagem de release mil vezes, com um volume válido e a rede isolada. Em cada boot os serviços ficaram prontos, o shell aceitou `shutdown` e a parada terminou limpa.

| Medida | Valor |
| --- | --- |
| Boots pedidos, concluídos e reprovados | 1.000, 1.000 e 0 |
| Tempo de um boot, do início do emulador ao fim da parada | Mínimo de 0,27 s, mediana de 0,29 s, p99 de 0,38 s e máximo de 0,46 s |
| Soma do tempo no QEMU | 293 s |
| Transcrições distintas | 7, com 971, 12, 7, 6, 2, 1 e 1 boots cada |

`boots.json` guarda de cada boot o número, a duração e o SHA-256 da transcrição. A transcrição inteira só é guardada quando o boot reprova, e por isso as desta execução não estão no relatório.

As transcrições têm 7 hashes distintos, e 971 boots compartilham um deles. Para ver o que varia, o mesmo cenário rodou mais 60 vezes com as transcrições guardadas. Apareceram 3 variantes, e os hashes delas são os de 984 dos 1.000 boots: a dos 971; uma com a linha `shutdown: action=shutdown` a mais, que é a de 6 boots; e uma com essa linha, com `shell: command=shutdown status=ok` e com um novo prompt, que é a de 7. A diferença fica toda entre o `shutdown` digitado e a parada do shell. O shell é o primeiro serviço a parar, e essas linhas só aparecem quando ele consegue escrevê-las antes de o gerente pará-lo. A ordem de parada dos cinco serviços, `system: shutdown=complete clean=1` e `kernel: status=ok` são iguais nas três. As outras quatro variantes, de 16 boots, não foram guardadas. Sobre elas este registro só afirma o que o cenário exige de todo boot: configuração aceita, shell pronto, sistema em execução e parada limpa.

## Ciclos de processo e de IPC

O cenário `cycles` da suíte `processes` levou 61,5 s. Ele faz 100 ciclos de aquecimento e depois 10.000 medidos. Cada ciclo cria um processo do serviço `echo`, troca duas chamadas com ele e espera o término. Os contadores lidos depois do aquecimento são comparados com os lidos no fim: objetos, capabilities e endpoints não podem crescer, e os frames livres não podem diminuir.

```
cycles: completed=10000 frames-free=62356
test: suite=processes case=ten-thousand-process-and-ipc-cycles checks=103 result=ok
```

## Budgets

`benchmark` mediu os oito budgets nas imagens de release, em três cenários: um programa de medição sobre a imagem de testes, o cenário `cycles` com o rastreio do coletor ligado e uma sessão do sistema operada pelo shell.

| Métrica | Budget | Medido | Condição |
| --- | --- | --- | --- |
| Boot até o shell pronto e a parada em ordem | 15 s | 0,46 s | Relógio do host, do início do emulador ao fim da parada. Imagem de release, volume válido e rede isolada |
| Memória comprometida em repouso | 96 MiB | 22,9 MiB | Memória da máquina menos os frames livres, com os serviços obrigatórios e o shell parados à espera |
| Memória comprometida sob carga | 224 MiB | 31,2 MiB | A mesma conta, com as quatro vagas de aplicação ocupadas e cada heap preenchido |
| Round-trip de IPC pequeno, p99 | 25 ms | 1,63 ms | Relógio do convidado, 10.000 chamadas a um processo de echo, sem disco e sem rede. p50 de 0,91 ms e máximo de 2,03 ms |
| Resposta de tarefa pronta, p99 | 250 ms | 80,0 ms | Relógio do convidado, atraso depois do prazo de um timer, com os serviços obrigatórios, quatro aplicações presas ao processador e duas a arquivos. 400 amostras, p50 de 33,1 ms e máximo de 82,5 ms |
| Pausa do coletor do supervisor, p99 | 25 ms | 2,72 ms | Sessão do sistema sob carga, com 3 coletas |
| Pausa do coletor do supervisor, máximo | 100 ms | 2,72 ms | A mesma sessão |
| Liberação após término, máximo | 1 s | 1,07 ms | Relógio do convidado, do `kill` de um processo até todos os frames dele voltarem a ficar livres. 50 amostras, p50 de 0,71 ms |

O boot é medido pelo relógio do host. As latências são medidas pelo contador `time` do convidado. São valores de TCG em uma máquina virtual de dois processadores e não valem para hardware físico.

As pausas do coletor vêm de 3 coletas. Com tão poucas amostras, o p99 e o máximo são o mesmo valor. O soak abaixo acrescenta 4 coletas, com máximo de 2,77 ms.

## Soak

`soak --hours 0.05` manteve um único boot por 181 s, com rede, e completou 198 rodadas. Nenhum comando terminou fora do esperado, não apareceu `trap:` nem `panic:`, a parada foi limpa e o volume montou depois. As 8 primeiras rodadas são aquecimento. As outras 190 ficaram assim:

| Recurso | Mediana da primeira metade | Extremo da primeira metade | Mediana da segunda metade | Extremo da segunda metade |
| --- | --- | --- | --- | --- |
| Frames livres | 59.676 | 59.676 | 59.676 | 59.676 |
| Objetos do kernel | 39 | 39 | 39 | 39 |
| Capabilities | 64 | 64 | 64 | 64 |
| Endpoints | 18 | 18 | 18 | 18 |
| Buffers | 6 | 6 | 6 | 6 |
| Processos | 8 | 8 | 8 | 8 |
| Bytes de IPC pendentes | 0 | 0 | 0 | 0 |
| Duração da rodada | 915 ms | 1.026 ms | 911 ms | 1.017 ms |

Nenhum recurso piorou. Três minutos não mostram um crescimento lento, e é para isso que o gate pede 24 horas. O gate `stability` continua em aberto.

## Fuzzing

`fuzz --all --budget-hours 0.05` deu três minutos a cada família, divididos entre os alvos dela, com a seed 1.

| Família | Alvos | Execuções | Tempo acumulado |
| --- | --- | --- | --- |
| `boot` | 3 | 3.340.701 | 0,05 h |
| `interface` | 4 | 7.012.586 | 0,05 h |
| `storage` | 4 | 5.465.076 | 0,05 h |
| `network` | 3 | 3.645.816 | 0,05 h |

| Família | Alvo | Execuções | Entradas no fim | Entradas novas | Falhas | Tempo |
| --- | --- | --- | --- | --- | --- | --- |
| `boot` | `device-tree` | 1.202.299 | 17 | 0 | 0 | 60 s |
| `boot` | `user-image` | 1.320.552 | 9 | 0 | 0 | 60 s |
| `boot` | `configuration` | 817.850 | 42 | 0 | 0 | 60 s |
| `interface` | `ipc-message` | 1.331.019 | 6 | 0 | 0 | 45 s |
| `interface` | `spawn-request` | 1.433.354 | 4 | 0 | 0 | 45 s |
| `interface` | `service-payloads` | 2.986.702 | 215 | 0 | 0 | 45 s |
| `interface` | `console-input` | 1.261.511 | 7 | 0 | 0 | 45 s |
| `storage` | `volume-image` | 214.604 | 21 | 0 | 0 | 45 s |
| `storage` | `volume-metadata` | 2.671.148 | 25 | 0 | 0 | 45 s |
| `storage` | `paths` | 1.664.859 | 13 | 0 | 0 | 45 s |
| `storage` | `boot-image` | 914.465 | 7 | 0 | 0 | 45 s |
| `network` | `frames` | 282.438 | 55 | 2 | 0 | 60 s |
| `network` | `packet-layers` | 3.314.264 | 47 | 1 | 0 | 60 s |
| `network` | `stream-dialogue` | 49.114 | 21 | 0 | 0 | 60 s |

Foram 19.464.179 execuções, sem nenhuma falha: nenhum crash, nenhum travamento e nenhum invariante quebrado. Como nada falhou, `tests/fuzz/regressions/` ainda não existe.

Dois alvos de rede alcançaram código que o corpus versionado não alcançava: `frames`, com 2 entradas, e `packet-layers`, com 1. `promote-corpus --all` repetiu as entradas sobre o corpus versionado e copiou para `tests/fuzz/corpus/network/` as que ainda acrescentavam cobertura, uma de cada alvo. `replay-corpus --all` passou nos 14 alvos com as duas entradas novas.

Três minutos sem falha dizem pouco. O gate `fuzzing` pede 24 horas acumuladas em cada família e continua em aberto.

## Build reproduzível

`reproduce-build` compilou duas vezes, cada uma em um diretório vazio, com `SOURCE_DATE_EPOCH=1787581954`. As seis imagens saíram iguais nos dois diretórios e iguais às do build testado: `kernel.elf`, `kernel-selftest.elf`, `init.img`, `tests.img`, `boot.img` e `fault.img`.

## Gates de release

| Gate | Estado | Evidência desta execução |
| --- | --- | --- |
| `correctness` | Cumprido | `verify --all`: 28 de 28 verificações, nenhuma incompleta |
| `boot` | Cumprido | `repeat-boot`: 1.000 de 1.000 boots |
| `lifecycle` | Cumprido | Cenário `cycles` da suíte `processes`: 10.000 ciclos sem crescimento de objetos, capabilities, endpoints ou frames |
| `stability` | Em aberto | `soak`: 0,05 de 24 horas em um boot, com rede e sem falha |
| `fuzzing` | Em aberto | `fuzz`: 0,05 de 24 horas em cada uma das quatro famílias, nenhuma falha em aberto |
| `isolation` | Cumprido | Suítes `memory`, `capabilities`, `ipc` e `devices`, e as falhas de `device-reset` |
| `durability` | Cumprido | Suíte `storage`, as falhas de `storage-crash` e o corpus de volumes |
| `network` | Cumprido | Suítes `network` e `network-interop`, e as falhas de `network-faults` |
| `dependencies` | Cumprido | Revisão de 17 de novembro de 2026 em `config/release/advisories.toml`: 13 avisos conferidos em quatro componentes, nenhum aplicável às versões fixadas. Licenças do inventário aceitas |
| `distribution` | Cumprido | `reproduce-build` com imagens idênticas, e as suítes `release-journey` e `system-journey` |
| `interfaces` | Cumprido | Os cinco digests de `specs/frozen-interfaces.toml` conferem |
| `budgets` | Cumprido | `benchmark`: 8 de 8 budgets cumpridos |

`release-check` terminou com status 1. A saída diz que 2 dos 12 gates não estão cumpridos, `stability` e `fuzzing`, e que o pacote foi marcado como não qualificado.

## Pacote

`release-check` montou `build/qemu-riscv64/release/kernel-1.0.0rc1-qemu-riscv64/`.

| Arquivo | Bytes |
| --- | --- |
| `SHA256SUMS` | 982 |
| `boot.img` | 65.536 |
| `init.img` | 431.655 |
| `kernel.elf` | 1.643.184 |
| `licenses/kernel.txt` | 35.149 |
| `licenses/libgcc.txt` | 3.324 |
| `licenses/micropython.txt` | 3.419 |
| `licenses.json` | 1.196 |
| `manifest.json` | 3.050 |
| `profile.toml` | 842 |
| `release-report.json` | 2.038 |
| `sbom.spdx.json` | 6.305 |
| `toolchain.lock.toml` | 1.395 |

`manifest.json` declara a versão `1.0.0rc1`, o perfil `qemu-riscv64`, o formato de volume 1, as cinco interfaces na versão 1.0 (`abi`, `service-protocol`, `image-manifest`, `configuration`, `persistent-format`) e `"qualified": false`. `SHA256SUMS` cobre os outros 12 arquivos. `sbom.spdx.json` é SPDX 2.3 e lista 6 pacotes.

| Componente | Versão | Papel | Licença | Vai no pacote |
| --- | --- | --- | --- | --- |
| `kernel` | 1.0.0rc1 | Produto | `GPL-3.0-only` | Sim |
| `riscv-none-elf-gcc` | 15.2.0-1 | Compilador | `GPL-3.0-or-later WITH GCC-exception-3.1` | Não |
| `libgcc` | 15.2.0-1 | Ligado às imagens | `GPL-3.0-or-later WITH GCC-exception-3.1` | Sim |
| `qemu-riscv` | 9.2.4-1 | Emulador | `GPL-2.0-only` | Não |
| `micropython` | 1.29.0 | Ligado às imagens | `MIT` | Sim |
| `opensbi` | 1.5.1 | Firmware | `BSD-2-Clause` | Não |

## Assinatura: ensaio

A chave de release ainda não existe. O procedimento de `docs/operations/release-procedure.md` foi ensaiado com uma chave ed25519 criada para isso, fora do repositório, e descartada depois.

| Passo | Resultado |
| --- | --- |
| `release-verify <pacote>` | Checksums conferidos: `is intact and not qualified` |
| `release-sign <pacote> --key <chave>` | Recusado com status 1: `is not qualified; only a bundle that passed release-check is signed` |
| `release-sign <pacote> --key <chave> --rehearsal` | `SHA256SUMS.sig` gravado |
| `release-verify <pacote> --allowed-signers <arquivo> --identity <signatário>` | Assinatura e checksums conferidos |
| O mesmo comando, com outra identidade | Recusado com status 1: `Could not verify signature.` |
| O mesmo comando, sobre uma cópia do pacote com um byte a mais em `boot.img` | Recusado com status 1: `boot.img: the content does not match its checksum` |

## Instalação, atualização e volta: ensaio

Os comandos são os de `docs/operations/installation.md`, na ordem do documento, sobre um diretório vazio. O segundo pacote é a mesma árvore com a versão `1.0.0rc2`, compilada em outro diretório de build. Os dois pacotes foram assinados com a chave do ensaio, e `install` e `update` conferiram a assinatura. Os três boots foram operados pela porta serial, um comando a cada prompt.

| Passo | Resultado |
| --- | --- |
| `install <pacote 1.0.0rc1> --target <diretório>` | `runs kernel-1.0.0rc1-qemu-riscv64; earlier release: none`, com um `data.img` novo |
| `run --installation <diretório>` | `cat boot/system/release` responde `version=1.0.0rc1`. `write data/site/first` grava 29 bytes, `sync` responde `volumes=2` e a parada termina com `clean=1` |
| `update <pacote 1.0.0rc2> --target <diretório>` | `runs kernel-1.0.0rc2-qemu-riscv64; earlier release: kernel-1.0.0rc1-qemu-riscv64` |
| `run --installation <diretório>` | `version=1.0.0rc2`. `cat data/site/first` devolve os 29 bytes gravados pelo release anterior, e `write data/site/second` grava 30 bytes |
| `rollback --target <diretório>` | `runs kernel-1.0.0rc1-qemu-riscv64; earlier release: kernel-1.0.0rc2-qemu-riscv64` |
| `run --installation <diretório>` | `version=1.0.0rc1`. Os dois arquivos são lidos, com 29 e 30 bytes, e `ls data/site` responde `entries=2`. O `data.img` termina com o mesmo SHA-256 que tinha antes desse boot |
| `rollback --target <diretório>`, de novo | Volta ao `1.0.0rc2`: o comando alterna entre os dois releases instalados |
| `verify-filesystem --image <diretório>/data.img` | `verdict=mountable reason=clean generation=3`, com 2 diretórios, 2 arquivos e 59 bytes |

A recuperação de um volume danificado ou em formato desconhecido não entrou no ensaio. Ela é coberta pelos dois últimos cenários de `release-journey`.

## Critérios de aceite

| Critério | Estado | Evidência desta execução |
| --- | --- | --- |
| A matriz de host, runtime, mecanismos nativos, QEMU, interoperabilidade e recuperação roda inteira | Cumprido | `verify --all`, com 28 de 28 |
| Não há crash, corrupção, deadlock ou quebra de isolamento conhecida sem correção | Cumprido para o que foi executado | As 18 suítes, 1.000 boots e 19.464.179 execuções de fuzzing sem falha. Falta a evidência de 24 horas |
| Não há vulnerabilidade alta ou crítica aplicável nem licença incompatível | Cumprido | Gate `dependencies` |
| Quotas, deadlines, reservas e caminhos de falha funcionam sob carga combinada | Cumprido em três minutos | `soak` de 0,05 hora e a sessão sob carga de `benchmark`. Falta o soak de 24 horas |
| Os gates de lifecycle, boot e recuperação passam no build de release | Cumprido | Gates `lifecycle`, `boot`, `durability` e `distribution` |
| Os gates de soak e de fuzzing passam no build de release | Em aberto | 0,05 de 24 horas em cada um |
| Os budgets são cumpridos no ambiente declarado | Cumprido | `benchmark`, com 8 de 8 |
| Build e artefatos reproduzíveis têm proveniência, inventário e checksums | Cumprido | `reproduce-build`, `SHA256SUMS`, `sbom.spdx.json` e `licenses.json` |
| Instalação, atualização, rollback e recuperação foram executados seguindo a documentação | Cumprido | O ensaio acima e a suíte `release-journey` |
| ABI, configuração e formato persistente têm versões e regras de evolução | Cumprido | `specs/compatibility.md` e o gate `interfaces` |
| Limitações, exclusões e fronteira nativa estão visíveis | Cumprido | `README.md`, `docs/security/trusted-computing-base.md`, `docs/security/privileged-boundary-review.md` e as seções finais deste registro |
| A versão 1.0 está pronta para distribuição autorizada | Em aberto | Depende dos dois gates de 24 horas |

## Falhas encontradas

O instalador gravava `installation.json` no lugar. Uma interrupção entre truncar e escrever o arquivo deixaria um diretório que `run --installation`, `update` e `rollback` não conseguiriam abrir, com as imagens e o volume intactos. A falha apareceu na leitura do código antes do ensaio e não chegou a acontecer. O estado agora vai para um arquivo pendente, é descarregado no disco e substitui o anterior por um rename. `tests/host/test_release_installation.py` interrompe a troca e confere que o release anterior continua instalado. As imagens do convidado não mudaram.

No ensaio da assinatura, `release-verify` recusou a identidade errada com status 1, mas a mensagem terminava sem o motivo. O `ssh-keygen` do host escreve essa recusa na saída padrão, e a ferramenta só lia a saída de erro. A mensagem agora junta as duas, e os testes de `tests/host/test_release_bundle_files.py` exigem um motivo. A linha da tabela do ensaio é a do comando repetido depois da correção.

Essa segunda correção veio depois do `verify --all`. Ela muda uma mensagem do `kernel-tool` e dois testes, e não muda as imagens. `ruff format --check`, `ruff check`, `mypy --strict host src` e `pytest tests/host tests/conformance` rodaram de novo sobre a árvore final: 693 arquivos, nenhuma ocorrência, nenhum erro e 960 testes aprovados.

As duas interrupções contadas em [O que não rodou de primeira](#o-que-não-rodou-de-primeira) foram do host e da operação. Nenhuma suíte, nenhum boot e nenhum alvo de fuzzing reprovou nesta execução.

## O que falta para qualificar

```sh
uv run kernel-tool fuzz --all --budget-hours 24
uv run kernel-tool soak --profile qemu-riscv64 --hours 24
uv run kernel-tool release-check --profile qemu-riscv64
```

- O soak precisa de 24 horas seguidas em um boot. Um runner hospedado do GitHub encerra um job em seis horas, então ele roda em uma máquina própria.
- O fuzzing soma 96 horas de alvo, 24 por família, divididas entre os 14 alvos. O comando roda um alvo por processador ao mesmo tempo: são cerca de 48 horas de relógio com dois processadores, 24 com quatro e 8 com catorze ou mais. O tempo acumula entre sessões em `build/fuzz/ledger.json`, e `--family` roda uma família por vez.
- Os dois precisam rodar sobre imagens com os hashes desta página. Uma mudança que altere uma imagem invalida também os relatórios de boot, de medições e da matriz.
- Com os doze gates cumpridos, `release-check` grava `"qualified": true`. Assinar com a chave de release, criar a tag e publicar dependem de autorização de quem responde pelo projeto.

## O que este registro não cobre

- Os tempos são de um host e de TCG. Não valem para hardware físico.
- A interoperabilidade de rede foi conferida contra uma pilha só, a do Linux 6.18.56.
- O p99 das pausas do coletor vem de 3 coletas.
- A assinatura foi ensaiada com uma chave descartada. Não existe ainda uma chave de release.
- O resultado do CI no runner `ubuntu-24.04` fica no pull request, e não nesta página.
