# Imagem de usuário

Formato do arquivo que carrega os programas de U-mode. O firmware o entrega como módulo de boot, na faixa `linux,initrd-start` a `linux,initrd-end` do nó `/chosen` do DTB.

A imagem contém o runtime MicroPython de usuário e os módulos Python congelados. Todo processo é criado a partir dela, e o programa de cada um é o módulo indicado no pedido de criação. O conteúdo é linkado para o endereço virtual `load_base`, começando pelo próprio cabeçalho. Não há relocação.

## Cabeçalho

72 bytes, inteiros little-endian sem sinal:

| Offset | Tamanho | Campo | Regra |
| --- | --- | --- | --- |
| 0 | 4 | `magic` | Bytes `4B 55 49 4D`, ASCII `KUIM` |
| 4 | 4 | `version` | `2` |
| 8 | 8 | `load_base` | Igual à base da região de usuário do perfil |
| 16 | 8 | `file_bytes` | Tamanho do arquivo, cabeçalho incluído |
| 24 | 8 | `entry` | Endereço da primeira instrução |
| 32 | 8 | `text_bytes` | Código, a partir de `load_base` |
| 40 | 8 | `rodata_bytes` | Dados somente leitura, logo depois do código |
| 48 | 8 | `data_bytes` | Dados graváveis e BSS, logo depois dos dados somente leitura |
| 56 | 8 | `heap_bytes` | Heap do runtime quando o pedido de criação não escolhe outro |
| 64 | 8 | `stack_bytes` | Stack |

## Espaço de endereçamento

Cada processo recebe estas faixas, na ordem, a partir de `load_base`:

| Faixa | Permissões | Páginas |
| --- | --- | --- |
| Código | Leitura e execução | As mesmas em todos os processos |
| Dados somente leitura | Leitura | As mesmas em todos os processos |
| Dados e BSS | Leitura e escrita | Privadas |
| Heap | Leitura e escrita | Privadas |
| Página de guarda, 4096 bytes | Nenhuma | Não mapeada |
| Stack | Leitura e escrita | Privadas |

Nenhuma página é gravável e executável ao mesmo tempo. Uma página privada é zerada antes de receber conteúdo. Fora dessas faixas e dos buffers mapeados, qualquer acesso é uma falha de página que encerra o processo; isso inclui o endereço zero, a memória do supervisor, a memória livre e os registradores de dispositivos.

## Validação

O supervisor rejeita a imagem, com o motivo indicado, quando:

| Motivo | Condição |
| --- | --- |
| `truncated-header` | O módulo tem menos de 72 bytes |
| `bad-magic` | `magic` diferente |
| `unsupported-version` | `version` diferente de 2 |
| `segment-outside-region` | `load_base` diferente da base da região, ou a soma de código, dados, heap, guarda e stack maior que a região |
| `bad-segment` | `text_bytes` zero, ou `text_bytes`, `rodata_bytes` ou `data_bytes` que não é múltiplo de 4096 |
| `bad-reservation` | `heap_bytes` ou `stack_bytes` zero ou que não é múltiplo de 4096 |
| `bad-file-size` | `file_bytes` menor que 72, maior que o módulo ou maior que `text_bytes + rodata_bytes + data_bytes` |
| `bad-entry` | `entry` em endereço ímpar, antes do fim do cabeçalho ou depois do código presente no arquivo |

A rejeição aparece como `policy: rejected=boot-module reason=<motivo>` e encerra o boot antes de qualquer processo existir.

O heap pedido em `process_spawn` substitui `heap_bytes` e passa pela mesma conta de tamanho. A política Python aplica o limite de heap por processo do perfil antes de a criação começar.

O cabeçalho é gerado pelo link da imagem, em `ports/micropython/user/image_header.S`. Os offsets estão em `native/include/kernel/abi/user_image.h` e o leitor do host em `host/kernel_tool/images/user_image.py`.
