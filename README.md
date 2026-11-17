# Kernel

[English](README.en.md)

Kernel Python-first para RISC-V de 64 bits. As políticas do sistema são escritas em Python e rodam em MicroPython dentro do supervisor, em S-mode. Cada processo de usuário é outro MicroPython, em U-mode, com o próprio espaço de endereçamento. O código nativo, em C17 e Assembly, cobre o que depende da máquina e o que não pode confiar em Python: boot, traps, memória virtual, troca de contexto, capabilities, IPC, transporte de dispositivos e validação das chamadas de processo.

O alvo é a máquina `virt` do QEMU com o firmware OpenSBI. O convidado não tem Linux e não usa semihosting.

## O que existe hoje

- Boot pelo OpenSBI com o DTB validado, console NS16550 e diagnóstico de trap.
- Memória virtual Sv39: alocador de frames com reserva para o supervisor e um espaço de endereçamento por processo, com código sem escrita, dados sem execução e página de guarda sob a stack.
- Até 16 processos em U-mode, cada um com um MicroPython privado. O timer preempta quem não coopera, e a troca de contexto preserva registradores inteiros e de ponto flutuante.
- Capabilities com handles geracionais: derivação que só reduz direitos, transferência por IPC ou na criação de um processo, revogação das derivadas e cota por processo.
- IPC por endpoints, com envio, recepção e chamada com resposta correlacionada, deadline, cancelamento e término definido quando o outro lado morre. Buffers de memória concedidos por capability para dados maiores que uma mensagem.
- Política Python congelada na imagem do kernel. Ela confere o perfil de recursos, admite processos dentro das cotas e escolhe quem executa: quatro prioridades, round-robin, aging e doação limitada de prioridade a quem atende uma chamada.
- Dispositivos descobertos no DTB e entregues por capability, cada um a um driver. O transporte VirtIO-MMIO e as filas ficam no supervisor: o driver nomeia buffers do próprio processo e nunca informa um endereço físico. A memória de um pedido fica fixada até o dispositivo concluir ou confirmar o reset.
- Drivers e serviços em Python, em U-mode, para a porta serial, o `virtio-blk` e o `virtio-rng`. O console tem disciplina de linha, entrada limitada e saída com backpressure. Pedidos a um dispositivo têm deadline. Sem `virtio-rng` o sistema não oferece entropia.
- Serviço de arquivos com namespaces por capability e handles de arquivo e de diretório, sobre três montagens: a imagem de boot somente leitura, um sistema temporário em memória e um volume persistente.
- Volume persistente copy-on-write, com dois superblocks, checksum em cada ponteiro e commits inteiros. `sync` só responde depois do flush do dispositivo. Um volume que não passa na verificação fica indisponível ou somente leitura e nunca é formatado no boot.
- `init` em U-mode, que inicia os serviços do seu manifesto com as capabilities declaradas, confere que respondem e os encerra: o `echo` e, para os dispositivos que o DTB descreve, console, entropia, bloco e arquivos.
- Rede IPv4 em um serviço Python, em U-mode, com o driver do `virtio-net` dentro do processo: Ethernet, ARP, fragmentação e reassembly limitado, ICMP, UDP e TCP com retransmissão, controle de congestionamento, half-close e `TIME_WAIT`. Interface com endereço estático e rota padrão; sem IPv6, DHCP e DNS.
- Sockets por capability: um processo só abre um socket com um acesso emitido pelo serviço, que pode ser restringido e revogado. As operações têm espera com prazo, cancelamento e backpressure, e a memória de rede tem um orçamento único.
- Gerente do sistema em U-mode, que lê uma configuração declarativa, validada inteira antes de ser aplicada, inicia os serviços na ordem das dependências e reinicia quem morre dentro de um limite por janela. Um serviço que esgota o limite fica degradado e visível, e o resto segue.
- Shell na porta serial, com `help`, `run`, `ps`, `kill`, `wait`, `mem`, `ls`, `cat`, `mkdir`, `write`, `rm`, `sync`, `net`, `ping` e `shutdown`. Cada comando é um pedido a um serviço e termina com uma linha de status.
- Aplicações: programas Python lidos do volume e executados em processos próprios, só com os arquivos e a rede que a configuração concede.
- Parada ordenada: novas aplicações recusadas, aplicações encerradas, serviços parados na ordem inversa, volumes sincronizados e, por fim, desligamento ou reboot pelo SBI.
- Modelos puros de handles geracionais, seleção de processos e contabilização de recursos. Um corpus de 10.000 transições roda em CPython e dentro do convidado, e os resultados precisam ser iguais.
- `kernel-tool`, que baixa a toolchain fixada por hash, compila, inicia o QEMU com deadline, executa os cenários e inspeciona as imagens. Ele também cria, verifica e inspeciona volumes, e reconstrói os estados que uma queda de energia deixaria no disco. Para a rede, liga o convidado a uma estação de teste isolada no host, degrada o enlace de propósito, injeta quadros forjados e grava o tráfego.
- Homologação pelo `kernel-tool`: a matriz de verificação inteira em um comando, fuzzing de 14 alvos em quatro famílias de entrada com corpus versionado, boot repetido, soak de um boot sob carga mista, medição dos budgets e build refeito em diretórios vazios. Cada relatório leva o hash das imagens a que se refere.
- Interfaces 1.0 congeladas, com política de compatibilidade: ABI, protocolo dos serviços, imagens, configuração e formato do volume.
- Pacote de release montado no host, com manifesto, checksums, SBOM em SPDX 2.3, inventário de licenças e assinatura OpenSSH com chave de fora do repositório. Instalação, atualização e rollback trocam as imagens e mantêm o volume de dados.

