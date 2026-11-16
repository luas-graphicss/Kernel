# Modelo de ameaças

Descreve contra o quê o kernel se protege, o que fica fora e como cada fronteira de entrada é limitada e testada. Vale para o perfil `qemu-riscv64`.

## Ativos

- Integridade do supervisor nativo, do interpretador supervisor e das políticas congeladas.
- Isolamento entre processos: memória, capabilities e recursos contabilizados.
- Dados persistidos e a garantia de `fsync`.
- Disponibilidade: CPU, memória, filas e a reserva do supervisor.
- Cadeia de build: toolchain, fontes fixadas e a imagem produzida.

## Atores

| Ator | Confiança |
| --- | --- |
| Aplicação em U-mode | Nenhuma. Pode ser maliciosa ou defeituosa |
| Serviço em U-mode | Limitada às capabilities que recebeu; responde pelos recursos que administra |
| Peer de rede | Nenhuma |
| Conteúdo de volume, imagem de boot e DTB | Não confiável até ser validado |
| Operador | Confiável: escolhe imagem, perfil e argumentos de boot |

Ficam fora do modelo: host comprometido, firmware malicioso, dispositivo físico malicioso, DMA não mediado e canais laterais de microarquitetura. Validar ponteiros em Python não resolve nenhum deles.

## Fronteiras de entrada

Cada fronteira tem limites, um resultado de erro definido e um teste negativo.

| Fronteira | Limites | Resultado de erro | Evidência |
| --- | --- | --- | --- |
| DTB entregue pelo firmware | 64 KiB, versão 17, blocos em ordem e sem sobreposição, profundidade 8, nomes de até 255 bytes, 16 faixas reservadas, uma faixa de RAM | `boot: device tree rejected reason=` e boot encerrado | Harness `tests/native/device_tree_test.c` com truncamento e mutações sob ASan e UBSan; cenários `device-tree-too-large` e `device-tree-without-memory` |
| Imagem de usuário em `/chosen` | Cabeçalho de 56 bytes, base igual à da região de usuário, tamanhos dentro da região e do módulo, entrada dentro do arquivo | `boot: user image rejected reason=` e boot encerrado | Harness `tests/native/user_image_test.c`; cenários `incompatible-segment` e `missing-user-image` |
| Argumentos de syscall | Número conhecido; buffer inteiro dentro da região do processo; 256 bytes por `debug_write` | Código de erro negativo em `a0` | Cenário `syscall-contract` |
| Programa em U-mode | Qualquer trap que não seja `ecall` encerra o processo | Relatório `user: fault` e status devolvido à política | Cenário `user-fault` |
| Argumentos de boot | 255 bytes; a imagem de produto não os interpreta | Ignorados | Harness do DTB |

IPC, manifestos, volumes, caminhos, respostas de dispositivos e pacotes de rede entram nesta tabela junto com o mecanismo que os introduz.

## Invariantes testáveis

- Entrada de boot inválida encerra o boot antes de o interpretador iniciar.
- Uma syscall com ponteiro fora da região do processo não lê nem escreve fora dela.
- Um handle liberado nunca volta a resolver, mesmo depois de o slot ser reutilizado.
- Cobrar um recurso é atômico: ou todos os limites passam, ou nada muda. A soma das contas é igual ao uso global.
- O ELF do kernel é estático, não tem símbolo indefinido e só liga `libgcc` além dos objetos do projeto.

## Riscos residuais

- Não há MMU ativa. O programa em U-mode lê e escreve toda a RAM que o PMP libera, inclusive a do supervisor. Código não confiável não deve rodar nesta imagem.
- A validação de ponteiros de syscall compara faixas contra a região de usuário. Ela vira `copy_from_user` com tratamento de page fault quando a MMU existir.
- O hash de um download prova que o arquivo é o que o lock registrou, não que o upstream é confiável.
- TCG não reproduz temporização nem falhas de hardware real.
