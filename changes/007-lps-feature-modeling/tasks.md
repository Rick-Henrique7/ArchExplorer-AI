# Change 007 — Tasks: Módulo LPS / SPL

> Checklist executável. Marcar `[x]` conforme conclusão. Cada bloco
> termina com `pytest` verde antes de começar o próximo.

---

## Bloco A — Fundação do serviço + SAT Solver

- [ ] A1. Adicionar `pysat` em `requirements-dev.txt` e `pyproject.toml` (deps)
- [ ] A2. Adicionar `pydantic` em `requirements-dev.txt` (validação do DSL)
- [ ] A3. `app/services/exceptions.py`: adicionar `LpsSpecError`, `LpsValidationError`, `LlmToolError`
- [ ] A4. `app/services/lps_service.py`: classe `LpsService` com `__init__(db_path)` e `_init_schema()`
- [ ] A5. `_init_schema()`: executar schema (lps_components, lps_feature_models, lps_product_runs + índices)
- [ ] A6. `app/services/lps_models.py`: `LpsComponent`, `FeatureModel`, `FeatureNode`, `FeatureEdge`, `FeatureGroup` como `@dataclass(frozen=True)`
- [ ] A7. `app/services/variability_solver.py`: classe `VariabilitySolver` com `encode(model)` e `is_satisfiable(encoded, selection)`
- [ ] A8. Implementar tradução JSON → cláusulas CNF (MANDATORY/OPTIONAL/REQUIRES/EXCLUDES/ALTERNATIVE/OR)
- [ ] A9. `tests/unit/test_lps_service.py`: 8+ testes (CRUD básico + isolamento do catálogo)
- [ ] A10. `tests/unit/test_variability_solver.py`: 10+ testes (cada regra isolada + casos combinados)
- [ ] A11. Smoke: `python -c "from app.services import VariabilitySolver; print('ok')"`

---

## Bloco B — Gerador Jinja2 (sandboxed) + templates base

- [ ] B1. Adicionar `Jinja2` em deps (já vem via FastAPI? se não, direto)
- [ ] B2. `app/services/template_engine.py`: classe `TemplateEngine` com `SandboxedEnvironment`
- [ ] B3. `app/templates/lps/base/python_package.zip.j2`: template raiz que gera estrutura Python
- [ ] B4. `app/templates/lps/base/readme.md.j2`: README gerado
- [ ] B5. `app/templates/lps/base/gitignore.j2`: .gitignore Python
- [ ] B6. `app/templates/lps/services/fastapi_app.py.j2`: exemplo FastAPI
- [ ] B7. `app/templates/lps/services/cli_app.py.j2`: exemplo CLI (argparse)
- [ ] B8. `app/templates/lps/infra/docker_compose.yml.j2`: docker-compose base
- [ ] B9. `app/templates/lps/infra/dockerfile.python.j2`: Dockerfile Python
- [ ] B10. `tests/unit/test_template_engine.py`: 6+ testes (render OK, sandbox bloqueia `__import__`, paths criados)

---

## Bloco C — CRUD de componentes e feature models

- [ ] C1. `LpsService.create_component(...)`: INSERT em `lps_components`
- [ ] C2. `LpsService.get_component(id)`, `list_components(category=None)`, `update_component(id, ...)`, `delete_component(id)`
- [ ] C3. `LpsService.create_feature_model(title, description, tree_structure_json)` — persiste JSON via Contrato 1
- [ ] C4. `LpsService.get_feature_model(id)`, `list_feature_models()`, `update_tree_structure(id, json)`
- [ ] C5. `LpsService.record_run(model_id, resolved_json, output_dir, file_count, duration_ms, status, error_message)`
- [ ] C6. `LpsService.list_runs(model_id)`, `latest_run(model_id)`
- [ ] C7. Validação de JSON no `update_tree_structure` via pydantic (`LpsFeatureModelPayload`)
- [ ] C8. `tests/unit/test_lps_service.py::test_*_component`: 8+ testes
- [ ] C9. `tests/unit/test_lps_service.py::test_*_feature_model`: 6+ testes
- [ ] C10. `tests/unit/test_lps_service.py::test_*_runs`: 3+ testes

