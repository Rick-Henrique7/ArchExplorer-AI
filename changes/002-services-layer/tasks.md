# Change 002 — Tasks: Services layer

> Checklist executável. Marcar `[x]` conforme conclusão.

---

## Bloco A — Exceções

- [ ] A1. Criar `app/services/exceptions.py` com `FileOperationError`, `AIServiceUnavailableError`, `DiagramParsingError` (todas subclasses de `Exception` com `__init__(self, message, **context)`)

## Bloco B — FileManager

- [ ] B1. Criar `app/services/file_manager.py` com `@dataclass(frozen=True) FileItem` e `@dataclass(frozen=True) ClipboardState`
- [ ] B2. Implementar `FileManager.__init__` (estado interno: `_clipboard: ClipboardState | None = None`)
- [ ] B3. Implementar `list_directory`, `create_folder`, `create_file`, `copy_item`, `move_item`, `delete_item` (todos levantam `FileOperationError` em falha; usam `pathlib.Path` internamente)
- [ ] B4. Implementar `copy_to_clipboard`, `cut_to_clipboard`, `paste_from_clipboard`, `clipboard_state` (modo `Literal["copy", "cut"]`)
- [ ] B5. Validar `paste_from_clipboard`: `None` se clipboard vazio; executa e limpa se era CUT; executa e mantém se era COPY

## Bloco C — AIEngine

- [ ] C1. Em `app/services/ai_engine.py`, definir `class IAIProvider(Protocol)` com método `generate(prompt, *, system=None, temperature=None) -> str`
- [ ] C2. Implementar `OllamaProvider.__init__(base_url, model, timeout, session=None)` e `generate(...)` (POST `/api/generate`, body com `stream=false`, parsing JSON, levanta `AIServiceUnavailableError` em falha de rede/HTTP/JSON)
- [ ] C3. Implementar `MockAIProvider.__init__(fixtures=None)` e `generate(...)` (match por substring; fallback determinístico por hash do prompt)
- [ ] C4. Implementar `AIEngine.__init__(provider: IAIProvider)` e 3 pipelines: `generate_component(prompt, context_path)`, `analyze_architecture(code_content, file_type)`, `extract_uml_structure(code_content)`
- [ ] C5. Cada pipeline monta prompt via `Final[str]` template na classe e chama `provider.generate(...)`; retorna a string crua sem parsing
- [ ] C6. Atualizar `app/services/__init__.py` para exportar `FileManager`, `AIEngine`, `OllamaProvider`, `MockAIProvider`, `IAIProvider`, `MermaidRenderer`, `BaseDiagramRenderer`, e as 3 exceções

## Bloco D — DiagramGenerator

- [ ] D1. Em `app/services/diagram_generator.py`, definir `class BaseDiagramRenderer(Protocol)` com `sanitize`, `validate`, `render_to_html`
- [ ] D2. Implementar `MermaidRenderer` com `MERMAID_VERSION = "10.9.1"`, `MERMAID_CDN`, `VALID_KEYWORDS`, `MERMAID_BLOCK_RE`, `GENERIC_BLOCK_RE`
- [ ] D3. Implementar `sanitize` com fallback de 3 níveis (ver design §3.5); levanta `DiagramParsingError` só se vazio
- [ ] D4. Implementar `validate` (retorna `True` se começa com `VALID_KEYWORDS` ou tem operadores Mermaid comuns)
- [ ] D5. Implementar `render_to_html` (template HTML mínimo com `<script src="MERMAID_CDN">`, `mermaid.initialize({startOnLoad:true})`, e `<div class="mermaid">` com conteúdo sanitizado)

## Bloco E — Dependências

- [ ] E1. Adicionar `requests-mock>=1.12` em `pyproject.toml` → `[project.optional-dependencies.dev]`
- [ ] E2. Adicionar `requests-mock>=1.12` em `requirements-dev.txt`
- [ ] E3. `pip install -r requirements-dev.txt` (ou `py -m pip install -e ".[dev]"`) e validar que `import requests_mock` funciona

