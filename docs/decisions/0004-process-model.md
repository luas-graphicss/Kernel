# ADR 0004: Modelo de processos

Estado: aceita.

## Contexto

Aplicações não confiáveis não podem rodar dentro do interpretador supervisor, e dois programas não podem compartilhar heap, globals ou estado do coletor.

## Decisão

Cada processo tem um espaço de endereçamento, um runtime MicroPython privado e um único contexto executável. Não há threads dentro de um processo; concorrência interna usa eventos.

O ciclo de vida é `new`, `ready`, `running`, `blocked`, `dying` e `reaped`, com as transições de `src/kernel_core/processes/lifecycle.py`. Qualquer outra transição é erro.

A tabela nativa guarda identidade e estado executável. O escalonador Python guarda só metadados de política. Antes de aplicar uma seleção, o mecanismo nativo revalida geração e estado, para que uma decisão antiga não reative um processo encerrado.

A política inicial tem quatro níveis de prioridade, round-robin dentro do nível e aging: um processo pronto que espera `AGING_THRESHOLD` seleções sobe um nível até executar, e então volta à prioridade base. O quantum nominal é 10 ms e não é garantia de tempo real.

Quem bloqueia esperando o dono de um endpoint empresta a ele a própria prioridade, por até 8 processos encadeados. A doação termina junto com a espera.

Identidades de processo são handles geracionais, definidos no ADR 0005.

## Consequências

Um runtime por processo consome mais memória do que um interpretador compartilhado. O orçamento inicial é de 16 processos com até 4 MiB de heap cada.

O modelo de seleção e o de contabilização são código puro, verificado em CPython e no MicroPython alvo. O supervisor Python os aplica sobre os mecanismos nativos: a cada passo escolhe um processo e pede ao código nativo que o execute por um quantum. A volta diz se o processo foi preemptado, cedeu a vez, bloqueou, terminou ou pediu a criação de outro.

Todo processo nasce da mesma imagem de usuário. Código e dados somente leitura são as mesmas páginas em todos os processos; dados, heap e stack são privados. O layout está em `specs/abi/user-image.md`, e criação, espera e término em `specs/abi/processes.md`.

Interrupções só são aceitas enquanto um processo roda em U-mode. O supervisor, nativo ou Python, nunca é interrompido. A interrupção do timer salva o contexto do processo e devolve o controle ao laço nativo, que expira as esperas vencidas e encerra o quantum sem executar Python e sem alocar.

A suíte `processes` preempta um programa que aloca sem parar e um laço que nunca cede a vez. Os dois seguem executando até serem encerrados, e os padrões de registradores inteiros e de ponto flutuante dos outros processos não mudam.

## Hipóteses a confirmar

- `AGING_THRESHOLD = 8` evita starvation sem inverter prioridades na prática. O modelo prova o limite de espera, não a adequação do valor.
- Doação de prioridade limitada resolve as dependências de IPC entre serviços.
