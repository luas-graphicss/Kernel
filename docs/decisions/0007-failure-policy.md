# ADR 0007: Política de falhas

Estado: aceita.

## Contexto

Um kernel que continua rodando sobre estado possivelmente corrompido é pior do que um que para. E um boot que falha em silêncio não deixa evidência para quem investiga.

## Decisão

Cada classe de falha tem um comportamento definido:

| Falha | Comportamento |
| --- | --- |
| Entrada de boot inválida: DTB, memória ou imagem de usuário | Diagnóstico nativo de uma linha, `kernel: status=failed` e desligamento |
| Trap inesperada em S-mode | Relatório de trap em stack de emergência, depois panic |
| Violação de invariante no supervisor | Panic com diagnóstico mínimo e parada |
| Exceção não tratada no Python supervisor | Traceback na serial e boot encerrado com falha |
| Entrada inválida em syscall | Erro para o chamador, sem acesso fora dos limites |
| Falha de processo em U-mode | Relatório de trap, encerramento do processo e devolução do status |
| Exceção não tratada em aplicação | Encerrar o processo, devolver status e liberar recursos |
| OOM em processo | Rejeitar a alocação ou encerrar o processo, sem consumir a reserva do supervisor |
| Morte de serviço | Invalidar endpoints antigos, concluir esperas e reiniciar só conforme o manifesto |
| Dispositivo sem resposta | Deadline, tentativa limitada de reset e estado degradado |
| Flood de logs ou eventos | Limitação e descarte contabilizado, preservando a reserva crítica |

O caminho de panic não usa heap Python, não depende de serviço em U-mode e escreve pela UART de emergência. Uma segunda trap durante o diagnóstico desliga sem imprimir de novo.

Hard IRQ salva contexto, reconhece a fonte, registra dados em buffer prealocado e retorna. Não executa Python, não coleta, não formata log e não aloca.

Toda espera tem deadline monotônico. Recuperar não é tentar de novo sem limite.

Todo boot termina com uma linha `kernel: status=ok` ou `kernel: status=failed`, seguida de `sbi_system_reset`. O `kernel-tool` usa três códigos de saída para separar os casos: `0` para sucesso, `1` para falha do que foi verificado e `3` para infraestrutura indisponível, como download que falhou ou ferramenta ausente.

## Consequências

Um teste só passa quando a linha de status, as asserções do cenário e o código de saída do emulador concordam. Boot que estoura o deadline é falha, não teste ignorado.

As oito primeiras linhas da tabela estão implementadas e têm cenário ou caso de suíte. Da morte de serviço existem o fechamento dos endpoints e a conclusão das esperas; o reinício pelo manifesto ainda não. Do flood existe a fila de eventos limitada, com descarte contabilizado. A linha de dispositivos depende dos drivers.

## Hipóteses a confirmar

- Quarentena de frames de DMA após falha de reset não esgota a memória em sequências longas de falha.
- A política de restart do manifesto, com quantidade e janela, evita restart loop sem mascarar defeito permanente.