---

## Bloco D — GUI: palette + canvas + inspector

- [ ] D1. `app/ui/lps_palette_panel.py`: `LpsPalettePanel(QWidget)` — QListWidget com drag habilitado
- [ ] D2. MIME type customizado `application/x-lps-component` com payload JSON `{component_id, name, category}`
- [ ] D3. `app/ui/lps_canvas_view.py`: `LpsCanvasView(QGraphicsView)` — aceita drops
- [ ] D4. `app/ui/lps_canvas_scene.py`: `LpsCanvasScene(QGraphicsScene)` — gerencia nodes/edges, emits signals
- [ ] D5. `app/ui/lps_node_item.py`: `LpsNodeItem(QGraphicsRectItem)` — visual + 4 anchors
- [ ] D6. `app/ui/lps_edge_item.py`: `LpsEdgeItem(QGraphicsPathItem)` — REQUIRES (sólida) / EXCLUDES (tracejada)
- [ ] D7. `app/ui/lps_inspector_panel.py`: `LpsInspectorPanel(QWidget)` — form para nó selecionado
- [ ] D8. `LpsCanvasScene.to_json()` / `from_json(payload)` — serializa para Contrato 1
- [ ] D9. Toolbar do canvas: [Validar] [Gerar Produto] [Auto-layout] [Limpar]
- [ ] D10. `tests/unit/test_lps_palette.py`: 4+ testes
- [ ] D11. `tests/unit/test_lps_canvas.py`: 6+ testes (drop, seleção, edges, JSON round-trip)
- [ ] D12. `tests/unit/test_lps_node_item.py`: 4+ testes (posição, anchors, double-click)
- [ ] D13. `tests/unit/test_lps_edge_item.py`: 3+ testes (REQUIRES vs EXCLUDES visual)

---

## Bloco E — Workers + MainWindow wiring

- [ ] E1. `app/workers/lps_solver_worker.py`: `LpsSolverWorker(QRunnable)` com `_WorkerSignals`
- [ ] E2. `app/workers/lps_generator_worker.py`: `LpsGeneratorWorker` — progresso (done/total) + finished
- [ ] E3. `app/workers/lps_llm_worker.py`: `LpsLlmWorker` — chunk (stream), tool_call, finished
- [ ] E4. `MainWindow`: `View > Painel esquerdo > LPS` (Ctrl+3) — toggle modo LPS
- [ ] E5. Modo LPS substitui `CodeEditorPanel` (centro) por `LpsCanvasView`
- [ ] E6. Modo LPS substitui `LeftPanel` por `LpsPalettePanel`
- [ ] E7. Modo LPS substitui `VisualizerPanel` (direita) por `LpsInspectorPanel` (3 colunas: palette, canvas, inspector)
- [ ] E8. Auto-save (QTimer 30s) quando canvas dirty
- [ ] E9. `MainWindow._on_lps_validate`: dispara `LpsSolverWorker`, mostra badge verde/vermelho
- [ ] E10. `MainWindow._on_lps_generate`: dialog "Selecionar diretório" + `LpsGeneratorWorker`
- [ ] E11. `tests/unit/test_lps_solver_worker.py`: 4+ testes (síncronos, sem thread pool)
- [ ] E12. `tests/unit/test_lps_generator_worker.py`: 4+ testes
- [ ] E13. `tests/integration/test_lps_full_flow.py`: 5+ testes end-to-end (cria component → monta modelo → valida → gera)

---

## Bloco F — LLM Adapter + Tool Use

