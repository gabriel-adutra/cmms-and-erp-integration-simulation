# Sistema de Integração TracOS ↔ Cliente

## Sobre o Projeto

Este projeto implementa um serviço Python assíncrono que simula uma integração bidirecional entre o CMMS TracOS da Tractian e o sistema ERP de um cliente. O sistema sincroniza ordens de trabalho entre os dois sistemas, realizando fluxos inbound (Cliente → TracOS) e outbound (TracOS → Cliente) com tradução de dados e validação.

## Arquitetura

O sistema foi projetado com **separação clara de responsabilidades** para facilitar a adição de novas integrações sem modificar módulos existentes:

### Módulos Principais
- **`client_adapter.py`** - Operações de leitura/escrita com sistema cliente (arquivos JSON)
- **`tracos_adapter.py`** - Operações de leitura/escrita com sistema TracOS (MongoDB)
- **`translator.py`** - Tradução bidirecional de formatos de dados entre sistemas
- **`config.py`** - Configuração centralizada via variáveis de ambiente
- **`main.py`** - Orquestrador principal do pipeline de integração

### Características do Sistema
- **Assíncrono**: Operações MongoDB não-bloqueantes para melhor performance
- **Resiliente**: Tratamento robusto de erros de I/O e falhas temporárias de rede
- **Idempotente**: Operações seguras para retry usando upsert com chaves únicas
- **Extensível**: Arquitetura modular permite adicionar novos sistemas facilmente

### Destaques Técnicos Implementados
- **Padrão Singleton**: Configuração centralizada com carregamento único
- **Retry com Backoff Exponencial**: Recuperação automática de falhas temporárias (1s → 2s → 4s)
- **Logging Estruturado**: Logs claros com métricas automáticas de performance
- **Gestão de Recursos**: Reutilização inteligente de conexões MongoDB e cleanup automático
- **Validação Rigorosa**: Campos obrigatórios e tipos validados com mensagens de erro específicas
- **Isolamento de Falhas**: Um arquivo com problema não interrompe o pipeline inteiro

## Como o Sistema Funciona

### Fluxo Inbound (Cliente → TracOS)
1. **Leitura**: Processa arquivos JSON da pasta `data/inbound/` (simulando respostas de API do cliente)
2. **Validação**: Verifica campos obrigatórios (`orderNo`, `summary`, `creationDate`)
3. **Tradução**: Converte formato do cliente para formato TracOS (ex: status booleanos → enums)
4. **Persistência**: Salva/atualiza registros no MongoDB com `isSynced=false`

### Fluxo Outbound (TracOS → Cliente)
1. **Consulta**: Busca workorders no MongoDB com `isSynced=false`
2. **Tradução**: Converte formato TracOS para formato do cliente
3. **Geração**: Cria arquivos JSON na pasta `data/outbound/` (prontos para "enviar" ao cliente)
4. **Marcação**: Atualiza registros no MongoDB com `isSynced=true` e timestamp `syncedAt`

### Normalização de Dados
- **Datas**: Normalizadas para UTC ISO 8601
- **Status**: Mapeamento entre enums (cliente usa booleanos, TracOS usa strings)
- **Campos**: Tradução entre diferentes nomenclaturas e estruturas

### Regra de Negócio Importante
**Status Padrão para Workorders**: Quando uma workorder do cliente não possui nenhum status ativo (todos os campos booleanos são `false`), o sistema automaticamente aplica `status="pending"` no TracOS. Isso garante que toda workorder tenha um estado válido no sistema.

**Exemplo**: Cliente envia `isPending: false, isDone: false, isCanceled: false, isOnHold: false` → Sistema aplica `"pending"` → Retorna `isPending: true` na sincronização de volta.

## Estrutura do Projeto

```
tractian_integrations_engineering_technical_test/
├── docker-compose.yml              # Container MongoDB
├── pyproject.toml                  # Dependências Poetry
├── setup.py                        # Script de inicialização com dados de exemplo
├── .env                           # Variáveis de ambiente
├── data/
│   ├── inbound/                   # Arquivos JSON de entrada (Cliente → TracOS)
│   └── outbound/                  # Arquivos JSON de saída (TracOS → Cliente)
├── src/
│   ├── main.py                    # Script principal - executa pipeline completo
│   ├── client_adapter.py          # Módulo para operações com sistema cliente
│   ├── tracos_adapter.py          # Módulo para operações com sistema TracOS
│   ├── translator.py              # Módulo para tradução entre formatos
│   └── config.py                  # Configuração centralizada
└── tests/
    └── test_integration.py        # Testes end-to-end
```

