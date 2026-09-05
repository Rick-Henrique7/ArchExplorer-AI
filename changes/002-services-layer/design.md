# Change 002 — Design: Services layer

> Decisões de **como** os 3 serviços são estruturados. Mapeia `spec.md`
> para código concreto.

---

## 1. Adaptações ao que o Change 001 deixou pronto

`MainWindow.__init__(services: dict | None = None)` já aceita DI. O hook
fica intocado. Em Change 003 (UI integration) vamos popular
`services={...}` com instâncias reais.

## 2. Estrutura de arquivos (após merge)

```
app/services/
├── __init__.py             # exports públicos
├── exceptions.py           # 3 exceções custom
├── file_manager.py         # FileItem, ClipboardState, FileManager
├── ai_engine.py            # IAIProvider Protocol, OllamaProvider, MockAIProvider, AIEngine, prompts
└── diagram_generator.py    # BaseDiagramRenderer Protocol, MermaidRenderer
```

```
tests/
├── unit/
│   ├── test_file_manager.py
│   ├── test_ai_engine.py
│   └── test_diagram_generator.py
└── integration/
    └── test_ai_ollama_live.py   # gated por OLLAMA_TEST=1
```

## 3. Decisões de design

### 3.1. `Protocol` em vez de `ABC` para `IAIProvider` e `BaseDiagramRenderer`

- `typing.Protocol` dá **structural subtyping** (duck typing
  formalizado): `MockAIProvider` não precisa herdar de `IAIProvider` —
  só precisa ter a mesma assinatura
- Testes não precisam importar/importar-uma-classe-pai
- LSP fica explícito no type checker (`mypy --strict` confirma
  intercambiabilidade)
- Custo: perdemos `@abstractmethod` decorator (mas ganhamos `mypy`)

### 3.2. `OllamaProvider` aceita `requests.Session` injetável

```python
class OllamaProvider:
    def __init__(self, *, ..., session: requests.Session | None = None) -> None:
        self._session = session or requests.Session()
```

- Default cria `requests.Session()` (connection pooling)
- Testes com `requests_mock.Mocker(session=provider._session)`
  interceptam HTTP de verdade
- Injetável para retry/timeout customizados em produção

### 3.3. `MockAIProvider` com fixtures e fallback determinístico

```python
class MockAIProvider:
    def __init__(self, fixtures: dict[str, str] | None = None) -> None:
        self._fixtures = fixtures or {}
        # Default fixtures para os 3 pipelines do AIEngine

    def generate(self, prompt, *, system=None, temperature=None) -> str:
        for substring, response in self._fixtures.items():
            if substring in prompt:
                return response
        # Fallback determinístico para testes de regressão
        return f"[MOCK:{hash(prompt) & 0xFFFF:04x}]"
```

Vantagens:
- Testes determinísticos sem re-escrever o mock a cada vez
- Inserção de fixtures específicas por substring do prompt
- Nunca retorna `None` ou string vazia (reduz branches defensivos)

### 3.4. Prompts como constantes de classe, não arquivos externos

- Em `AIEngine`, prompts são `Final[str]` no nível de classe
- Vantagem: fácil de versionar junto com o código
- Desvantagem: prompts longos poluem o arquivo
- Decisão: prompts vão ter **máximo ~20 linhas cada**; se crescer,
  refatorar para `app/services/prompts.py` em change futuro

### 3.5. `MermaidRenderer` faz fallback em 3 níveis

```python
def sanitize(self, raw_response: str) -> str:
    # 1. Bloco ```mermaid ... ```
    m = self.MERMAID_BLOCK_RE.search(raw_response)
    if m:
        return m.group(1).strip()
    # 2. Bloco ``` ... ``` genérico, com keywords
    for m in self.GENERIC_BLOCK_RE.finditer(raw_response):
        lang = (m.group(1) or "").lower()
        content = m.group(2).strip()
        if "mermaid" in lang or any(content.startswith(k) for k in self.VALID_KEYWORDS):
            return content
    # 3. Assume que o texto cru já é Mermaid
    text = raw_response.strip()
    if not text:
        raise DiagramParsingError("Empty response from LLM", raw=raw_response)
    return text
```

- Falha **só** se vazio (modelo "fail-loud" — não tenta adivinhar)
- Caller decide se texto cru sem keywords é inválido (`validate()`)

### 3.6. Mermaid.js versionado, CDN fixo

```python
MERMAID_VERSION = "10.9.1"   # última estável do Mermaid.js v10
MERMAID_CDN = f"https://cdn.jsdelivr.net/npm/mermaid@{MERMAID_VERSION}/dist/mermaid.min.js"
```

- Versão fixada evita surpresas de breaking changes
- Permite bump explícito via change dedicado
- CDN é o oficial (jsDelivr) — fallback para S3/self-host fica em
  change futuro de empacotamento

