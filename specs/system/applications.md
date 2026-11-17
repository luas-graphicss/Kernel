# Aplicações

[English](applications.en.md)

Uma aplicação é um programa Python lido de um arquivo e executado em um processo próprio, em U-mode, com o interpretador, o heap e as capabilities só dele. Quem inicia uma aplicação é o gerente, a pedido do shell, pela operação `LAUNCH` de `control-service.md`.

## Como uma aplicação inicia

1. O gerente confere o limite de aplicações em execução e a linha de comando.
2. Cria um processo com o programa `kernel_apps.runner.main`, com o heap e a prioridade de `[access.application]`.
3. Concede ao processo o que a política permite, e nada mais:

| Política | Capabilities concedidas |
| --- | --- |
| `files` diferente de `none` | O endpoint do serviço de arquivos e um namespace no modo configurado |
| `network` com algum direito | O endpoint do serviço de rede e um acesso com os direitos configurados |
| Sempre | Um endpoint de registro, para avisar o gerente de que iniciou |

4. O runner lê o arquivo nomeado pela primeira palavra do comando, pelo namespace que recebeu, e o executa.

A aplicação não recebe a capability do sistema, o endpoint de controle, nenhum dispositivo nem as capabilities do shell. Ela não herda memória: o processo começa com um interpretador novo, sem os módulos, as variáveis e os buffers de quem pediu o início.

## O programa

| Regra | Valor |
| --- | --- |
| Caminho | A primeira palavra do comando, resolvida no namespace da aplicação, por exemplo `boot/apps/sysinfo.py` |
| Tamanho | Até 65.536 bytes |
| Formato | Código-fonte Python. O interpretador do processo compila o arquivo ao carregar |
| Argumentos | As palavras do comando, separadas por espaço. O comando inteiro cabe em 63 bytes |
| Execução | O arquivo roda com `__name__` igual a `"__main__"`. Se ele define `main`, ela é chamada em seguida |
| Status | 0 quando o arquivo termina e `main`, se existe, não devolve `False`. 1 quando `main` devolve `False`, quando uma exceção escapa ou quando o arquivo não pôde ser lido |

Uma exceção que escapa imprime o traceback no console de diagnóstico. Um arquivo que não existe produz `application: program=<caminho> error=NOT_FOUND`.

O programa importa os módulos congelados na imagem: `kernel_apps.runtime`, `kernel_client`, `kernel_protocol` e os utilitários de `kernel_services.network.ipv4.address`. Importar um módulo a partir de um arquivo do volume não é suportado e falha com `ImportError`. As diferenças do runtime em relação ao CPython estão em `docs/architecture/runtime-differences.md`.

## API do programa

`kernel_apps.runtime.current()` devolve a aplicação em execução:

| Atributo | Conteúdo |
| --- | --- |
| `arguments` | Lista de textos. O primeiro é o caminho do programa |
| `files` | Um `kernel_client.files.Namespace`, ou `None` se a política não concede arquivos |
| `network` | Um `kernel_client.sockets.Network`, ou `None` se a política não concede rede |

```python
from kernel_apps import runtime


def main() -> bool:
    application = runtime.current()
    if len(application.arguments) != 2 or application.files is None:
        print("usage: count.py <path>")
        return False
    ...
    return True
```

Os arquivos seguem `specs/filesystem/file-service.md` e a rede segue `specs/network/socket-service.md`. `print` escreve no console de diagnóstico, pela chamada `debug_write`.

## Limites e término

| Limite | Valor |
| --- | --- |
| Aplicações em execução | `limit` de `[access.application]`, até 8. A imagem do repositório usa 4 |
| Heap | `heap_bytes` de `[access.application]`. A imagem do repositório usa 2 MiB |
| Sockets e arquivos | Os limites por processo de cada serviço |

Uma aplicação que esgota o heap recebe `MemoryError` e termina com status 1; os outros processos não são afetados. Uma aplicação que não devolve o processador é preemptada pelo timer e pode ser encerrada por `SIGNAL`.

Quando uma aplicação termina, por qualquer motivo, o gerente pede aos serviços de arquivos e de rede que encerrem as sessões dela: sockets, conexões e arquivos abertos são fechados. O supervisor libera a memória e as capabilities do processo.

## Evidência

A suíte `applications` inicia os programas de `tests/guest/apps` pelo shell:

| Programa | O que demonstra |
| --- | --- |
| `counter.py`, duas vezes | Argumentos entregues; a segunda execução não vê variáveis da primeira |
| `authority.py` | A aplicação percorre a própria tabela de capabilities e encontra cinco, todas endpoints só com `SEND`. Por nenhuma delas, nem por handles adivinhados, ela cria processo, lista ou reivindica dispositivo, pede desligamento ou é atendida em uma operação de controle. Os módulos do shell não estão carregados no processo, e arquivos e rede vieram conforme a política |
| `failing.py`, `broken.txt`, `missing.py` | Exceção, erro de sintaxe e arquivo ausente terminam com status 1 e diagnóstico |
| `spin.py` | Laço sem cooperação: `wait` com prazo devolve `TIMED_OUT`, `ps` mostra a aplicação em execução e `kill` a encerra |
| `hog.py` | Heap esgotado termina a aplicação com `MemoryError` |
| `idle.py`, cinco vezes | A quinta é recusada com `LIMIT_EXCEEDED`; a parada encerra as quatro em execução |
