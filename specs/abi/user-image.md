# Imagem de usuário

Formato do arquivo que carrega um programa de U-mode. O firmware o entrega como módulo de boot, na faixa `linux,initrd-start` a `linux,initrd-end` do nó `/chosen` do DTB.

A imagem é o conteúdo que deve estar na memória a partir de `load_base`, começando pelo próprio cabeçalho. Não há relocação.

## Cabeçalho

56 bytes, inteiros little-endian sem sinal:

| Offset | Tamanho | Campo | Regra |
| --- | --- | --- | --- |
| 0 | 4 | `magic` | Bytes `4B 55 49 4D`, ASCII `KUIM` |
| 4 | 4 | `version` | `1` |
| 8 | 8 | `load_base` | Igual à base da região de usuário do perfil |
| 16 | 8 | `file_bytes` | Bytes a copiar, cabeçalho incluído |
| 24 | 8 | `memory_bytes` | Memória total a partir de `load_base`: arquivo, BSS, heap e stack |
| 32 | 8 | `entry` | Endereço da primeira instrução |
| 40 | 8 | `heap_bytes` | Heap que o runtime da imagem reserva |
| 48 | 8 | `stack_bytes` | Stack que a imagem reserva |

## Validação

O supervisor rejeita a imagem, com o motivo indicado, quando:

| Motivo | Condição |
| --- | --- |
| `truncated-header` | O módulo tem menos de 56 bytes |
| `bad-magic` | `magic` diferente |
| `unsupported-version` | `version` diferente de 1 |
| `segment-outside-region` | `load_base` diferente da base da região, ou `memory_bytes` maior que a região |
| `bad-file-size` | `file_bytes` menor que 56, maior que o módulo ou maior que `memory_bytes` |
| `bad-entry` | `entry` fora de `[load_base + 56, load_base + file_bytes)` ou em endereço ímpar |
| `bad-reservation` | `heap_bytes + stack_bytes` maior que `memory_bytes - file_bytes` |

Só depois da validação o supervisor copia `file_bytes` para a região e zera o restante até `memory_bytes`.

A política Python recebe `memory_bytes`, `heap_bytes`, `stack_bytes` e `file_bytes` e decide a admissão: o heap declarado precisa caber no limite por processo do perfil.

O cabeçalho é gerado pelo link da imagem, em `ports/micropython/user/image_header.S`.
