# ADR 0006: Persistência

Estado: aceita.

## Contexto

O sistema precisa guardar arquivos e sobreviver a queda de energia sem uma stack POSIX nativa. Decidir o contrato de durabilidade depois do formato leva a `fsync` que promete o que o disco não entrega.

## Decisão

Há três backends atrás do serviço VFS:

- Imagem de boot, somente leitura.
- Filesystem temporário, sem promessa de persistência.
- Volume persistente em formato próprio e versionado, implementado em Python, com dados e metadados copy-on-write.

O volume persistente segue este contrato:

1. Blocos de 4096 bytes. Metadados têm tipo, geração e comprimento validado, e todo ponteiro carrega o CRC-32 do bloco que aponta. Árvores têm profundidade e fan-out limitados.
2. Dois superblocks alternados apontam para o root comprometido, cada um com sua geração.
3. Uma transação escreve dados e metadados novos sem sobrescrever o que os roots protegidos ainda alcançam.
4. O novo root só é publicado depois de o transporte confirmar ordenação e flush dos blocos.
5. `fsync` só retorna sucesso depois do flush que segue a publicação do root.
6. A recuperação escolhe o root consistente de maior geração e valida o que ele alcança.
7. O volume não guarda mapa de blocos livres. A montagem o reconstrói pelos roots, e um bloco liberado só é reutilizado depois que o root que o alcançava deixa de existir.

O commit é do volume inteiro, não de um arquivo. `fsync` em qualquer arquivo publica tudo o que mudou na montagem.

`write` aceito não significa durabilidade, e `close` não substitui `fsync`. Disco cheio, checksum incorreto ou formato desconhecido produzem erro ou montagem somente leitura. O sistema nunca formata um volume para conseguir inicializar.

Symlinks e hard links ficam fora da versão 1.0.

O formato está em `specs/filesystem/volume-format.md`, a imagem de boot em `specs/filesystem/boot-image.md` e o serviço em `specs/filesystem/file-service.md`. O código fica em `src/kernel_services/filesystem/` e roda igual no convidado e no `kernel-tool`, que o usa para criar, verificar e inspecionar imagens.

## Consequências

O filesystem é trabalho grande e a prova de consistência após falha bloqueia a entrega dele. Checksum detecta corrupção, mas não autentica o disco contra adulteração deliberada.

Como o commit é do volume inteiro, um `fsync` custa a reescrita de todos os diretórios alterados desde o commit anterior, da folha à raiz. Um diretório cabe em um bloco e um arquivo tem um nível de índice, o que limita um diretório a 4080 bytes de entradas e um arquivo a 2.084.864 bytes.

A imagem do runtime de usuário continua sendo carregada pelo QEMU na faixa que o DTB descreve em `/chosen`. A imagem de boot é outra coisa: um disco somente leitura, montado pelo serviço de arquivos depois que os drivers iniciam.

## Hipóteses a confirmar

- Um nível de índice e um bloco por diretório bastam para a versão 1.0. O índice já tem um campo de nível, hoje sempre zero.
- O custo de reescrever a árvore até a raiz a cada `fsync` cabe nos deadlines dos clientes. Ainda não foi medido com árvores fundas.
- O contrato vale em um disco físico. Ele foi exercitado no `virtio-blk` do QEMU, com erro de flush injetado pelo `blkdebug` e com o log de escritas do `blklogwrites`.

## Hipóteses resolvidas

- O `virtio-blk` do QEMU fixado aceita flush e permite injetar a falha. O cenário `flush-failure` e o estágio `flush-trace-replay` dependem disso.
- Bloco de 4096 bytes e CRC-32.
- Blocos órfãos não precisam de recuperação: sem mapa gravado, eles já são livres na montagem seguinte.