O kernel usa um único hart, e o isolamento foi exercitado só no QEMU com TCG. A durabilidade foi demonstrada só no `virtio-blk` do QEMU: um disco que confirme um flush que não fez está fora do que foi testado. A rede foi exercitada contra a pilha TCP/IP do Linux, em uma rede isolada; o tráfego não é cifrado, e o shell não autentica quem está na porta serial.

A versão 1.0 ainda não está qualificada. Dois gates de release pedem 24 horas de execução cada, o soak e o fuzzing de cada família, e ainda não foram cumpridos. O estado de cada gate, com o que foi executado, está no [registro de homologação](docs/acceptance/qualification-and-distribution.md).

## Requisitos do host

- Linux x86_64. Os pacotes de `toolchain.lock.toml` são para essa plataforma.
- [uv](https://docs.astral.sh/uv/). O projeto é desenvolvido com a versão 0.13.5. O uv instala o Python 3.13 indicado em `.python-version`.
- `make` e o GCC do host, acessível como `cc` e como `gcc`, com AddressSanitizer e UndefinedBehaviorSanitizer. Ele compila o `mpy-cross` e os testes nativos hospedados. No Amazon Linux 2023 o runtime dos sanitizers vem à parte, nos pacotes `libasan` e `libubsan`. Sem `make`, `cc` ou `gcc`, `build` termina com status 3 e diz qual falta.
- Caminhos sem espaço para o repositório, o diretório de build e o cache da toolchain. O `make` separa nomes de arquivo nos espaços, e `build` recusa um caminho assim com status 3 e o cita. Acentos passam.
- Cerca de 2,5 GB livres para a toolchain. Ela fica em `~/.cache/kernel-tool` ou no diretório indicado por `KERNEL_TOOL_CACHE`.
- Para a rede: permissão para criar um namespace de rede com uma interface TAP. Serve rodar como root, um host que permita user namespaces sem privilégio com acesso a `/dev/net/tun`, ou `sudo` sem senha. Sem isso `run` segue sem rede, e as suítes de rede terminam com status 3.

## Compilar e executar

```sh
uv sync --frozen
uv run kernel-tool toolchain
uv run kernel-tool build
uv run kernel-tool run
```

`toolchain` baixa e confere o GCC, o QEMU e o MicroPython fixados. `build` gera as imagens em `build/qemu-riscv64/`. `run` inicia o sistema no QEMU com o shell neste terminal, um volume de dados que persiste em `build/qemu-riscv64/system/` e a rede isolada, e termina quando o sistema desliga:

```
kernel> ping 10.0.2.2 2
ping: from=10.0.2.2 bytes=32 time-us=4540
ping: from=10.0.2.2 bytes=32 time-us=2022
ping: sent=2 received=2
shell: command=ping status=ok
kernel> shutdown
```

`--deadline` limita o tempo da sessão e `--without-network` dispensa a rede. Quando a entrada vem de um pipe ou de um arquivo, `run` só a entrega ao sistema depois de `shell: ready`. O perfil padrão é `qemu-riscv64`; `--profile` escolhe outro arquivo de `config/profiles/`. O uso do shell está em [Operar o sistema](docs/operations/system-operation.md).

## Verificar

```sh
uv run ruff format --check .
uv run ruff check .
uv run mypy --strict host src
uv run pytest tests/host tests/conformance
uv run kernel-tool native-check
uv run kernel-tool test --suite bootstrap
uv run kernel-tool test --suite memory
uv run kernel-tool test --suite processes
uv run kernel-tool test --suite capabilities
uv run kernel-tool test --suite ipc
uv run kernel-tool test --suite scheduling
uv run kernel-tool test --suite devices
uv run kernel-tool test --suite vfs
uv run kernel-tool test --suite storage
uv run kernel-tool test --suite network
uv run kernel-tool test --suite network-interop
uv run kernel-tool test --suite applications
uv run kernel-tool test --suite supervision
uv run kernel-tool test --suite system-journey
uv run kernel-tool test --suite release-journey
uv run kernel-tool fault-test --suite device-reset
uv run kernel-tool fault-test --suite storage-crash
uv run kernel-tool fault-test --suite network-faults
uv run kernel-tool verify-filesystem --corpus tests/faults/storage
uv run kernel-tool verify-artifacts --reproduce
```

| Comando | O que confere |
| --- | --- |
| `native-check` | Testes nativos hospedados com sanitizers e a análise estática do supervisor |
| `test --suite bootstrap` | Nove cenários no QEMU: boot repetido, autoteste do runtime, DTB grande demais, DTB sem memória, RAM insuficiente, segmento incompatível, falha em U-mode e trap no supervisor, com o runtime parado e com o heap dele esgotado |
| `test --suite memory` | Programas adversariais em U-mode: acesso a memória de outro processo, do supervisor, livre, de dispositivos e à página de guarda; ponteiros inválidos em syscalls; buffers compartilhados; memória zerada entre processos; cotas e reserva do supervisor |
| `test --suite processes` | Status de término, autoridade e validação na criação, preempção de um laço sem cooperação, preservação de registradores, 16 processos simultâneos e liberação de recursos no término. Dois cenários à parte: falha de cada alocação de uma criação, e 10.000 ciclos de processo e IPC sem crescimento de recursos |
| `test --suite capabilities` | Handles antigos e forjados, delegação atenuada, revogação com descendentes, cota, ausência de autoridade ambiente e mapeamentos que seguem a capability |
| `test --suite ipc` | Mensagens malformadas, entrega e transferência, limites de fila, morte do outro lado, cancelamento, deadlines, correlação de respostas, ownership do endpoint e recusa de deadlock |
| `test --suite scheduling` | Round-robin, prioridade sem starvation, doação de prioridade, limite da cadeia de espera, deadline disputando com a resposta, limites do relógio e yield. Um cenário à parte registra o trace de escalonamento do boot |
| `test --suite devices` | Drivers em U-mode: acesso só ao dispositivo recebido, disputa pelo mesmo dispositivo, negociação incompatível, descritores fora dos buffers concedidos e término com pedido pendente. Dois cenários à parte: os serviços de console, bloco e entropia com a autoridade de cada operação, e o boot sem fonte de entropia |
| `test --suite vfs` | Serviço de arquivos sobre a imagem de boot e o sistema temporário: caminhos com `..`, nomes excessivos e UTF-8 inválido, namespaces e direitos, handles, clientes concorrentes e handles antigos depois do reinício do serviço |
| `test --suite storage` | Volume persistente no `virtio-blk`: disco cheio, `sync` ligado ao flush e reinício do serviço. Sete cenários à parte: dados gravados em um boot e conferidos no seguinte, dispositivo somente leitura, dispositivo sem formato, versão de formato desconhecida, root mais novo danificado e erro de flush |
| `test --suite network` | Serviço de rede contra a estação de teste: interface e echo, datagramas vazios, grandes, truncados e para porta sem socket, conexões nos dois sentidos, escuta, espera com prazo, cancelamento e backpressure, cota de sockets e direitos de acesso, com um processo sem acesso que não abre socket nem alcança o dispositivo |
| `test --suite network-interop` | Dados trocados com a pilha TCP/IP do Linux, conferidos por hash, em dois cenários: enlace limpo e enlace com 3% de perda, 2% de duplicação e 10% de reordenação. Envio e recepção de 128 KiB, ida e volta de 64 KiB, conexão iniciada pelo peer, datagramas fragmentados, peer que lê devagar e devolução dos buffers |
| `test --suite applications` | Programas do volume iniciados pelo shell: argumentos, memória não compartilhada entre execuções, capabilities recebidas, exceção, erro de sintaxe, arquivo ausente, laço encerrado por `kill`, heap esgotado, limite de aplicações e parada com aplicações em execução |
| `test --suite supervision` | Ordem de início e de parada, serviço que não fica pronto, reinício com pedido pendente, limite de reinícios e janela. Cinco cenários à parte: sistema sem dispositivo de rede, com a rede degradada e o resto em uso, e quatro configurações recusadas sem nada aplicado: ausente, com dependência circular, com valor excessivo e inconsistente |
| `test --suite system-journey` | Dois boots sobre o mesmo volume, operados pelo shell: arquivos, programas, `ping`, transferência por TCP gravada em arquivo, `sync`, parada com uma aplicação presa em uma conexão e reinício; o segundo boot confere os dados do primeiro e desliga |
| `test --suite release-journey` | Primeira inicialização, atualização para uma imagem de boot de outra versão sobre o mesmo volume e volta à imagem anterior com os dados das duas. Dois cenários à parte: volume com o root mais novo danificado, que fica somente leitura, e volume em formato desconhecido, que não é montado nem alterado |
| `fault-test --suite device-reset` | Dispositivo que para de responder: deadline do pedido, término do driver com IO pendente e reset que falha, sem devolver ao alocador a memória ainda exposta ao dispositivo |
| `fault-test --suite storage-crash` | Estados que uma queda de energia deixaria no disco, com perda, corte e reordenação das escritas ainda sem flush: 66 pontos de crash em 11 transações, 1.000 sequências geradas a partir da seed 1 e o registro de escritas e flushes de um boot no QEMU. Cada estado precisa montar em um commit inteiro, com todo `sync` confirmado. A montagem roda no host, com o código de recuperação do convidado |
| `fault-test --suite network-faults` | 31 espécimes de quadros malformados, de Ethernet a TCP, cada um contado pelo parser da sua camada; 32 pedidos de conexão forjados contra uma fila de aceitação; 1,5 s de enlace caído no meio de uma transferência; reset do dispositivo de rede; reinício do serviço com um cliente à espera |
| `verify-filesystem --corpus` | As 21 imagens de `tests/faults/storage`, válidas, truncadas, incompatíveis e corrompidas, cada uma com o veredito esperado |
| `verify-artifacts --reproduce` | Ligação estática, origem de cada entrada do link, layout e hashes das imagens, e nenhum caminho da máquina de build dentro delas; compila de novo em outro diretório e exige imagens idênticas |
| `inventory` | Versão e hash de cada ferramenta usada no build |

Os relatórios ficam em `build/qemu-riscv64/reports/`, e as capturas de tráfego das suítes de rede em `reports/captures/`.

Para volumes fora das suítes, `create-volume` grava um volume vazio em um arquivo que ainda não existe, `inspect-volume` imprime os superblocks e a árvore de uma imagem e `build-corpus` regrava as imagens do corpus a partir das receitas. Nenhum comando formata ou repara um volume que já existe.

O `kernel-tool` termina com 0 em sucesso, 1 quando uma verificação falha, 2 em erro de uso e 3 quando a infraestrutura não está disponível, por exemplo uma ferramenta fixada que não pôde ser baixada ou executada.

## Homologar e distribuir

```sh
uv run kernel-tool verify --all
uv run kernel-tool repeat-boot --count 1000
uv run kernel-tool benchmark
uv run kernel-tool reproduce-build
uv run kernel-tool fuzz --all --budget-hours 24
uv run kernel-tool soak --hours 24
uv run kernel-tool release-check
```

| Comando | O que faz |
| --- | --- |
| `verify --all` | Roda tudo o que a seção anterior lista, mais `verify-interfaces` e o replay do corpus de fuzzing, e grava um resultado por verificação. Uma verificação que não pôde rodar fica incompleta e não conta como sucesso |
| `verify-interfaces` | Compara os arquivos das interfaces congeladas com os digests de `specs/frozen-interfaces.toml` |
| `fuzz`, `replay-corpus` e `promote-corpus` | Mutam as entradas de boot, de interface, de armazenamento e de rede pelo tempo pedido para cada família; repetem as seeds, o corpus e as regressões; copiam para `tests/fuzz/corpus/` o que alcançou código novo |
| `repeat-boot` | Inicia a imagem de release até o shell e desliga em ordem, o número de vezes pedido, com o resultado de cada boot |
| `benchmark` | Mede boot, memória, IPC, resposta de tarefa pronta, pausas do coletor do supervisor e liberação após término, e compara com os budgets |
| `soak` | Mantém um boot sob carga de processos, arquivos, rede e memória, e reprova crescimento persistente de recursos |
| `reproduce-build` | Compila duas vezes em diretórios vazios e exige imagens iguais entre si e iguais às do build atual |
| `release-check` | Avalia os doze gates de release e monta o pacote em `build/qemu-riscv64/release/`. Termina com status 1 enquanto algum gate estiver em aberto. Não publica, não cria tag e não usa chave |
| `release-sign` e `release-verify` | Assinam os checksums de um pacote com uma chave de fora do repositório e conferem checksums e assinatura |
| `install`, `update` e `rollback` | Instalam um pacote em um diretório com o seu volume de dados, trocam o release instalado e voltam ao anterior quando ele lê o formato do volume |

Os relatórios de homologação ficam em `build/qemu-riscv64/qualification/` e em `build/fuzz/`. A sequência completa está em [Qualificar e montar um release](docs/operations/release-procedure.md), e o uso de um pacote em [Instalar, atualizar e recuperar](docs/operations/installation.md).

## Organização

| Caminho | Conteúdo |
| --- | --- |
| `native/` | Supervisor em C17 e Assembly RISC-V |
| `ports/micropython/` | Port do MicroPython: parte comum, perfil `supervisor` e perfil `user` |
| `src/` | Python do convidado: `kernel_protocol`, `kernel_core`, `kernel_client`, `kernel_drivers`, `kernel_services` e `kernel_apps`, com o shell e o runner de aplicações |
| `apps/` | Programas que a imagem de boot leva em `apps/` |
| `host/kernel_tool/` | Ferramenta de build, execução e verificação |
| `tests/` | Testes do host, corpus de conformidade, testes nativos hospedados, autoteste do convidado, programas adversariais das suítes, corpus de volumes e, em `tests/fuzz/`, os alvos nativos e o corpus de fuzzing |
| `specs/abi/` | Handles, erros, syscalls, capabilities, mensagens, buffers, processos, dispositivos, serviços de dispositivo, imagem de usuário e perfil de recursos |
| `specs/filesystem/` | Formato do volume, imagem de boot e protocolo do serviço de arquivos |
| `specs/network/` | Protocolos suportados e serviço de sockets |
| `specs/system/` | Configuração, gerente e serviço de controle, aplicações |
| `specs/compatibility.md` e `specs/frozen-interfaces.toml` | Política de compatibilidade e digests das interfaces congeladas |
| `config/boot/` | Manifesto dos arquivos da imagem de boot |
| `config/system/` | Configuração do sistema que vai na imagem de boot |
| `config/profiles/` | Máquina, layout de memória, limites e deadlines de cada perfil |
| `config/release/` | Revisão dos avisos de segurança de cada componente fixado |
| `docs/` | Decisões de arquitetura, requisitos, conformidade, segurança, operação e registros de aceite |

## Documentação

Cada documento tem a versão em português, que é a original, e uma versão em inglês ao lado, com o sufixo `.en.md`.

- [Operar o sistema](docs/operations/system-operation.md), [operar a rede](docs/operations/network-operation.md) e [serviços e configuração](docs/operations/services-and-configuration.md)
- [Matriz de requisitos](docs/architecture/requirements.md) e [matriz de conformidade das APIs públicas](docs/architecture/api-conformance.md)
- [Registro de aceite da rede e do ambiente operacional](docs/acceptance/network-and-operational-environment.md) e [registro de homologação](docs/acceptance/qualification-and-distribution.md)
- [Instalar, atualizar e recuperar](docs/operations/installation.md), [qualificar e montar um release](docs/operations/release-procedure.md) e [diagnóstico](docs/operations/diagnostics.md)
- [Política de compatibilidade](specs/compatibility.md)
- [Diferenças entre CPython e o runtime do convidado](docs/architecture/runtime-differences.md)
- [Decisões de arquitetura](docs/decisions/)
- [Formato do volume](specs/filesystem/volume-format.md), [imagem de boot](specs/filesystem/boot-image.md) e [serviço de arquivos](specs/filesystem/file-service.md)
- [Protocolos de rede](specs/network/protocols.md) e [serviço de sockets](specs/network/socket-service.md)
- [Configuração do sistema](specs/system/configuration.md), [gerente e serviço de controle](specs/system/control-service.md) e [aplicações](specs/system/applications.md)
- [Modelo de ameaças](docs/security/threat-model.md), [base computacional confiável](docs/security/trusted-computing-base.md), [revisão da fronteira privilegiada](docs/security/privileged-boundary-review.md) e [resposta a vulnerabilidades](docs/security/vulnerability-response.md)
- [Máquina de referência, workload e budgets](docs/operations/reference-machine.md)
- [Integração contínua](docs/operations/continuous-integration.md)

## Licença

GPL-3.0-only. O texto completo está em [LICENSE](LICENSE).
