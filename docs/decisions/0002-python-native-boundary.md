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

A superfície exposta ao Python do supervisor é o módulo `_supervisor`, com quatro funções: `memory_facts`, `resource_limits`, `user_image_facts` e `run_user_image`. Cada binding novo entra nesta lista com o motivo.

## Consequências

Toda chamada entre os dois lados tem custo e precisa de validação nos dois sentidos. O binding recebe e devolve inteiros e tuplas; não devolve ponteiro nem endereço físico reutilizável.

O interpretador supervisor e as políticas congeladas pertencem à TCB. Um erro de política ali tem o mesmo peso de um erro em C.

## Hipóteses a confirmar

- O custo de IPC com políticas em Python cabe no quantum de 10 ms. Medir antes de mover qualquer política para C.
- Handles opacos geracionais bastam para o Python referenciar objetos nativos sem tabela paralela de ownership.
