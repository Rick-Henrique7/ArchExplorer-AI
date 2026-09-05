# Diretrizes Arquiteturais e Princípios SOLID

Este documento define os padrões arquiteturais, decisões de design e regras de código obrigatórias para o desenvolvimento do ArchExplorer AI.

---

## 1. Visão Geral da Arquitetura

O ArchExplorer AI adota uma arquitetura em camadas fracamente acopladas, baseada no padrão **Model-View-Presenter (MVP)** ou **Controller/Service Layer** adaptado para aplicações desktop em PyQt6.

* **Presentation Layer (UI):** Responsável estritamente pela exibição e captura de interações do usuário.
* **Service Layer (Business Logic):** Concentra a orquestração de regras de negócio, manipulação de arquivos no SO e chamadas ao motor de IA.
* **Engine/Infrastructure Layer:** Gerencia a comunicação de baixo nível com o processo local da IA (Qwen 2.5-Coder 3B via Ollama/processo embutido).

---

## 2. Aplicação Prática dos Princípios SOLID

### Single Responsibility Principle (SRP)
Cada classe ou módulo deve ter apenas uma razão para mudar:
* **`FileExplorer` (UI):** Captura cliques e exibe a árvore de diretórios. Não faz leitura ou gravação direta em disco.
* **`FileManager` (Service):** Executa operações físicas no sistema de arquivos (`mkdir`, `copy`, `move`). Não interage com elementos gráficos.
* **`AIEngine` (Service):** Comunica-se com o modelo local Qwen 2.5-Coder. Não faz parsing de sintaxe Mermaid ou manipulação de UI.
* **`DiagramGenerator` (Service):** Recebe o código ou resposta bruta da IA e formata em sintaxe Mermaid/UML válida.

### Open/Closed Principle (OCP)
Módulos devem estar abertos para extensão, mas fechados para modificação:
* O renderizador de diagramas deve utilizar um contrato base (`BaseDiagramRenderer`). Se no futuro for necessário adicionar suporte a **PlantUML** ou **Graphviz** além do **Mermaid.js**, basta criar uma nova subclasse sem alterar a lógica principal da janela (`MainWindow`).

### Liskov Substitution Principle (LSP)
Subtipos devem ser substituíveis por seus tipos de base sem quebrar a aplicação:
* Qualquer implementação do provedor de IA (ex: `OllamaProvider`, `LlamaCppProvider`, ou um `MockAIProvider` para testes) deve seguir a interface `IAIProvider`. O sistema deve operar de forma idêntica independentemente da implementação concreta.

### Interface Segregation Principle (ISP)
Clientes não devem ser forçados a depender de interfaces que não utilizam:
* Em vez de uma interface genérica e gigante para eventos da janela, dividimos em contratos menores: `IFileActionHandler` (operações de disco), `IAIActionHandler` (comandos de prompt) e `ICodeEditorHandler` (edição e destaque de código).

### Dependency Inversion Principle (DIP)
Módulos de alto nível não devem depender de módulos de baixo nível. Ambos devem depender de abstrações:
* A janela principal (`MainWindow`) não instancia diretamente o cliente do Ollama ou o gerenciador de arquivos nativo. As dependências são injetadas via construtor (`Dependency Injection`), facilitando o uso de Mocks nos testes automatizados.

---

## 3. Boas Práticas Adicionais

* **Tratamento de Exceções:** Falhas de I/O de arquivos ou tempo limite da IA não devem travar a thread principal da interface. As chamadas pesadas devem rodar em threads separadas (`QThread` / `QThreadPool`).
* **Clean Code:** Métodos pequenos, nomes expressivos em inglês para o código, e comentários restritos apenas ao "porquê" de decisões complexas.
* **Imutabilidade de Estado na UI:** O estado do arquivo selecionado e do diagrama renderizado deve ser centralizado para evitar inconsistências entre os três painéis.


**Não use emojis prefira sempre icones**