# Diagnosticar

[English](diagnostics.en.md)

Onde olhar quando algo falha, no convidado e nas ferramentas do host.

## O que o console diz

Cada linha começa pelo nome de quem a escreveu.

| Prefixo | Quem escreve | Para que serve |
| --- | --- | --- |
| `boot:` | Código nativo, antes do runtime | Memória, regiões reservadas, console, dispositivos do DTB |
| `trap:` | Código nativo | Trap inesperada no supervisor: causa, `sepc`, `stval`, `sstatus`, `ra` e `sp` |
| `panic:` | Código nativo | Motivo de uma parada fatal |
| `policy:` | Política Python do supervisor | Perfil conferido, processo inicial admitido e recolhido, recursos liberados ou vazados, deadlock |
| `system:` | Gerente do sistema | Configuração aceita ou recusada, estado de cada serviço, aplicações, parada |
| `shell:` | Shell | `shell: command=<nome> status=ok` ou `status=failed error=<ERRO>` depois de cada comando |
| `kernel:` | Código nativo | `kernel: power=restart` e a última linha, `kernel: status=ok` ou `kernel: status=failed` |

A última linha diz como o sistema terminou. Sem ela, o kernel não chegou ao fim: travou, foi morto pelo deadline do emulador ou o emulador caiu.

`policy: resources=leaked` lista os contadores que não voltaram ao valor do boot. `policy: stopped=deadlock` diz que todos os processos esperavam uns pelos outros.

Com `trace=collector` nos argumentos do kernel, a política escreve ao final `policy: collector=measured collections=<n> pause-total-us=<t> pause-p99-us=<p> pause-longest-us=<m>`. São as pausas do coletor do supervisor, medidas pelo timer. `benchmark` e `soak` iniciam o sistema assim.

Processos diferentes escrevem no console sem coordenação entre si. O texto de um pode aparecer colado ao fim da linha de outro, como em `shell: command=run status=okspin: started`. As ferramentas do host procuram os padrões dentro da linha e não dependem de onde ela termina.

## No shell

- `ps` mostra o estado do sistema, de cada serviço, com reinícios usados e permitidos, e de cada aplicação.
- `mem` mostra frames utilizáveis, livres e reservados, e os contadores de processos, objetos, capabilities, endpoints, buffers e bytes de IPC pendentes.
- `net` mostra endereço, enlace e contadores da interface; `net neighbors` mostra a tabela ARP.
- `cat boot/system/release` mostra a versão, a interface da imagem de boot e o runtime.

Os erros de cada comando estão em `system-operation.md`.

## Códigos de saída do `kernel-tool`

| Status | Significado |
| --- | --- |
| 0 | A verificação passou |
| 1 | A verificação falhou |
| 2 | Uso incorreto do comando |
| 3 | Faltou infraestrutura: ferramenta do host, emulador, rede isolada. Nada foi verificado |

Status 3 nunca conta como aprovação. Em `verify --all` a verificação fica registrada como `incomplete`.

## Relatórios

| Caminho em `build/qemu-riscv64/` | Conteúdo |
| --- | --- |
| `reports/<suíte>.json` | Cada cenário, com falhas, duração, hashes e a transcrição completa |
| `reports/captures/<cenário>.pcap` | Tráfego dos cenários com rede |
| `qualification/verification.json` | Cada verificação da matriz: passou, falhou ou incompleta, com o motivo |
| `qualification/boots.json` | Cada boot repetido, com duração e hash da transcrição |
| `qualification/measurements.json` | Máquina, medições e o resultado de cada budget |
| `qualification/soak.json` | Rodadas, tendências, pausas do coletor e uma amostra por rodada |
| `qualification/reproduction.json` | Hashes de cada build limpo |
| `soak/soak.log` | Tudo o que o convidado escreveu durante o soak |
| `release/.../release-report.json` | Resultado de cada gate |

Os relatórios de fuzzing ficam em `build/fuzz/`: `ledger.json` com o tempo acumulado, `report.json` com a última sessão e `findings/` com as falhas.

## Reproduzir uma falha

- Cenário: `uv run kernel-tool test --suite <suíte> --scenario <cenário>`. A transcrição da falha sai no terminal e no relatório.
- Fuzzing: copie a linha de `build/fuzz/findings/<família>/<alvo>/<hash>.hex` para `tests/fuzz/regressions/<família>/<alvo>.hex` e rode `uv run kernel-tool replay-corpus --family <família>`. O arquivo `.txt` ao lado traz o diagnóstico da falha original.
- Volume: `uv run kernel-tool inspect-volume <imagem>` e `uv run kernel-tool verify-filesystem --image <imagem>`.
- Boot que não termina: `uv run kernel-tool run --deadline <segundos>` encerra a sessão e mostra o que o console escreveu até ali.

## O que as ferramentas não mostram

Não há depurador ligado ao convidado nem dump de memória. O diagnóstico de uma trap no supervisor é a linha `trap:`. Uma falha em um processo de usuário aparece como o motivo de término dele, em `wait` e em `ps`.
