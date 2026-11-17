# Qualificar e montar um release

Um release sai de um build cujas evidências foram todas produzidas para as mesmas imagens. Cada comando abaixo grava um relatório com o SHA-256 de `kernel.elf`, `init.img` e `boot.img`. `release-check` só aceita relatórios dessas imagens: depois de qualquer mudança que altere uma delas, a evidência anterior deixa de valer. Os hashes não mudam com o lugar da árvore, do diretório de build ou do cache da toolchain.

## Sequência

```sh
uv run kernel-tool build --profile qemu-riscv64
uv run kernel-tool verify --all --profile qemu-riscv64
uv run kernel-tool repeat-boot --profile qemu-riscv64 --count 1000
uv run kernel-tool benchmark --profile qemu-riscv64
uv run kernel-tool reproduce-build --profile qemu-riscv64
uv run kernel-tool fuzz --all --budget-hours 24
uv run kernel-tool soak --profile qemu-riscv64 --hours 24
uv run kernel-tool release-check --profile qemu-riscv64
```

| Comando | O que faz | Relatório |
| --- | --- | --- |
| `verify --all` | Roda a matriz inteira: formatação, lint, tipos, testes do host, interfaces congeladas, testes nativos, corpus de fuzzing, build, inspeção das imagens, todas as suítes no QEMU, as suítes de falha e o corpus de volumes. Uma verificação que não pôde rodar fica `incomplete`, e o comando termina com status 3 | `build/qemu-riscv64/qualification/verification.json` |
| `repeat-boot` | Inicia a imagem de release até o shell e desliga em ordem, o número de vezes pedido. Guarda duração, hash da transcrição e, em caso de falha, a transcrição de cada boot | `qualification/boots.json` |
| `benchmark` | Mede boot, memória, IPC, resposta de tarefa pronta, pausas do coletor do supervisor e liberação após término, e compara com os budgets | `qualification/measurements.json` |
| `reproduce-build` | Compila duas vezes em diretórios vazios e exige imagens iguais entre si e iguais às do build atual | `qualification/reproduction.json` |
| `fuzz` | Muta entradas de cada família pelo tempo pedido. O tempo é de cada família, não dividido entre elas | `build/fuzz/ledger.json` e `build/fuzz/report.json` |
| `soak` | Mantém um único boot sob carga mista pelo tempo pedido | `qualification/soak.json` |
| `release-check` | Avalia os gates, monta o pacote e termina com status diferente de zero enquanto algum gate estiver em aberto | `release/kernel-<versão>-qemu-riscv64/release-report.json` |

`verify --area <área>` roda uma parte da matriz. Uma execução parcial não satisfaz o gate de correção.

Rode um comando de cada vez sobre um diretório de build. Os que iniciam o QEMU usam os mesmos volumes de cenário, e dois ao mesmo tempo disputam esses arquivos: um deles termina com status 3, e o relatório dele fica incompleto.

## Fuzzing

As famílias são `boot`, `interface`, `storage` e `network`. Os alvos nativos são compilados para o host com AddressSanitizer, UndefinedBehaviorSanitizer e cobertura por bloco; os alvos Python rodam o código do convidado em CPython com cobertura por linha. Um alvo falha por crash, por travar ou por quebrar um invariante que o próprio alvo confere.

O tempo acumula entre sessões em `build/fuzz/ledger.json`, por alvo e pela versão do código que o alvo exercita. Quando esse código muda, o tempo do alvo volta a zero.

- `uv run kernel-tool replay-corpus --all` roda as seeds, o corpus de `tests/fuzz/corpus/` e as regressões de `tests/fuzz/regressions/`, sem mutar.
- `uv run kernel-tool promote-corpus --all` copia para `tests/fuzz/corpus/` as entradas da última campanha que alcançam código novo.
- Uma falha fica em `build/fuzz/findings/<família>/<alvo>/`, com a entrada reduzida em hexadecimal e o diagnóstico. Depois da correção, a entrada vai para `tests/fuzz/regressions/<família>/<alvo>.hex`, uma por linha.

## Soak

