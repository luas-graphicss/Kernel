# Formato do volume persistente

[English](volume-format.en.md)

Formato versão 1. Um volume é uma sequência de blocos de 4096 bytes em um dispositivo de blocos. Dados e metadados são copy-on-write: uma transação nunca sobrescreve um bloco que um root protegido ainda alcança. As decisões estão no ADR 0006 e a implementação em `src/kernel_services/filesystem/`.

Os inteiros são little-endian e sem sinal. Todo checksum é o CRC-32 do `zlib`.

## Geometria

| Item | Valor |
| --- | --- |
| Bloco | 4096 bytes |
| Blocos 0 e 1 | Slots de superblock |
| Bloco 2 em diante | Árvore: diretórios, índices de arquivo e dados |
| Menor volume | 8 blocos |
| Maior volume | 65.536 blocos, 256 MiB |

Em um dispositivo maior que o maior volume, a criação usa só os primeiros 65.536 blocos. Um superblock que declara mais blocos do que o dispositivo tem é recusado.

## Superblock

O superblock ocupa os primeiros 64 bytes do seu bloco. O resto do bloco é zero.

| Offset | Tamanho | Campo | Regra |
| --- | --- | --- | --- |
| 0 | 8 | `magic` | `KVOLSUPR` |
| 8 | 4 | `version` | 1 |
| 12 | 4 | `block_bytes` | 4096 |
| 16 | 4 | `total_blocks` | De 8 a 65.536, e não mais que o dispositivo |
| 20 | 4 | reservado | Zero |
| 24 | 8 | `generation` | A partir de 1. O resto da divisão por 2 é o número do slot |
| 32 | 8 | `next_node` | Próximo número de nó a atribuir, maior que 1 |
| 40 | 4 | `root_block` | Bloco do diretório raiz, de 2 a `total_blocks - 1` |
| 44 | 4 | `root_checksum` | CRC-32 do bloco do diretório raiz |
| 48 | 8 | `volume` | Identificador escolhido na criação |
| 56 | 4 | reservado | Zero |
| 60 | 4 | `checksum` | CRC-32 dos bytes 0 a 59 |

A geração 1 fica no slot 1, a 2 no slot 0, e assim por diante. Publicar a geração seguinte nunca sobrescreve o superblock da geração corrente.

A leitura de um slot confere, nesta ordem: `magic`, depois `version` e `block_bytes`, depois o checksum, depois os demais campos. Versão ou tamanho de bloco diferentes devolvem `UNSUPPORTED` sem olhar o checksum, porque outro formato pode calcular o checksum de outro jeito. Qualquer outra falha devolve `CORRUPTED`.

## Blocos de metadados

Diretórios e índices de arquivo começam com um cabeçalho de 16 bytes.

| Offset | Tamanho | Campo | Regra |
| --- | --- | --- | --- |
| 0 | 4 | `magic` | `KDIR` para diretório, `KIDX` para índice de arquivo |
| 4 | 4 | `payload_bytes` | Até 4080 |
| 8 | 8 | `generation` | Geração do commit que escreveu o bloco |
| 16 | `payload_bytes` | payload | Conteúdo do tipo |

Os bytes depois do payload são zero. A geração do bloco é pelo menos 1 e não passa da geração de quem aponta para ele: o superblock, no caso da raiz, ou o diretório pai nos demais casos.

Um bloco de metadados não guarda o próprio checksum. O CRC-32 do bloco inteiro fica no ponteiro que leva a ele. Trocar um bloco exige reescrever todos os ancestrais até o superblock.

## Diretório

O payload é a sequência das entradas, em ordem estritamente crescente dos bytes do nome. Um diretório cabe em um bloco.

| Offset | Tamanho | Campo | Regra |
| --- | --- | --- | --- |
| 0 | 1 | `kind` | 1 para arquivo, 2 para diretório |
| 1 | 1 | `name_length` | De 1 a 255 |
| 2 | 2 | reservado | Zero |
| 4 | 4 | `block` | Bloco do diretório filho ou do índice do arquivo. Zero em arquivo vazio |
| 8 | 4 | `checksum` | CRC-32 do bloco apontado. Zero quando não há bloco |
| 12 | 8 | `node` | Número do nó: maior que 1, menor que `next_node` e único no volume |
| 20 | 8 | `size` | Bytes do arquivo, até 2.084.864. Zero em diretório |
| 28 | `name_length` | `name` | Nome |

Um nome é UTF-8 válido, sem byte zero e sem `/`. `.` e `..` não são nomes. A raiz tem o número de nó 1 e não aparece em nenhuma entrada. Números de nó não são reutilizados.

## Arquivo

Um arquivo vazio não tem bloco. Os demais têm um bloco de índice, cujo payload é:

| Offset | Tamanho | Campo | Regra |
| --- | --- | --- | --- |
| 0 | 1 | `level` | Zero: os ponteiros levam a blocos de dados |
| 1 | 7 | reservado | Zero |
| 8 | 8 por ponteiro | ponteiros | Bloco, em 4 bytes, e CRC-32 do bloco, em 4 bytes |

O índice tem exatamente um ponteiro para cada 4096 bytes do tamanho do arquivo, arredondado para cima. Um ponteiro com bloco zero é um buraco: lê como zeros, não ocupa espaço e tem checksum zero. Um bloco de dados guarda 4096 bytes do arquivo, sem cabeçalho. Os bytes do último bloco depois do fim do arquivo são zero.

## Limites

| Limite | Valor | Ao atingir |
| --- | --- | --- |
| Nome | 255 bytes | `INVALID_ARGUMENT` |
| Entradas de um diretório | 4080 bytes: 28 fixos mais o nome, por entrada | `LIMIT_EXCEEDED` |
| Profundidade | 32 níveis de diretório, contando a raiz | `LIMIT_EXCEEDED` |
| Arquivo | 2.084.864 bytes, 509 blocos de dados | `LIMIT_EXCEEDED` |
| Espaço | Blocos livres menos a reserva | `NO_SPACE` |

Symlinks e hard links não existem no formato.

## O que uma árvore válida garante

A verificação parte de um superblock e percorre tudo o que ele alcança. Ela recusa a árvore com `CORRUPTED` quando encontra:

- ponteiro para fora da faixa de blocos da árvore;
- bloco referenciado duas vezes, o que também cobre ciclos de diretórios;
- número de nó repetido, igual ao da raiz ou nunca atribuído;
- mais de 32 níveis de diretório;
- bloco de tipo diferente do que o ponteiro espera, checksum que não confere, payload maior que o bloco ou bytes depois do payload;
- bloco com geração maior que a de quem aponta para ele;
- entrada truncada, com nome inválido, fora de ordem, de tipo desconhecido ou com tamanho impossível;
- índice que não cobre o tamanho do arquivo, ou buraco com checksum.

O serviço de arquivos confere todos os metadados ao montar e o checksum de cada bloco de dados ao ler. `kernel-tool verify-filesystem` confere também todos os blocos de dados.

## Transação e commit

As mudanças se acumulam em memória. O conteúdo escrito em um arquivo vai direto para o dispositivo, em blocos livres. Um bloco alocado pela transação em curso pode ser regravado no lugar; um bloco alcançado por um root publicado, não.

O commit da geração `G + 1` segue esta ordem:

1. Escreve em blocos livres o índice de cada arquivo alterado e o bloco de cada diretório alterado, dos mais fundos para a raiz, todos com a geração `G + 1`.
2. Faz flush do dispositivo.
3. Escreve o superblock da geração `G + 1` no slot dela.
4. Faz flush do dispositivo.
5. Responde a quem pediu.

O commit publica de uma vez tudo o que mudou no volume desde o commit anterior. Não há commit de um arquivo só.

| Falha | Resultado para quem pediu | Estado no dispositivo |
| --- | --- | --- |
| Nos passos 1 ou 2 | `IO_ERROR` | Geração `G` |
| Nos passos 3 ou 4 | `UNKNOWN_OUTCOME` | Geração `G` ou `G + 1` |

Depois de qualquer uma das duas, o volume fica marcado como falho e toda operação devolve `IO_ERROR` até ele ser montado de novo. A montagem seguinte decide pelo que está no dispositivo.

## Pontos de crash

O modelo de falha é perda de energia: toda escrita ainda não seguida de flush pode se perder, em qualquer combinação, e uma delas pode ficar pela metade. Para um commit de `G` para `G + 1`:

| Momento do crash | O que a recuperação monta |
| --- | --- |
| Antes do flush da árvore, com qualquer parte das escritas gravada | `G`. As escritas só tocaram blocos livres em `G` |
| Depois do flush da árvore e antes do superblock | `G` |
| Com a escrita do superblock em curso | `G` se ela se perdeu ou ficou pela metade, `G + 1` se chegou inteira |
| Depois do flush final | `G + 1` |

Nenhum momento monta uma mistura das duas gerações, e uma geração já confirmada a quem pediu nunca deixa de montar.

`kernel-tool fault-test --suite storage-crash` exercita isso em três estágios, todos registrados em `reports/storage-crash.json`:

| Estágio | O que faz |
| --- | --- |
| `crash-matrix` | Onze transações mínimas, com um crash depois de cada evento do dispositivo. Até quatro escritas voláteis, todas as combinações de perda são testadas; acima disso, os prefixos, cada escrita sozinha, cada escrita ausente e cada escrita pela metade. As transações são criar arquivo, acrescentar, sobrescrever um trecho, truncar, estender, criar diretório, renomear, renomear por cima, mover para outro diretório, remover arquivo e remover diretório |
| `crash-sequences` | Sequências geradas de 24 operações com 8 crashes cada. O padrão são 1.000 sequências a partir da seed 1; `--sequences` e `--seed` mudam os dois, e o relatório guarda as seeds |
| `flush-trace-replay` | Lê o log de escritas e flushes que o QEMU gravou enquanto o convidado executava sete transações, confere que cada superblock saiu entre dois flushes e repete os crashes sobre esse log |

Em cada imagem, a recuperação precisa montar leitura e escrita, em uma geração que foi commitada, não mais antiga que a última confirmada, e com o mesmo digest que essa geração tinha.

## Alocação e reutilização

O volume não guarda mapa de blocos livres. A montagem reconstrói o mapa pela árvore: está em uso o que o root escolhido alcança.

- Um bloco liberado pela transação que leva a `G + 1` continua alcançado pelo root de `G`. Ele só volta a ser livre quando `G + 2` é publicada e o superblock de `G` deixa de existir.
- Na montagem com dois superblocks válidos, os blocos que só o root anterior alcança ficam protegidos pela mesma regra.
- Um bloco alocado e liberado dentro da mesma transação volta a ser livre na hora.
- Blocos escritos por uma transação interrompida não são alcançados por nenhum root. Na montagem seguinte eles já são livres, sem varredura nem reparo.

O volume mantém uma reserva de `total_blocks / 8` blocos, limitada a 34, mais um bloco para cada nó de metadados com mudança pendente. Operações que consomem espaço devolvem `NO_SPACE` antes de começar quando não cabem fora da reserva. Operações que liberam espaço, como remover, encurtar e renomear por cima, usam a reserva. Uma escrita pode ser parcial: devolve quantos bytes aceitou, ou `NO_SPACE` quando não aceitou nenhum.

Quando falta espaço e há blocos esperando a geração seguinte, o volume faz dois commits para liberá-los e tenta a operação mais uma vez.

## Montagem e recuperação

1. Um dispositivo com menos de 8 blocos é recusado com `CORRUPTED`.
2. Os dois slots são lidos. Se algum guarda um superblock de outra versão ou de outro tamanho de bloco, o volume inteiro é recusado com `UNSUPPORTED`, mesmo que o outro slot seja legível: o slot desconhecido pode ser o estado mais novo.
3. Sem nenhum superblock válido, o volume é recusado com `CORRUPTED`.
4. Os superblocks válidos são tentados do mais novo para o mais antigo. Vale o primeiro cuja árvore passa na verificação. Se nenhuma passa, `CORRUPTED`.
5. O modo da montagem sai da tabela abaixo.

| Situação | Modo | Motivo |
| --- | --- | --- |
| Dois superblocks de gerações consecutivas, árvore do mais novo válida | Leitura e escrita | `clean` |
| O mesmo, mas a árvore do anterior não é válida | Leitura e escrita | `previous-root-damaged` |
| Um superblock só, de geração 1 | Leitura e escrita | `clean` |
| Um superblock só, de outra geração | Leitura e escrita | `recovered` |
| Árvore do mais novo inválida, montado o anterior | Somente leitura | `newest-root-damaged` |
| Dois superblocks de gerações não consecutivas | Somente leitura | `generation-gap` |
| Dispositivo somente leitura | Somente leitura | `device-read-only` |
| Dispositivo sem comando de flush | Somente leitura | `device-without-flush` |

Um volume somente leitura devolve `READ_ONLY` a qualquer mudança. O sistema nunca cria, formata nem repara um volume para conseguir montar: um dispositivo em branco aparece como montagem indisponível, com o erro, e o boot segue sem ela.

Sem flush o volume não aceita escrita, porque o passo 2 e o passo 4 do commit não teriam efeito e nenhuma confirmação valeria.

## Digest

Ferramentas e testes comparam volumes pelo digest da árvore: um CRC-32 encadeado sobre o caminho, o tipo e o tamanho de cada entrada, seguidos do conteúdo de cada arquivo. O digest depende do que o volume guarda, não de onde os blocos estão nem de quantos commits houve.

## Corpus

`tests/faults/storage/` guarda 21 imagens e o veredito esperado de cada uma em `manifest.toml`: volumes válidos, com um superblock só, com checksum ou geração errados, truncados, de versão ou tamanho de bloco desconhecidos, com bloco referenciado duas vezes, ciclo de diretórios, ponteiro para fora, tipo trocado, número de nó repetido e bloco mais novo que o root. `kernel-tool verify-filesystem --corpus tests/faults/storage` confere todas, e `kernel-tool build-corpus` as regrava a partir das receitas de `host/kernel_tool/corpus/recipes.py`.
