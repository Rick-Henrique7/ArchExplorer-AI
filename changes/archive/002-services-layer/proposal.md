# Change 002 — Services layer (FileManager + AIEngine + DiagramGenerator)

> **Status:** Aguardando aprovação
> **Tipo:** Feature (camada de serviços, sem UI)
> **Risco:** Médio (primeira integração com LLM + I/O real)
> **Pré-requisito externo:** Ollama rodando com `qwen2.5-coder:3b` ✅ (validado)

---

## 1. Contexto

O Change 001 entregou a casca PySide6 com 3 painéis placeholder. Para o app
ter utilidade, precisamos implementar os 3 serviços definidos em
`docs/backend/backend.md`:

- `FileManager` — abstração de I/O do sistema de arquivos
- `AIEngine` — orquestrador dos pipelines de IA, com `IAIProvider` trocável
- `DiagramGenerator` — sanitização e renderização de Mermaid.js

O ambiente está validado: **Ollama 0.33.3** em `localhost:11434` com
**`qwen2.5-coder:3b`** (1.9 GB, Q4_K_M, 32k context) — `OK` em 7.7s no
smoke test de cold start.

A diretriz `docs/guidelines/diretriz.md` exige SOLID estrito: a troca do
backend de IA (`OllamaProvider` → `LlamaCppProvider` futuro) e do
renderizador (`MermaidRenderer` → `PlantUMLRenderer` futuro) **não pode**
mexer em código existente (OCP). Daí a escolha de `Protocol` e de
classes-base finas.

## 2. Mudança

### 2.1. Camada de serviços

| Arquivo | Conteúdo |
|---|---|
| `app/services/__init__.py` | Exports públicos dos 3 serviços + exceções |
| `app/services/exceptions.py` | `FileOperationError`, `AIServiceUnavailableError`, `DiagramParsingError` |
| `app/services/file_manager.py` | `FileManager` + dataclass `FileItem` + clipboard interno (COPY/CUT) |
| `app/services/ai_engine.py` | Protocol `IAIProvider` + `OllamaProvider` + `MockAIProvider` + `AIEngine` (3 pipelines) |
| `app/services/diagram_generator.py` | Protocol `BaseDiagramRenderer` + `MermaidRenderer` (sanitização + HTML) |

### 2.2. Camada de testes

| Arquivo | Cobertura |
|---|---|
| `tests/unit/test_file_manager.py` | Criar/copiar/mover/deletar + clipboard, com `tmp_path` |
| `tests/unit/test_ai_engine.py` | `MockAIProvider` (contrato `IAIProvider`), `OllamaProvider` (HTTP mockado com `requests_mock`), 3 pipelines |
| `tests/unit/test_diagram_generator.py` | Sanitização de resposta LLM, validação de sintaxe, geração de HTML |
| `tests/integration/test_ai_ollama_live.py` | **Gated** por env var `OLLAMA_TEST=1` — bate no Ollama real, pula se não estiver |

### 2.3. Dependências

- Adiciona `requests-mock>=1.12` aos dev deps (mock HTTP determinístico)

### 2.4. NÃO mexe

- `app/main.py` — entry point intocado
- `app/ui/` — 3 painéis continuam placeholder
- `app/utils/` — continua vazio
- `MainWindow.__init__(services=...)` — o hook de DI do 001 já está preparado
- `pyproject.toml` classifiers / metadata

## 3. Fora do escopo

- UI integration (sinais `file_selected`, threading, `QThread`) → **Change 003**
- Renderização Mermaid em `QWebEngineView` → **Change 004**
- Streaming de tokens do Ollama (não-streaming é suficiente)
- Persistência de preferências (`QSettings`)
- Empacotamento (PyInstaller/Nuitka)
- Outros provedores de IA além de `OllamaProvider` e `MockAIProvider`
- Syntax highlighter real (apenas helper de detecção de tipo de arquivo)

## 4. Critérios de aceitação

- [ ] `py -m pytest` roda e exibe **todos os testes verdes** (sem o integration gated)
- [ ] `py -m pytest` com `OLLAMA_TEST=1` **inclui** o integration test e ele passa contra o Ollama real
- [ ] `FileManager` é 100% coberto por testes unitários
- [ ] `IAIProvider` tem **pelo menos 2 implementações** (`OllamaProvider` + `MockAIProvider`), ambas testadas isoladamente
- [ ] `AIEngine` chama o provider via `IAIProvider` (LSP — funciona com mock ou real sem mudar)
- [ ] `MermaidRenderer` extrai bloco ```mermaid ... ``` de respostas com lixo ao redor
- [ ] `MainWindow(services={...})` aceita os 3 services injetados (já existia no 001; validado por teste novo)
- [ ] Nenhuma referência a `PyQt6` no código (continua PySide6)
- [ ] `py -m app.main` continua abrindo a janela 3-painéis sem mudanças (UI intocada)
- [ ] Type hints em todas as funções públicas; `mypy --strict` em zero erros nos arquivos novos

## 5. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Timeout HTTP do Ollama muito curto para o 3B em prompts grandes | Timeout configurável no construtor do `OllamaProvider` (default 120s); testado em smoke real |
| LLM retorna Mermaid malformado (sem fence ```mermaid) | `MermaidRenderer.sanitize` faz fallback: tenta extrair bloco com fence, depois bloco genérico, depois retorna o texto cru. `DiagramParsingError` só se vazio. |
| Race condition no clipboard do `FileManager` | `FileManager` é stateless entre instâncias; cada instância tem seu próprio clipboard. Não compartilhado. |
| `requests-mock` não intercepta o `OllamaProvider` por causa de instanciação de `requests.Session` | `OllamaProvider` aceita `session: requests.Session | None` no construtor; default `requests.Session()`. Teste injeta mock. |
| Integração Ollama real quebra em CI (sem GPU/RAM) | Integration test é **gated** por `OLLAMA_TEST=1` env var. CI não seta essa var, então pula. Roda só local ou em job dedicado. |
| Type hints com `from __future__ import annotations` quebram em runtime (dataclass) | Import só onde necessário (dataclasses, Protocol); anotações de função ficam como string em `from __future__ import annotations` |

## 6. Definition of Done

- [ ] 4 artefatos deste change revisados e aprovados pelo Henrique
- [ ] `py -m pytest` verde local
- [ ] `py -m pytest -k integration` com `OLLAMA_TEST=1` verde
- [ ] Pelo menos 1 execução ponta-a-ponta do `AIEngine` com `OllamaProvider` real gravada em log de smoke
- [ ] `git log` no `main` mostra novo commit com tag `feat:` ou similar
- [ ] Henrique confirma que a janela do 001 ainda abre igual (UI intocada)
- [ ] Este change é arquivado em `changes/archive/002-services-layer/` após o commit

## 7. Rollback

`git revert <commit-hash>` reverte os 3 services novos + testes + dep
adicionada. UI do 001 permanece funcional (a DI hook é tolerante a
`services=None`).
