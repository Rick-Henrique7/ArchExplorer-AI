# Change 007 — Proposal: Módulo LPS / SPL (Linha de Produto de Software)

> **Status:** draft · **Autor:** Henrique Moraes dos Santos · **Data:** 2026-09-17

---

## 1. Contexto

O ArchExplorer AI (Changes 001–006) entrega hoje:

- IDE desktop de 3 colunas com LLM local (Qwen 2.5 Coder via Ollama).
- Análise sob demanda, chat livre, "Editar com IA" com diff preview.
- Catálogo pessoal (SQLite + FTS5) de soluções/patterns (`Ctrl+2`).

Tudo isso é focado em **analisar** código existente. Falta um módulo
para **compor** soluções: pegar componentes do catálogo (e de
repositórios externos) e conectá-los num **feature model** que valide
regras de variabilidade e gere o esqueleto de um produto final.

## 2. Oportunidade

Software Product Line Engineering (SPLE) é uma disciplina estabelecida
em engenharia de software, com ferramentas industriais (Eclipse
FeatureIDE, pure::variants, Gears) e acadêmicas. O cerne é simples:

1. Modelar features como nós de um grafo (Mandatory, Optional,
   Alternative, Or).
2. Conectar features com arestas tipadas (Requires, Excludes).
3. Validar a seleção do usuário com um **SAT solver** (ex: pysat /
   z3) — a combinação escolhida tem que ser **satisfatível**.
4. Gerar o produto final (código + assets) a partir de templates
   Jinja2, alimentado pela seleção validada.

Hoje o ArchExplorer tem o catálogo (matéria-prima) mas falta a **linha
de montagem**. Esta change preenche esse buraco.

## 3. Decisão

Adicionar ao ArchExplorer AI um **modo LPS** (toggle `Ctrl+3`) que
substitui temporariamente a coluna central por um **canvas de
variabilidade** (`QGraphicsView` + `QGraphicsScene`) onde:

- O usuário **arrasta** componentes da paleta (esquerda) para o canvas.
- **Conecta** nós com arestas tipadas (Requires / Excludes).
- Vê em tempo real se a configuração atual é **válida** (via pysat).
- Clica em **Gerar Produto** → backend Python escreve a árvore de
  arquivos via Jinja2 + SQLite, respeitando o sandbox do workspace.

### Por que Python nativo (e não Electron + IPC)

Versões anteriores deste módulo foram esboçadas em Electron (Node) +
PHP como backend IPC. Os problemas eram:

- **Complexidade de empacotamento:** 2 runtimes, 2 build pipelines,
  .exe enorme e quebradiço.
- **Latência:** IPC assíncrona adiciona overhead em cada chamada de IA
  ou SAT solver.
- **Distribuição:** impossível entregar via `pip install` ou wheel.

Python nativo (PySide6 + SQLite + pysat + Jinja2) resolve tudo isso:
**um único processo, um único bundle (PyInstaller depois), zero IPC**.
Aproveita ainda que o Change 002 já implementou `IAIProvider` (Protocol)
— o módulo LPS vai herdar o mesmo padrão para multi-provider.

### Por que **pysat** (e não regras caseiras)

Implementar Requires/Excludes/Mandatory/Optional/Alternative/Or com
`if/else` em Python fica ingovernável em modelos com > 10 features.
pysat (e opcionalmente z3) é o padrão usado por FeatureIDE e pela
literatura acadêmica (Benavides et al., 2010). Para o recrutador, é
um diferencial técnico forte: mostra conhecimento de **modelagem
formal + SAT solving**, não apenas CRUD.

### Por que **Jinja2** para geração

- É o padrão de fato em Python para templating (Flask, Ansible,
  Cookiecutter, Sphinx).
- Sintaxe simples (`{{ var }}`, `{% if %}`, `{% for %}`).
- Herança de templates (base + blocos) encaixa naturalmente em
  múltiplos tipos de produto (web app, API, CLI).

### Por que **QGraphicsView** (e não React Flow no QWebEngineView)

Considerado: usar React Flow / Mermaid.js embarcado num
`QWebEngineView` (mesma estratégia que já usamos no visualizer).
Rejeitado: para um canvas com **drag-and-drop interativo** e edição
de arestas em tempo real, o overhead de IPC JS↔Python é alto e a
performance piora com > 50 nós. `QGraphicsView` é nativo, performático
e trivial de integrar com Qt signals.

(Mermaid/React Flow continua sendo usado para o **render** de
diagramas de arquitetura no visualizer — são casos de uso diferentes.)

### Por que **LiteLLM** (e não cliente por provider)

