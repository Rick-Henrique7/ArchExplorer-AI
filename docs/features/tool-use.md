# Tool Use — Como a IA cria arquivos (Change 007)

> **Público-alvo:** usuários do ArchExplorer AI que querem entender
> como a IA consegue manipular o sistema de arquivos com segurança.

---

## O que é Tool Use?

É o mecanismo que permite que o modelo de IA (Qwen, GPT-4, Claude,
Gemini, ...) emita **chamadas estruturadas** a funções pré-definidas
em vez de gerar texto livre. Cada tool tem um JSON Schema
explícito; a IA devolve o nome da função + os argumentos; nós
executamos a função e devolvemos o resultado.

Em vez de pedir:

> "Por favor, crie o arquivo `src/main.py` com o conteúdo tal..."

(prompt livre, imprevisível)

nós dizemos:

```json
{
  "name": "create_file",
  "arguments": {
    "file_path": "src/main.py",
    "content": "print('hi')"
  }
}
```

(chamada estruturada, validável, executável)

---

## As 4 tools disponíveis

| Tool | O que faz | Read/Write |
|---|---|---|
| `create_file` | Cria (ou sobrescreve) um arquivo com conteúdo | Write |
| `create_directory` | Cria uma pasta (recursivo) | Write |
| `read_file` | Lê um arquivo existente (retorna string) | Read |
| `list_directory` | Lista entradas (`/` no fim para pastas) | Read |

Todas operam em um **workspace_root** definido pelo app. Nenhuma
consegue escapar dele.

---

## Sandbox — por que é seguro

Cada tool passa por três checagens antes de tocar o disco:

1. **Whitelist de caracteres** — `^[a-zA-Z0-9._/-]+$`. Nada de `..`,
   `\`, espaços, null bytes ou metacaracteres shell.
2. **Resolução + path traversal** — `(workspace_root / rel_path).resolve()`
   deve `startswith(workspace_root.resolve())`. `../etc/passwd` é
   barrado.
3. **Tamanho máximo** — 1 MiB por arquivo. Impede que a IA gere um
   payload de GB que preencha o disco.

Quando uma checagem falha, a tool retorna `ERROR (reason): ...`
para a IA, que pode se autocorrigir na próxima iteração do loop.

Veja `app/services/filesystem_agent.py` para a implementação.

---

## O loop de Tool Use

```
┌─────────────────────────────────────────────────────────────┐
│                    run_agent_loop()                        │
│                                                             │
│  1. Envia prompt + tools para o LLM                         │
│  2. Recebe resposta: content + tool_calls?                  │
│  3. Se só content → fim (retorna para o usuário)            │
│  4. Se tool_calls → executa cada uma via FileSystemAgent     │
│  5. Adiciona resultados ao histórico de mensagens           │
│  6. Volta ao passo 1 (max 10 iterações)                     │
└─────────────────────────────────────────────────────────────┘
```

Implementado em `app/services/llm_adapter.py::run_agent_loop`.

---

## Multi-provider — uma interface, vários backends

O `LiteLlmAdapter` usa [LiteLLM](https://github.com/BerriAI/litellm)
para falar com qualquer provider sem mudar uma linha de código:

```python
config = {
    "active_provider": "ollama_local",
    "providers": {
        "ollama_local": {"model": "qwen2.5-coder:3b",
                         "base_url": "http://localhost:11434"},
        "openai":       {"model": "gpt-4o",
                         "api_key_env": "OPENAI_API_KEY"},
        "anthropic":    {"model": "claude-3-5-sonnet-20241022",
                         "api_key_env": "ANTHROPIC_API_KEY"},
        "gemini":       {"model": "gemini-1.5-pro",
                         "api_key_env": "GOOGLE_API_KEY"},
        "cohere":       {"model": "command-r-plus",
                         "api_key_env": "COHERE_API_KEY"},
    }
}
```

Trocar de provider = trocar `active_provider`. As chaves de API são
lidas de **variáveis de ambiente** — nada fica gravado em disco.

A configuração persiste em `config/llm_config.json` (ao lado do
`pyproject.toml`) ou `~/Documents/ArchExplorer/llm_config.json`.

---

## Exemplo end-to-end

**Prompt do usuário:**

> "Cria a pasta `src/` e adiciona um `main.py` que imprime 'Hello,
> World!'."

**Resposta do LLM (round 1):**

```json
{
  "tool_calls": [{
    "function": {
      "name": "create_directory",
      "arguments": "{\"dir_path\": \"src\"}"
    }
  }]
}
```

**Execução:**
```
Created directory src
```

**Resposta do LLM (round 2):**

```json
{
  "tool_calls": [{
    "function": {
      "name": "create_file",
      "arguments": "{\"file_path\": \"src/main.py\", \"content\": \"print('Hello, World!')\"}"
    }
  }]
}
```

**Execução:**
```
Created src/main.py (24 bytes)
```

**Resposta do LLM (round 3):**

```json
{
  "content": "Pronto! Criei `src/main.py` com o print pedido."
}
```

**Loop termina** — só `content`, sem mais `tool_calls`.

---

## Instalação do extra `[llm]`

Por padrão o ArchExplorer só traz `pysat`, `Jinja2`, `pydantic`. O
`litellm` (~80 MB de deps) é opcional:

```bash
pip install arch-explorer-ai[llm]
```

Sem o extra, o `LiteLlmAdapter` continua funcionando — só que a
primeira chamada levanta `LlmToolError("litellm_missing")` com a
mensagem instalando o extra.

---

## Onde encontrar no código

| Arquivo | Conteúdo |
|---|---|
| `app/services/llm_adapter.py` | `LlmAdapter` Protocol + `LiteLlmAdapter` + `run_agent_loop` |
| `app/services/filesystem_agent.py` | Sandbox + 4 tools |
| `app/services/exceptions.py` | `LlmToolError` (com `reason` no `message`) |
| `app/ui/llm_chat_widget.py` | Widget de chat com Tool Use |
| `app/ui/llm_settings_dialog.py` | Dialog de configuração |

---

## Roadmap

- Change 007/Bloco F: ✅ LiteLLM adapter + sandbox + loop.
- Change 007/Bloco G: ✅ Settings dialog + chat widget.
- Change 008 (futuro): streaming das respostas token a token
  (hoje só recebe o conteúdo final).
- Change 008 (futuro): vincular o chat a um diretório específico
  (hoje o workspace_root é fixo na criação do FileSystemAgent).
