# ADR 0004: Modelo de processos

Estado: aceita.

## Contexto

Aplicações não confiáveis não podem rodar dentro do interpretador supervisor, e dois programas não podem compartilhar heap, globals ou estado do coletor.

## Decisão

Cada processo tem um espaço de endereçamento, um runtime MicroPython privado e um único contexto executável. Não há threads dentro de um processo; concorrência interna usa eventos.

O ciclo de vida é `new`, `ready`, `running`, `blocked`, `dying` e `reaped`, com as transições de `src/kernel_core/processes/lifecycle.py`. Qualquer outra transição é erro.

A tabela nativa guarda identidade e estado executável. O escalonador Python guarda só metadados de política. Antes de aplicar uma seleção, o mecanismo nativo revalida geração e estado, para que uma decisão antiga não reative um processo encerrado.

A política inicial tem quatro níveis de prioridade, round-robin dentro do nível e aging: um processo pronto que espera `AGING_THRESHOLD` seleções sobe um nível até executar, e então volta à prioridade base. O quantum nominal é 10 ms e não é garantia de tempo real.

Identidades de processo são handles geracionais, definidos no ADR 0005.

## Consequências

Um runtime por processo consome mais memória do que um interpretador compartilhado. O orçamento inicial é de 16 processos com até 4 MiB de heap cada.

A primeira entrega cobre o modelo de seleção e o de contabilização como código puro, verificado em CPython e no MicroPython alvo. Troca de contexto e preempção vêm depois: até lá um único programa roda em U-mode e devolve o controle por trap.

Esse programa roda com `satp` em modo bare e enxerga toda a memória que o PMP do firmware libera para S e U. A prova cobre a entrada em U-mode e o retorno, não o isolamento de memória.

## Hipóteses a confirmar

- `AGING_THRESHOLD = 8` evita starvation sem inverter prioridades na prática. O modelo prova o limite de espera, não a adequação do valor.
- Doação de prioridade limitada resolve as dependências de IPC entre serviços.
- O timer consegue preemptar a execução nativa do runtime de um processo sem corromper o coletor.