- [ ] F1. Adicionar `litellm` em deps (opcional, extra `[llm]`)
- [ ] F2. `app/services/llm_adapter.py`: Protocol `LlmAdapter`, dataclasses `LlmResponse`, `ToolCall`
- [ ] F3. `app/services/llm_adapter.py`: `LiteLlmAdapter` com multi-provider (openai, anthropic, gemini, ollama_local, cohere)
- [ ] F4. `app/services/filesystem_agent.py`: `FileSystemAgent` com sandbox (path traversal, regex, max size)
- [ ] F5. `LlmToolError` com `reason` (path_traversal, invalid_chars, file_too_large, file_not_found, not_a_directory)
- [ ] F6. Função `run_agent_loop()`: loop Tool Use (max 10 iterações)
- [ ] F7. `tests/unit/test_llm_adapter.py`: 6+ testes (mock litellm.completion, multi-provider, tool_calls parsing)
- [ ] F8. `tests/unit/test_filesystem_agent.py`: 8+ testes (path traversal, parent dir, file size, encoding)
- [ ] F9. `tests/unit/test_agent_loop.py`: 4+ testes (loop termina em resposta final, loop termina em max_iter, erro de tool vira mensagem)

---

## Bloco G — Settings + Chat integrado

- [ ] G1. `app/ui/settings_dialog.py`: dialog com QComboBox para escolher provider + spinbox temperature/max_tokens
- [ ] G2. Persistir config em QSettings (`llm/active_provider`, `llm/api_key_env_*`) e em `config/llm_config.json`
- [ ] G3. LLM tab no chat visualizer (`Ctrl+L`): prompt + tools visíveis + history
- [ ] G4. Chat com Tool Use: cada tool_call aparece como chip colorido no histórico
- [ ] G5. Botão "Agent Loop" no chat: roda o loop com prompt do usuário
- [ ] G6. `tests/unit/test_settings_dialog.py`: 4+ testes (persistência, validação)
- [ ] G7. `tests/integration/test_lps_chat_flow.py`: 4+ testes (chat → IA cria arquivo → file_system atualiza tree)

---

## Bloco H — Docs + empacotamento

- [ ] H1. `docs/features/lps.md`: tutorial completo ("Como modelar e gerar um produto")
- [ ] H2. `docs/features/tool-use.md`: tutorial do agente IA ("Como a IA cria arquivos")
- [ ] H3. `docs/backend/backend.md`: nova seção `LpsService` + SAT solver + gerador
- [ ] H4. `docs/frontend/front.md`: nova seção LPS (palette/canvas/inspector + Ctrl+3)
- [ ] H5. `docs/decisions/decisions.md`: 5 novas decisões (pysat, Jinja2 sandboxed, LiteLLM, pydantic, mesmo DB)
- [ ] H6. `docs/testing/testing-strategy.md`: como mockar pysat / litellm / filesystem_agent
- [ ] H7. README: novo bullet "Módulo LPS" + roadmap + badge
- [ ] H8. Tutorial de importação de ícones (SVG/PNG) na paleta

---

## Bloco I — Commit + archive

- [ ] I1. `pytest` ≥ 521 passing (atual: 491; +30 mínimo)
- [ ] I2. Cobertura ≥ 85% nos módulos novos (`LpsService`, `VariabilitySolver`, `TemplateEngine`, `LlmAdapter`, `FileSystemAgent`, GUI nova)
- [ ] I3. Smoke: `python -m app.main` abre Ctrl+3 sem warnings
- [ ] I4. Manual: criar feature model com 5 nodes → validar → gerar produto → abrir zip
- [ ] I5. Commit único: `feat(change-007): LPS module ...`
- [ ] I6. Push pro remote
- [ ] I7. Move `changes/007-lps-feature-modeling/` para `changes/archive/`
- [ ] I8. Commit `chore: archive change 007 (LPS module shipped)`

---

## Definição de Done

Todos os blocos A–H marcados, I1–I4 confirmados, I5–I8 commitados.

---

## Notas

- **Bloco A** é fundação (pysat + schema); fazer primeiro.
- **Bloco D** (GUI) é o mais caro em tempo — começar cedo pra iterar com o usuário.
- **Bloco F** (LLM + Tool Use) tem dependência externa (LiteLLM); pinar versão e testar offline com mocks antes de rodar online.
- **Bloco H** (docs) pode ir em paralelo com qualquer outro.
- Cada bloco termina com `pytest tests/<bloco>_<test>.py` verde antes do próximo.
- Se pysat não buildar em alguma plataforma, fallback para z3 puro-Python (registrar como issue separado).
