# ADR 0010: Homologação e distribuição

Estado: aceita.

## Contexto

O sistema tinha todas as funções previstas e uma verificação por mudança no CI. Faltava o que diz se um build pode ser distribuído: evidência longa, como fuzzing e soak, medições contra os budgets, interfaces com versão, um pacote verificável e um procedimento de instalação.

Parte dessa evidência leva dias de máquina. Era preciso decidir como ela se liga a um build, o que acontece quando falta, e quais ferramentas o projeto traz em vez de depender de serviços externos.

## Decisão

A evidência pertence a imagens, não a um commit. Cada comando de qualificação grava o SHA-256 de `kernel.elf`, `init.img` e `boot.img`, e `release-check` recusa um relatório de outras imagens. Como o build é reprodutível, a evidência produzida em uma máquina vale para as mesmas imagens compiladas em outra.

Um gate em aberto reprova. `release-check` monta o pacote de qualquer forma, para que a instalação possa ser ensaiada, mas grava `"qualified": false` no manifesto e termina com status diferente de zero. `release-sign` não assina um pacote assim sem `--rehearsal`. Não existe opção para dispensar um gate.

A versão é `1.0.0rc1` enquanto os gates de 24 horas não tiverem evidência. O número `1.0.0` é atribuído ao build que passar por `release-check`.

O fuzzing é feito por um motor do próprio `kernel-tool`: mutação determinística por seed, cobertura por linha para o código Python do convidado e por bloco para os parsers nativos, redução da entrada que falha e um registro de tempo por alvo. O GCC do host não traz libFuzzer, e o código de protocolo é Python, que um fuzzer de C não instrumenta. O registro de tempo é zerado quando o código de um alvo muda, para que horas gastas em uma versão anterior não contem.

O soak é um boot só, operado pelo console como um operador faria. Reiniciar o sistema a cada poucos minutos esconderia o crescimento de recursos, que é o que um soak procura.

As pausas do coletor do supervisor são medidas no código nativo, por um histograma de tamanho fixo alimentado pelo timer, e lidas pela política. A medição não aloca e não muda o caminho da coleta.

As interfaces congeladas são vigiadas por digest dos arquivos que as definem. O digest não prova compatibilidade; ele obriga quem muda um desses arquivos a decidir, pela política de compatibilidade, que tipo de mudança fez.

O pacote é assinado com assinaturas OpenSSH, pelo `ssh-keygen` do host, sobre o arquivo de checksums. A chave fica fora do repositório, e a ferramenta recusa uma chave dentro dele. Não há dependência de um serviço de assinatura nem de uma cadeia de certificados.

Instalar, atualizar e voltar são operações sobre um diretório com as imagens e o volume. A compatibilidade entre um release e um volume é decidida pelo formato que o release declara ler, conferido contra o superblock antes de trocar as imagens.

## Consequências

- Qualquer mudança em código que entra nas imagens invalida a evidência longa. A correção de uma falha achada no fim da qualificação custa a qualificação de novo.
- A qualificação completa não cabe em um runner hospedado do GitHub, que encerra um job em seis horas. O fuzzing pode acumular em várias sessões, na máquina de quem prepara o release; o soak de 24 horas pede uma máquina que fique ligada esse tempo.
- O motor de fuzzing é mais simples que um fuzzer dedicado: não tem dicionários por formato nem cobertura por aresta. Ausência de falhas com ele diz menos do que diria com uma ferramenta madura.
- O gate de dependências depende de uma revisão manual registrada em arquivo. Ele garante que a revisão acompanha a versão fixada, não que a revisão está certa.

## Hipóteses a confirmar

- Os budgets foram medidos no QEMU com TCG em uma máquina virtual de dois processadores. Os números não valem para hardware físico.
- O critério de piora persistente do soak foi exercitado com um convidado simulado que vaza um frame por rodada e com execuções curtas do sistema real. Ele ainda não foi observado em uma execução de 24 horas.