Um boot só, com volume novo, e rodadas até o tempo acabar. Cada rodada grava um arquivo, conta as palavras dele em uma aplicação, baixa um arquivo do peer por TCP, faz `ping`, esgota o heap de uma aplicação, mata uma aplicação presa em um laço e outra presa em arquivos, sincroniza o volume e lê os contadores do sistema.

O soak falha quando um comando não termina como esperado, quando aparece `trap:`, `panic:`, vazamento ou deadlock, quando o desligamento não é limpo, quando o volume não monta depois, ou quando frames livres, objetos, capabilities, endpoints, buffers ou a duração da rodada pioram de forma persistente depois das 8 primeiras rodadas. A piora é persistente quando a mediana e o extremo da segunda metade das amostras são piores que os da primeira.

`--without-network` deixa a rede de fora. Uma execução assim serve para desenvolvimento e não satisfaz o gate.

## Gates

| Gate | Exigência | De onde vem |
| --- | --- | --- |
| `correctness` | Matriz inteira, sem falha e sem verificação incompleta | `verify --all` |
| `boot` | 1.000 boots sem falha | `repeat-boot` |
| `lifecycle` | 10.000 ciclos de processo e IPC sem crescimento | Suíte `processes` em `verify --all` |
| `stability` | 24 horas em um boot, com rede, sem falha e sem piora persistente | `soak --hours 24` |
| `fuzzing` | 24 horas acumuladas em cada família e nenhuma falha em aberto | `fuzz` |
| `isolation` | Suítes `memory`, `capabilities`, `ipc`, `devices` e as falhas de `device-reset` | `verify --all` |
| `durability` | Suíte `storage`, as falhas de `storage-crash` e o corpus de volumes | `verify --all` |
| `network` | Suítes `network`, `network-interop` e as falhas de `network-faults` | `verify --all` |
| `dependencies` | Revisão de avisos de segurança para a versão fixada de cada componente e licenças aceitas | `config/release/advisories.toml` e o inventário de licenças |
| `distribution` | Builds limpos idênticos e as suítes `release-journey` e `system-journey` | `reproduce-build` e `verify --all` |
| `interfaces` | Interfaces congeladas iguais aos digests gravados | `specs/frozen-interfaces.toml` |
| `budgets` | Todos os budgets medidos e cumpridos | `benchmark` |

`release-check` não publica, não cria tag e não usa chave. Publicar, marcar a versão e assinar com a chave de release dependem de autorização de quem responde pelo projeto.

## Assinar

A chave de release fica fora do repositório. `release-sign` recusa uma chave que esteja dentro dele.

```sh
ssh-keygen -t ed25519 -f <fora do repositório>/kernel-release -C <identidade>
uv run kernel-tool release-sign <pacote> --key <fora do repositório>/kernel-release
```

O comando confere os checksums e grava `SHA256SUMS.sig`, uma assinatura OpenSSH de `SHA256SUMS` no namespace `kernel-release`. Só um pacote com `"qualified": true` é assinado. `--rehearsal` permite assinar um pacote não qualificado para ensaiar o procedimento; o manifesto continua dizendo que ele não é um release.

Quem confere usa um arquivo de signatários com uma linha por chave pública:

```
<identidade> namespaces="kernel-release" ssh-ed25519 AAAA...
```

```sh
uv run kernel-tool release-verify <pacote> --allowed-signers <arquivo> --identity <identidade>
```

O que fica registrado para auditoria: `release-report.json`, com cada gate e a versão; `manifest.json`, com os hashes das imagens; e `SHA256SUMS`, que cobre os dois e é o que a assinatura protege.

A assinatura diz que o pacote é o que o dono da chave montou. Ela não é secure boot e não protege um host comprometido.

## Dependências

`config/release/advisories.toml` registra, para cada componente de `toolchain.lock.toml`, a versão revisada, as fontes consultadas e cada aviso encontrado, com a severidade e o motivo de se aplicar ou não. O gate reprova quando a versão fixada muda sem revisão nova e quando um aviso alto ou crítico se aplica e não tem tratamento. A revisão é refeita antes de cada release e sempre que uma versão fixada muda.