---

## Pré-requisitos

Antes de começar, certifique-se de ter instalado:
- **Python 3.11+**
- **Docker e Docker Compose**
- **Poetry** para gerenciamento de dependências

## Configuração do Ambiente

### 1. Instalar Dependências
```bash
# Instalar Poetry (se necessário)
curl -sSL https://install.python-poetry.org | python3 -

# Instalar dependências do projeto
poetry install
```

### 2. Subir MongoDB
```bash
# Inicializar container MongoDB
docker compose up -d

# Verificar se container está rodando
docker ps
```

### 3. Inicializar Dados de Exemplo
```bash
# Criar dados de amostra (TracOS + Cliente)
poetry run python setup.py
```

### 4. Executar Pipeline
```bash
# Executar integração bidirecional completa
poetry run python src/main.py
```

### 5. Verificar Resultados
```bash
# Verificar arquivos gerados pelo pipeline
ls data/outbound/
```

## Executando o Sistema

### Rodar Pipeline Completo
```bash
# Executa fluxo inbound + outbound completo
poetry run python src/main.py
```

## Testes

### Executar Testes End-to-End
```bash
# Execução simples
poetry run pytest

# Execução com logs detalhados (recomendado)
poetry run pytest -v -s
```

### O Que os Testes Validam
- ✅ Pipeline completo: fluxo inbound → MongoDB → outbound
- ✅ Tradução correta de dados entre formatos Cliente ↔ TracOS  
- ✅ Integridade: dados de entrada correspondem aos dados de saída
- ✅ Tratamento de erros e logging apropriado

## Troubleshooting

### Problemas Comuns

**MongoDB não conecta**:
```bash
# Verificar se container está rodando
docker ps | grep mongo

# Reiniciar se necessário
docker compose down && docker compose up -d
```

**Testes falhando**:
```bash
# Limpar ambiente e recomeçar
docker compose down -v
docker compose up -d
poetry run python setup.py
poetry run pytest -v -s
```

**Dados não aparecem**:
```bash
# Verificar se dados de exemplo foram criados
ls data/inbound/
# Se vazio, executar: poetry run python setup.py
```

---

## Configuração

### Variáveis de Ambiente
O arquivo `.env` contém as configurações necessárias:
```bash
MONGO_URI=mongodb://localhost:27017/tractian
DATA_INBOUND_DIR=./data/inbound  
DATA_OUTBOUND_DIR=./data/outbound
```

## Exemplo de Dados

### JSON de Entrada (Cliente → TracOS)
```json
{
  "orderNo": 1,
  "isCanceled": true,
  "isDeleted": false,
  "isDone": false,
  "isOnHold": false,
  "isPending": false,
  "summary": "Example workorder #1",
  "creationDate": "2025-09-30T23:04:29.045089+00:00",
  "lastUpdateDate": "2025-10-01T00:04:29.045089+00:00",
  "deletedDate": null
}
```

### Formato TracOS (MongoDB Interno)
```json
{
  "_id": "ObjectId('69029d7dbc2225d88a00780d')",
  "number": 1,
  "status": "cancelled",
  "title": "Example workorder #1",
  "description": "Example workorder #1 description",
  "createdAt": "2025-09-30T23:04:29.045Z",
  "updatedAt": "2025-10-29T23:04:29.685Z",
  "deleted": false,
  "isSynced": false
}
```

### JSON de Saída (TracOS → Cliente)
```json
{
  "orderNo": 1,
  "summary": "Example workorder #1",
  "creationDate": "2025-09-30T23:04:29.045000",
  "lastUpdateDate": "2025-10-29T23:04:29.685000",
  "isDeleted": false,
  "deletedDate": null,
  "isDone": false,
  "isCanceled": true,
  "isOnHold": false,
  "isPending": false,
  "isActive": false
}
```

### Formato TracOS (Após Sincronização)
```json
{
  "_id": "ObjectId('69029d7dbc2225d88a00780d')",
  "number": 1,
  "status": "cancelled", 
  "title": "Example workorder #1",
  "description": "Example workorder #1 description",
  "createdAt": "2025-09-30T23:04:29.045Z",
  "updatedAt": "2025-10-29T23:04:29.685Z",
  "deleted": false,
  "isSynced": true,
  "syncedAt": "2025-10-29T23:04:29.788Z"
}
```

---

*Sistema de integração TracOS ↔ Cliente implementado com foco em modularidade, resiliência e facilidade de extensão para novos sistemas.*