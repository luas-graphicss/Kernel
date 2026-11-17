# Imagem de boot

[English](boot-image.en.md)

A imagem de boot é um conjunto de arquivos somente leitura que o `kernel-tool build` grava em `boot.img` e o QEMU entrega como o disco `kernel-boot`. O serviço de arquivos a monta em `boot`. Ela não tem diretórios próprios: cada arquivo guarda o caminho inteiro, e os diretórios saem dos caminhos.

Os inteiros são little-endian e sem sinal. Os blocos têm 4096 bytes e os checksums são CRC-32.

## Conteúdo

`config/boot/manifest.toml` lista os arquivos:

```toml
[[file]]
path = "system/license"
source = "LICENSE"
```

`source` é um arquivo do repositório. Um caminho que sai do repositório, que não existe ou que é um diretório reprova o build. Só as chaves `path` e `source` são aceitas.

O build acrescenta `system/release`, com a versão da interface do sistema e o runtime para o qual a imagem foi feita:

```
abi=1
runtime=micropython-1.29
```

## Layout

| Blocos | Conteúdo |
| --- | --- |
| 0 | Cabeçalho |
| 1 em diante | Tabela de arquivos |
| Depois da tabela | Conteúdo dos arquivos, na ordem da tabela, cada um a partir de um bloco inteiro |

### Cabeçalho

| Offset | Tamanho | Campo | Regra |
| --- | --- | --- | --- |
| 0 | 8 | `magic` | `KBOOTIMG` |
| 8 | 4 | `version` | 1 |
| 12 | 4 | `abi` | Versão da interface do sistema: 1 |
| 16 | 16 | `runtime` | Nome e versão do runtime, completados com zeros |
| 32 | 4 | `entries` | Quantidade de arquivos, até 64 |
| 36 | 4 | `table_bytes` | Tamanho da tabela |
| 40 | 4 | `table_checksum` | CRC-32 da tabela |
| 44 | 4 | `total_blocks` | Blocos da imagem |
| 48 | 12 | reservado | Zero |
| 60 | 4 | `checksum` | CRC-32 dos bytes 0 a 59 |

### Tabela

Uma entrada por arquivo, em ordem estritamente crescente dos bytes do caminho.

| Offset | Tamanho | Campo | Regra |
| --- | --- | --- | --- |
| 0 | 2 | `path_length` | De 1 a 255 |
| 2 | 2 | reservado | Zero |
| 4 | 4 | `first_block` | Primeiro bloco do conteúdo |
| 8 | 4 | `size` | Bytes do arquivo, até 262.144 |
| 12 | 4 | `checksum` | CRC-32 do conteúdo |
| 16 | `path_length` | `path` | Nomes separados por `/`, com as regras de nome do volume persistente |

## Validação

A montagem lê o cabeçalho e a tabela e recusa a imagem inteira, sem montar nada, quando:

- o `magic`, o checksum do cabeçalho ou um campo reservado não confere: `CORRUPTED`;
- a versão do formato, a `abi` ou o `runtime` é diferente do que o sistema em execução espera: `UNSUPPORTED`. O runtime esperado vem de `sys.implementation` no convidado e de `toolchain.lock.toml` no build;
- a imagem é maior que o dispositivo ou menor que a própria tabela;
- a tabela não confere com o checksum, tem mais de 64 entradas, termina dentro de uma entrada, sobra depois da última, tem caminho inválido, repetido ou fora de ordem;
- os arquivos se sobrepõem, deixam bloco sem dono ou não terminam em `total_blocks`;
- um caminho passa por dentro de um arquivo.

O conteúdo de um arquivo é lido e conferido com o checksum na primeira leitura. Um arquivo que não confere devolve `CORRUPTED` para essa leitura; os outros continuam legíveis.

Toda mudança devolve `READ_ONLY`. A montagem aparece no estado do serviço como somente leitura, com o motivo `verified`.

O formato e a validação estão em `src/kernel_services/filesystem/boot/layout.py` e `backends/boot.py`. A imagem é montada pelo host em `host/kernel_tool/storage/boot_image.py`, com as mesmas funções de codificação.
