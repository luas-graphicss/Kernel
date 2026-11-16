# Kernel

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
- Modelos puros de handles geracionais, seleção de processos e contabilização de recursos. Um corpus de 10.000 transições roda em CPython e dentro do convidado, e os resultados precisam ser iguais.
- `kernel-tool`, que baixa a toolchain fixada por hash, compila, inicia o QEMU com deadline, executa os cenários e inspeciona as imagens. Ele também cria, verifica e inspeciona volumes, e reconstrói os estados que uma queda de energia deixaria no disco.

Ainda não existem rede nem shell. O kernel usa um único hart, e o isolamento foi exercitado só no QEMU com TCG. A durabilidade foi demonstrada só no `virtio-blk` do QEMU: um disco que confirme um flush que não fez está fora do que foi testado.

## Requisitos do host

- Linux x86_64. Os pacotes de `toolchain.lock.toml` são para essa plataforma.
- [uv](https://docs.astral.sh/uv/). O projeto é desenvolvido com a versão 0.13.5. O uv instala o Python 3.13 indicado em `.python-version`.
- `make` e o GCC do host, acessível como `cc` e como `gcc`, com AddressSanitizer e UndefinedBehaviorSanitizer. Ele compila o `mpy-cross` e os testes nativos hospedados.
- Cerca de 2,5 GB livres para a toolchain. Ela fica em `~/.cache/kernel-tool` ou no diretório indicado por `KERNEL_TOOL_CACHE`.

## Compilar e executar

```sh
uv sync --frozen
uv run kernel-tool toolchain
uv run kernel-tool build
uv run kernel-tool run
```

`toolchain` baixa e confere o GCC, o QEMU e o MicroPython fixados. `build` gera as imagens em `build/qemu-riscv64/`. `run` inicia o QEMU, imprime o console serial e falha se o kernel não terminar com `kernel: status=ok` dentro do deadline. O perfil padrão é `qemu-riscv64`; `--profile` escolhe outro arquivo de `config/profiles/`.

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
uv run kernel-tool fault-test --suite device-reset
uv run kernel-tool fault-test --suite storage-crash
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
| `fault-test --suite device-reset` | Dispositivo que para de responder: deadline do pedido, término do driver com IO pendente e reset que falha, sem devolver ao alocador a memória ainda exposta ao dispositivo |
| `fault-test --suite storage-crash` | Estados que uma queda de energia deixaria no disco, com perda, corte e reordenação das escritas ainda sem flush: 66 pontos de crash em 11 transações, 1.000 sequências geradas a partir da seed 1 e o registro de escritas e flushes de um boot no QEMU. Cada estado precisa montar em um commit inteiro, com todo `sync` confirmado. A montagem roda no host, com o código de recuperação do convidado |
| `verify-filesystem --corpus` | As 21 imagens de `tests/faults/storage`, válidas, truncadas, incompatíveis e corrompidas, cada uma com o veredito esperado |
| `verify-artifacts --reproduce` | Ligação estática, origem de cada entrada do link, layout e hashes das imagens; compila de novo em outro diretório e exige imagens idênticas |
| `inventory` | Versão e hash de cada ferramenta usada no build |

Os relatórios ficam em `build/qemu-riscv64/reports/`.

Para volumes fora das suítes, `create-volume` grava um volume vazio em um arquivo que ainda não existe, `inspect-volume` imprime os superblocks e a árvore de uma imagem e `build-corpus` regrava as imagens do corpus a partir das receitas. Nenhum comando formata ou repara um volume que já existe.

O `kernel-tool` termina com 0 em sucesso, 1 quando uma verificação falha, 2 em erro de uso e 3 quando a infraestrutura não está disponível, por exemplo uma ferramenta fixada que não pôde ser baixada ou executada.

## Organização

| Caminho | Conteúdo |
| --- | --- |
| `native/` | Supervisor em C17 e Assembly RISC-V |
| `ports/micropython/` | Port do MicroPython: parte comum, perfil `supervisor` e perfil `user` |
| `src/` | Python do convidado: `kernel_protocol`, `kernel_core`, `kernel_client`, `kernel_drivers` e `kernel_services` |
| `host/kernel_tool/` | Ferramenta de build, execução e verificação |
| `tests/` | Testes do host, corpus de conformidade, testes nativos hospedados, autoteste do convidado, programas adversariais das suítes e corpus de volumes |
| `specs/abi/` | Handles, erros, syscalls, capabilities, mensagens, buffers, processos, dispositivos, serviços de dispositivo, imagem de usuário e perfil de recursos |
| `specs/filesystem/` | Formato do volume, imagem de boot e protocolo do serviço de arquivos |
| `config/boot/` | Manifesto dos arquivos da imagem de boot |
| `config/profiles/` | Máquina, layout de memória, limites e deadlines de cada perfil |
| `docs/` | Decisões de arquitetura, requisitos, segurança e operação |

## Documentação

- [Matriz de requisitos](docs/architecture/requirements.md)
- [Diferenças entre CPython e o runtime do convidado](docs/architecture/runtime-differences.md)
- [Decisões de arquitetura](docs/decisions/)
- [Formato do volume](specs/filesystem/volume-format.md), [imagem de boot](specs/filesystem/boot-image.md) e [serviço de arquivos](specs/filesystem/file-service.md)
- [Modelo de ameaças](docs/security/threat-model.md) e [base computacional confiável](docs/security/trusted-computing-base.md)
- [Máquina de referência, workload e budgets](docs/operations/reference-machine.md)
- [Integração contínua](docs/operations/continuous-integration.md)

## Licença

GPL-3.0-only. O texto completo está em [LICENSE](LICENSE).
