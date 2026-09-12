# Change 006 — Proposal: Catálogo Pessoal de Soluções

## Contexto

O ArchExplorer AI nasceu como ferramenta pra **analisar** código
alheio com ajuda de LLM local. Em uso, percebemos que o usuário
(Henrique) tem outra necessidade igualmente importante: **catalogar
as próprias soluções** que ele desenvolveu ou encontrou ao longo da
carreira, pra poder reusar quando aparecer um problema parecido.

Hoje, quando o Henrique resolve algo elegante num projeto, a única
forma de "lembrar depois" é confiar na memória ou anotar em algum
arquivo .md solto. Não há:

- Índice pesquisável por tecnologia / tag / categoria
- Banco unificado que cresce ao longo dos anos
- Forma de injetar a solução diretamente no editor quando precisar
- Compartilhamento estruturado (gist, doc) das entradas públicas

## Proposta

Adicionar um **catálogo pessoal** ao ArchExplorer:

1. Banco **SQLite local** (`catalogo.db` em `%USERPROFILE%/Documents/ArchExplorer/`)
2. **Toggle no menu View** (`View > Catálogo`) substitui a árvore do
   Explorer pelo painel do catálogo no slot da coluna esquerda
3. Form de "Nova entrada" (título, descrição markdown, código,
   linguagem, categoria, tags, origem)
4. Busca **full-text** (FTS5 do SQLite) por título/descrição/código
5. Filtros por linguagem, categoria e tags
6. Botão **Inserir no editor** cola o snippet na posição do cursor
7. Import / Export **JSON** pra backup e migração

## Por que SQLite

- **Sem dependência nova** — `sqlite3` é stdlib do Python
- **Full-text search nativo** via FTS5
- **Escala** — 1 usuário, décadas de uso, milhões de registros
- **Single-file** — fácil backup (`copia o .db` pra outro lugar)
- **Migração** — schema pode evoluir sem perder dados
- **Portable** — copia o arquivo pra outra máquina

## Por que toggle no menu View (e não em toolbar)

- **Padrão VS Code / IDEs** — `View > Side Bar` / `View > Panel` segue
  a mesma convenção. Usuário reconhece.
- **Atalho dedicado** — `Ctrl+2` troca pro catálogo, `Ctrl+1` volta
  pro Explorer (mesmo padrão dos browsers pra abas)
- **Toolbar separada** competiria por espaço com botões existentes
  (Select/+Pasta/Atualizar)
- **Menu View já existe** (theme switcher), é coerente adicionar lá

## Não-objetivos (Change 006)

- **Gist sync** (publicar entradas como gist público) — Change 007
- **Site estático** pras entradas públicas — Change 007
- **Markdown export** com arquivos `.md` por entrada — Change 007
- **Drag-and-drop** de arquivo pro catálogo — Change 007
- **Syntax highlight** nos snippets — Change 008
- **Templates** (snippet reutilizável com placeholders) — Change 008
- **Links** entre entradas (dependências) — Change 008
- **RAG / indexação semântica** (LlamaIndex) — Change 008
- **`.exe` instalável** — Change 009

## Impacto no código existente

| Arquivo | Mudança |
|---|---|
| `app/ui/main_window.py` | Splitter ganha `LeftPanel` (container QStackedWidget) em vez de `FileExplorerPanel` direto; menu View ganha ação "Catálogo" |
| `app/services/` | **Novo:** `catalogo_service.py` + `models.py` (SQLite + FTS5) |
| `app/services/exceptions.py` | **Novo:** `CatalogoError` |
| `app/ui/` | **Novos:** `catalogo_panel.py`, `entry_editor_dialog.py`, `left_panel.py` |
| `app/ui/code_editor.py` | **Novo método:** `insert_text_at_cursor(text)` |
| `app/ui/file_explorer.py` | Sem mudança — vira filho do LeftPanel |
| `tests/` | **Novos:** `test_catalogo_service.py`, `test_catalogo_panel.py`, `test_entry_editor_dialog.py` |
| `docs/` | **Novos:** atualiza `backend.md`, `frontend/front.md`; **novo:** `features/catalog.md` |

## Aceite

- [ ] Toggle `View > Catálogo` (`Ctrl+2`) troca o painel esquerdo
- [ ] Toggle `View > Projeto` (`Ctrl+1`) volta pro Explorer
- [ ] Modo persiste entre execuções via QSettings
- [ ] Botão "Nova entrada" abre dialog com form completo
- [ ] Salvar → entrada aparece na lista imediatamente
- [ ] Busca por texto livre funciona (FTS5)
- [ ] Filtros por linguagem/categoria/tag funcionam
- [ ] Click numa entrada → preview no centro
- [ ] "Inserir no editor" cola no CodeEditorPanel na posição do cursor
- [ ] Import / Export JSON funciona
- [ ] `pytest` ≥ 350 passing (atual: 334)
- [ ] Cobertura ≥ 85% nos módulos novos

## Prazo estimado

1-2 semanas pra Change 006 (Change 007-009 são follow-ups).
