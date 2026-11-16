# ADR 0006: Persistência

Estado: aceita. Nenhum código de armazenamento existe ainda.

## Contexto

O sistema precisa guardar arquivos e sobreviver a queda de energia sem uma stack POSIX nativa. Decidir o contrato de durabilidade depois do formato leva a `fsync` que promete o que o disco não entrega.

## Decisão

Há três backends atrás do serviço VFS:

- Imagem de boot, somente leitura.
- Filesystem temporário, sem promessa de persistência.
- Volume persistente em formato próprio e versionado, implementado em Python, com dados e metadados copy-on-write.

O volume persistente segue este contrato:

1. Blocos têm tipo, geração, comprimento validado e checksum. Árvores têm profundidade e fan-out limitados.
2. Dois superblocks alternados apontam para o root comprometido, cada um com sua geração.
3. Uma transação escreve dados e metadados novos sem sobrescrever o que os roots protegidos ainda alcançam.
4. O novo root só é publicado depois de o transporte confirmar ordenação e flush dos blocos.
5. `fsync` só retorna sucesso depois do flush que segue a publicação do root.
6. A recuperação escolhe o root consistente de maior geração e valida o que ele alcança.

`write` aceito não significa durabilidade, e `close` não substitui `fsync`. Disco cheio, checksum incorreto ou formato desconhecido produzem erro ou montagem somente leitura. O sistema nunca formata um volume para conseguir inicializar.

Symlinks e hard links ficam fora da versão 1.0.

## Consequências

O filesystem é trabalho grande e a prova de consistência após falha bloqueia a entrega dele. Checksum detecta corrupção, mas não autentica o disco contra adulteração deliberada.

Até a imagem de boot existir, o único arquivo de boot é a imagem do runtime de usuário. O QEMU a carrega na faixa que o DTB descreve em `/chosen`, e o supervisor valida cabeçalho e limites antes de copiar. Esse caminho é somente leitura.

## Hipóteses a confirmar

- O `virtio-blk` do QEMU fixado honra flush de modo que o contrato de `fsync` seja testável com injeção de falha.
- Tamanho de bloco e algoritmo de checksum. Nenhum está escolhido.
- A recuperação de blocos órfãos de transações interrompidas termina em tempo limitado.
