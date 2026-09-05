# Change 001 — Spec: Esqueleto PySide6

> Especificação do **comportamento observável** do esqueleto. Não descreve
> implementação — para isso veja `design.md`.

---

## 1. Comando de execução

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
py -m app.main
```

Resultado esperado: uma janela desktop abre, centralizada na tela, com
título `ArchExplorer AI`, tamanho padrão ~1100×700, contendo três painéis
horizontais lado a lado separados por `QSplitter`.

## 2. Layout visível

```
+---------------------------+--------------------------+--------------------------+
|  File Explorer            |  Editor                  |  Visualizer              |
|  (placeholder)            |  (placeholder)           |  (placeholder)           |
|                           |                          |                          |
|  [ label "File Explorer" ]|  [ label "Editor" ]      |  [ label "Visualizer" ]  |
|                           |                          |                          |
+---------------------------+--------------------------+--------------------------+
        ~25% largura               ~45% largura                ~30% largura
```

- Todos os painéis têm fundo cinza claro (cor padrão Qt) e fonte 14pt.
- Os separadores do `QSplitter` são arrastáveis.
- Janela é redimensionável; ao redimensionar, os painéis mantêm suas
  proporções relativas.
- Fechar a janela encerra o processo Python (sem processos zumbis).

## 3. Sem interações

No escopo do Change 001, **nenhuma interação é funcional**:

- Nenhum clique em menu responde
- Nenhum atalho responde
- Os labels são apenas texto estático
- Nenhum arquivo é lido do disco pelo app
- Nenhuma chamada de IA é feita

Isso é proposital: o change valida que a base Qt/PySide6 sobe no Windows
antes de qualquer lógica.

## 4. Saída de log

O app não imprime nada no stdout durante a execução normal. Se
instanciado sem display (modo teste), a inicialização completa sem erro.

## 5. Saída do pytest

```
$ py -m pytest -v
============================= test session starts =============================
platform win32 -- Python 3.13.13, pytest-8.x
collected 1 item

tests/unit/test_main_window.py::test_main_window_has_three_panels PASSED

============================== 1 passed in X.XXs ===============================
```

## 6. Comportamento de plataforma headless

O smoke test usa `QT_QPA_PLATFORM=offscreen` para permitir pytest em CI sem
display. Nesse modo:

- A `QApplication` é criada normalmente
- O `MainWindow` é instanciado e `show()` não trava
- Os 3 painéis são filhos do `QSplitter` central
- Nenhum pixel é renderizado (mas a contagem de widgets é confiável)

## 7. Restrições de ambiente

- **Python**: `>=3.10,<3.14` (3.13.x testado, mas 3.14 pode quebrar)
- **SO alvo**: Windows 11 (CI roda em `windows-latest`)
- **Dependências runtime** (em `requirements.txt`):
  - `PySide6>=6.8`
  - `requests>=2.32`
- **Dependências dev** (em `requirements-dev.txt` ou seção `[project.optional-dependencies]`):
  - `pytest>=8`
  - `pytest-cov>=5`
  - `pytest-mock>=3.14`

## 8. Erros e exceções

- Falha ao criar `QApplication` (já existe outra instância) → erro fatal,
  mensagem em stderr, exit code 1. Não tratado neste change (a PySide6 já
  emite mensagem clara).
- Falha ao instanciar `MainWindow` (import quebrado, etc.) → propaga como
  traceback Python normal, exit code 1.
