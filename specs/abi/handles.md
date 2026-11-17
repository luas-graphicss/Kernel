# Handles

[English](handles.en.md)

Um handle identifica um slot em uma tabela e a geração desse slot. Ele é opaco para quem o recebe e só tem significado na tabela que o emitiu.

## Formato

Inteiro sem sinal de 64 bits:

| Bits | Campo | Regra |
| --- | --- | --- |
| 0 a 23 | `index` | Posição do slot, de 0 até a capacidade da tabela menos 1 |
| 24 a 55 | `generation` | De 1 a `0xFFFFFFFF` |
| 56 a 63 | reservado | Zero |

O valor `0` é o handle inválido. Como a geração começa em 1, nenhum handle emitido vale zero.

## Ciclo de um slot

1. A tabela nasce com todos os slots livres e geração 1.
2. `allocate` ocupa um slot livre e devolve o handle com a geração atual. Sem slot livre, falha com `LIMIT_EXCEEDED`.
3. `resolve` aceita o handle só se o índice existir, o slot estiver ocupado, a geração coincidir e os bits reservados forem zero. Caso contrário, `INVALID_HANDLE`.
4. `release` valida como `resolve`, libera o slot e soma 1 à geração.
5. Se a geração já era a máxima, o slot é aposentado: não volta à lista de livres e a capacidade útil da tabela diminui em um.

Depois de `release`, o handle antigo falha em `resolve` para sempre, inclusive quando o slot é reutilizado.

A escolha do próximo slot livre é LIFO: o slot liberado por último é o primeiro a ser reutilizado. Isso é determinístico e faz parte do contrato testado pelo corpus de conformidade.

## Autoridade

Um handle não carrega autoridade fora da tabela do processo que o recebeu. Escrever o inteiro em um payload e enviá-lo a outro processo não transfere a capability. As regras estão no ADR 0005.

A implementação de referência é `kernel_protocol.identity`. A largura da geração é parâmetro da tabela, para que os testes esgotem o contador com poucos passos; o formato de produção usa 32 bits.