LiteLLM dá uma interface unificada para OpenAI, Anthropic, Gemini,
Ollama, Cohere etc. — basta trocar `model=` na chamada. Para o
recrutador, isso mostra conhecimento de **adapter pattern** aplicado
a um domínio real (LLM providers são o caso de uso mais popular em
2026).

### Por que **MCP / Tool Use** (e não prompts livres)

Prompts livres ("cria uma pasta e joga o Auth.py lá") geram saída
**imprevisível** — a IA inventa caminhos, ignora estrutura, escreve
em locais errados. Tool Use (OpenAI function calling, Anthropic
tools, Gemini function calling) **força** a IA a emitir uma chamada
de função estruturada (JSON), que validamos e executamos num
**sandbox** (path traversal protection). É o mesmo padrão que o
Cursor, Continue.dev e Cline adotaram.

## 4. Valor para recrutadores

Esta change adiciona ao ArchExplorer um módulo que demonstra:

- **Engenharia de Software clássica:** feature modeling, variabilidade,
  SAT solving (padrão Eclipse FeatureIDE).
- **Python desktop maduro:** PySide6 + QGraphicsView + signals/slots,
  threading sem travar UI.
- **Adapter + sandbox patterns:** `IAIProvider` (já existente),
  `LlmAdapter` via LiteLLM, `FileSystemAgent` com path traversal
  protection.
- **IA agentic moderna:** Tool Use / Function Calling com provedores
  reais (OpenAI, Anthropic, Ollama local).

## 5. Escopo

### Dentro
- Modo LPS (`Ctrl+3`) com 3 painéis (paleta, canvas, inspector).
- Persistência local em SQLite (mesmo arquivo `catalogo.db` ou novo
  `lps.db` — decidir em `design.md`).
- SAT solver via pysat (z3 opcional, opt-in).
- Templates Jinja2 empacotados (`app/templates/`) com 2-3 exemplos.
- Multi-provider LLM via LiteLLM (OpenAI, Anthropic, Ollama).
- Tool Use seguro (criar arquivo, criar pasta) com sandbox.
- Catálogo de componentes: reutiliza o `CatalogoService` do Change 006.
- Testes: ≥ 30 novos, cobertura ≥ 85% nos módulos novos.

### Fora (changes futuras)
- Suporte a features **cardinality-based** (`[1..3]`).
- Editor visual de regras avançadas (cross-tree constraints).
- Exportação para outros formatos de feature model (FeatureIDE XML,
  UVL — Universal Variability Language).
- Geração de diagramas UML a partir do feature model resolvido.
- Sincronização com GitHub (importar feature models de repos).

## 6. Alternativas rejeitadas

| Alternativa | Por que rejeitada |
|---|---|
| Manter Electron + PHP IPC | Complexidade de empacotamento, latência, dois runtimes. |
| Implementar SAT solving manualmente | Inviável para > 10 features; perde o valor acadêmico/industrial. |
| Usar React Flow via QWebEngineView | IPC JS↔Python caro; performance piora com escala. |
| LLM provider-por-provider sem adapter | Explosão de código se quisermos suportar > 2 providers. |
| IA só via prompt livre (sem Tool Use) | Saída imprevisível; impossível validar; sem sandbox. |

## 7. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| pysat (binding C) não builda em algum Windows | pinar `python-sat==0.1.8.dev6` ou fallback para z3 puro-Python |
| SAT solver fica lento em modelos grandes | limite de features por modelo (50) com aviso; cache de resoluções |
| LiteLLM adiciona ~50 deps | import lazy; aceitar como dependência opcional `pip install archexplorer-ai[llm]` |
| IA escreve arquivo no lugar errado | sandbox de path traversal + confirmação visual para paths fora de `~/Documents/ArchExplorer/` |
| Template Jinja2 malicioso | rodar Jinja2 em `SandboxedEnvironment`, sem `__import__`, sem file I/O no template |

## 8. Métricas de sucesso

- ≥ 30 testes novos, ≥ 85% cobertura nos módulos novos.
- Modelo de 20 features validado em < 100 ms (pysat g3).
- Geração de projeto (zip com 10 arquivos) em < 1 s.
- LLM Tool Use round-trip (request → tool call → execução → resposta)
  em < 3 s para Ollama local; < 5 s para APIs cloud.

## 9. Próximos passos

1. **Agora:** fechar os 4 artefatos SDD (proposal, spec, design, tasks).
2. **Em seguida:** revisar e marcar como `accepted`.
3. **Depois:** implementação em blocos (Bloco A: modelo + SAT; Bloco B:
   GUI drag-and-drop; Bloco C: gerador Jinja2; Bloco D: multi-LLM +
   Tool Use; Bloco E: wiring + testes + docs).