## Bloco F — Testes unitários

- [ ] F1. `tests/unit/test_file_manager.py`: cobre `list_directory` em dir vazio e populado; `create_folder`/`create_file` com sucesso e com colisão; `copy_item`/`move_item`; `delete_item` em arquivo e em pasta não-vazia; clipboard COPY/CUT com paste
- [ ] F2. `tests/unit/test_ai_engine.py`: 3 pipelines com `MockAIProvider`; `OllamaProvider.generate` com `requests_mock` retornando JSON válido; `OllamaProvider.generate` com 500/timeout/conexão recusada → `AIServiceUnavailableError`; `IAIProvider` LSP via mypy-style check
- [ ] F3. `tests/unit/test_diagram_generator.py`: sanitize com fence ```mermaid; sanitize sem fence mas com keyword; sanitize com lixo ao redor; sanitize vazio → `DiagramParsingError`; validate com/sem keywords; render_to_html contém `mermaid.min.js` e o conteúdo sanitizado
- [ ] F4. `py -m pytest tests/unit/ -v` — todos verdes
- [ ] F5. `py -m pytest --cov=app/services --cov-report=term-missing tests/unit/` — cobertura de FileManager, AIEngine, DiagramGenerator ≥ 90%

## Bloco G — Integration test gated

- [ ] G1. `tests/integration/test_ai_ollama_live.py` com `pytestmark = pytest.mark.integration` e `@pytest.mark.skipif(not os.getenv("OLLAMA_TEST"), reason="set OLLAMA_TEST=1 to enable")`
- [ ] G2. Teste único: instancia `OllamaProvider`, chama `generate("Reply with the single word: OK.", temperature=0.0)`, afirma que resposta.strip().upper() == "OK"
- [ ] G3. `py -m pytest tests/integration/` (sem env var) → **1 skipped**
- [ ] G4. `py -m pytest tests/integration/` com `OLLAMA_TEST=1` → **1 passed** (smoke real contra o Ollama rodando)

## Bloco H — Verificações finais

- [ ] H1. `py -m pytest` (todos os testes) → todos verdes, com `test_ai_ollama_live` skipped
- [ ] H2. `py -m app.main` ainda abre a janela do 001 sem warnings novos (UI intocada)
- [ ] H3. `py -c "from app.services import FileManager, AIEngine, OllamaProvider, MockAIProvider, MermaidRenderer; print('imports ok')"` → funciona
- [ ] H4. Smoke ponta-a-ponta: `py -c "..."` que cria `OllamaProvider`, `AIEngine(provider)`, chama `extract_uml_structure('class Foo: pass')`, e loga primeiros 200 chars da resposta (prova que o pipeline real funciona)
- [ ] H5. `git status` mostra apenas arquivos do change 002

## Bloco I — Commit e arquivamento

- [ ] I1. `git add .` e revisar com `git status`
- [ ] I2. `git commit -F .git/COMMIT_EDITMSG.tmp` com mensagem descrevendo os 3 services + testes
- [ ] I3. `git log --oneline` → 2 commits no `main` (001 + 002)
- [ ] I4. Mover `changes/002-services-layer/` para `changes/archive/002-services-layer/`
- [ ] I5. Commit adicional ou amend mencionando o arquivamento (ou commitar separadamente como `chore: archive change 002`)

## Bloco J — Comunicação

- [ ] J1. Reportar pytest verde + 1 integration test gated
- [ ] J2. Mostrar output do smoke ponta-a-ponta (resposta real do Qwen 2.5)
- [ ] J3. Pedir confirmação de que `py -m app.main` ainda funciona (UI intocada)
- [ ] J4. Listar o que entra no **Change 003** (UI integration: FileExplorerPanel real + sinais + thread + Mermaid em texto)

---

## Definition of Done (DoD)

Todos os blocos A–I marcados, H1–H4 verdes, J1–J2 reportados ao
usuário. Só então o `TodoWrite` do Change 002 é marcado como completo.
