# ADR 0002: Fronteira entre Python e código nativo

Estado: aceita.

## Contexto

O projeto é Python-first, mas um kernel real precisa de mecanismos que continuam corretos quando um processo Python trava, esgota memória ou envia dados malformados. Sem uma regra escrita, a camada nativa cresce até virar uma segunda implementação das políticas.

## Decisão

Python decide. Código nativo executa e valida.

Ficam em C17 freestanding e Assembly RISC-V: boot, entrada e saída de traps, troca de contexto, MMU, validação de acesso à memória de usuário, primitivas de IPC, enforcement de capabilities e transporte de dispositivos. Assembly cobre só o que exige instrução ou convenção de máquina: ponto de entrada, vetor de traps, entrada em U-mode e leitura de registradores para o GC.

Ficam em Python: escalonamento, admissão de processos, cotas, supervisão, VFS, filesystem, protocolos de rede, comportamento dos drivers e aplicações.

Uma inclusão nativa nova precisa de pelo menos um destes motivos: depende de privilégio, acessa memória física ou registradores, protege a segurança de memória, faz parte da ABI ou integra o interpretador. Conveniência e desempenho não medido não bastam.

O supervisor nativo não depende de Python para tratar uma trap, liberar recurso ou encerrar processo. Python não executa em hard IRQ.

A superfície exposta ao Python do supervisor é o módulo `_supervisor`. Nenhuma função recebe argumentos. Cada binding novo entra nesta tabela com o motivo.

| Binding | Devolve | Motivo |
| --- | --- | --- |
| `machine()` | Hart de boot, base e tamanho da RAM | Fatos do DTB, que só o código nativo lê e valida |
| `limits()` | Limites do perfil compilado e tamanho do heap do supervisor | O perfil faz parte da ABI e o heap vem do layout de linkagem |
| `user_region()` | Base e tamanho da região de usuário | Layout de memória física |
| `arguments()` | Texto de `bootargs` do DTB | Fato do DTB. Nenhuma política usa ainda; o autoteste confere o tipo |
| `inspect_boot_module()` | Estado da validação e os tamanhos de arquivo, memória, heap e stack da imagem | Validação de bytes não confiáveis antes de a política decidir a admissão |
| `run_boot_module()` | Motivo do término, `exit` ou `fault`, com o status ou a causa | Depende de privilégio: carrega a imagem, entra em U-mode e trata as traps |

## Consequências

Toda chamada entre os dois lados tem custo e precisa de validação nos dois sentidos. Os bindings devolvem inteiros, textos e tuplas. Endereços físicos aparecem só como fatos para orçamento e diagnóstico: nenhum binding aceita endereço como argumento.

O interpretador supervisor e as políticas congeladas pertencem à TCB. Um erro de política ali tem o mesmo peso de um erro em C.

## Hipóteses a confirmar

- O custo de IPC com políticas em Python cabe no quantum de 10 ms. Medir antes de mover qualquer política para C.
- Handles opacos geracionais bastam para o Python referenciar objetos nativos sem tabela paralela de ownership.