### 3.7. `FileManager` sem threads, sem signals

- Toda operação é **síncrona** e retorna o resultado ou levanta exceção
- Threading fica no UI layer (Change 003) com `QThread` / `QRunnable`
- Isso mantém o serviço simples e fácil de testar

### 3.8. `ClipboardState` como dataclass imutável

```python
@dataclass(frozen=True)
class ClipboardState:
    source_path: str
    mode: Literal["copy", "cut"]
```

- `@dataclass(frozen=True)` garante imutabilidade
- `Literal` dá type-safety em `mode`
- `FileManager` mantém **um** `Optional[ClipboardState]` em memória

### 3.9. Test isolation

- `test_file_manager.py`: `tmp_path` do pytest (diretório temporário
  real, auto-cleanup)
- `test_ai_engine.py`: `requests_mock` para HTTP; `MockAIProvider` com
  fixtures inline (sem fixture compartilhada, para deixar cada teste
  legível)
- `test_diagram_generator.py`: strings inline, sem I/O
- `test_ai_ollama_live.py`: `@pytest.mark.skipif(not os.getenv("OLLAMA_TEST"))`
  + `pytestmark = pytest.mark.integration` para filtragem fácil

### 3.10. `from __future__ import annotations` em todos os novos arquivos

- Permite type hints com classes ainda não definidas (útil para
  forward references)
- Compatível com dataclasses, Protocol, etc.
- Padrão já adotado nos arquivos do 001

## 4. Fluxo end-to-end (alto nível)

```
[Change 003 vai plugar este fluxo na UI; aqui só documentamos]

Usuário seleciona arquivo
    │
    ▼
FileExplorerPanel.file_selected(path)
    │
    ▼
MainWindow._on_file_selected(path)
    │
    ├─► FileManager.read_file(path)            # futuro
    │
    └─► AIEngine.extract_uml_structure(code)   # bloqueia a thread
            │
            ▼
        OllamaProvider.generate(prompt)        # HTTP POST
            │
            ▼
        "```mermaid\nclassDiagram\n  ...\n```"
            │
            ▼
        MermaidRenderer.sanitize(raw)
            │
            ▼
        "classDiagram\n  ..."
            │
            ▼
        MermaidRenderer.render_to_html(diagram)
            │
            ▼
        HTML string → VisualizerPanel          # QWebEngineView no 004
```

No Change 002, **somente** os 3 services são implementados e testados.
A fiação acima é documentada mas não executada até o Change 003.

## 5. Compatibilidade com Change 001

- `app/services/__init__.py` deixa de ser placeholder e exporta os
  novos símbolos
- `app/main.py` continua igual — `MainWindow(services=None)` ainda
  funciona (services é opt-in)
- `tests/conftest.py` ganha uma fixture opcional `live_ollama` que
  skipa se `OLLAMA_TEST` não está setado (reaproveitada pelo
  integration test)
- `pyproject.toml` adiciona `requests-mock` em
  `[project.optional-dependencies.dev]`
- `requirements-dev.txt` espelha a mudança

## 6. Trade-offs assumidos

| Decisão | Custo | Benefício |
|---|---|---|
| `Protocol` em vez de `ABC` | Sem `isinstance(x, IAIProvider)` confiável em runtime | LSP sem herança, mock trivial, mypy valida |
| `requests.Session` injetável | API mais verbosa (`session=`) | Testes determinísticos, retry/timeout custom |
| `MockAIProvider` com fallback determinístico | Hash do prompt muda entre versões Python | Testes não dependem de fixtures para todos os casos |
| Prompts inline em `AIEngine` | Poluição visual do arquivo | Versionamento coeso, fácil de iterar |
| Mermaid.js via CDN | Requer internet no 1º uso; offline-only quebra o render | Zero download no skeleton, versionamento claro |
| Sem streaming Ollama | Latência percebida maior (cold start visível) | Implementação 1/3 menor, debug mais fácil |
| `ClipboardState` sem encriptação | Paths em memória | Custo zero; UI é local-only, sem adversary |
| Integration test gated por env var | Não roda em CI por default | CI não fica flaky por causa do Ollama local |

## 7. O que **NÃO** está neste design

- `BaseDiagramRenderer` registry/factory (auto-detect de renderer pelo
  conteúdo) — overkill para 1 implementação
- Retry automático no `OllamaProvider` (com backoff) — fica para change
  de "robustez"
- Cache de respostas LLM — fora de escopo
- Persistência de clipboard entre sessões — UX nice-to-have
- Logging estruturado (Python `logging` module) — não usado em nenhum
  arquivo; em change dedicado
- Métricas de uso (tokens, latência) — para change de observability
