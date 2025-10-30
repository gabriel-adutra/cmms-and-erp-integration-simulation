# Sistema de Integração TracOS ↔ Cliente

## Sobre o Projeto

Este projeto implementa um sistema de integração bidirecional assíncrona entre o CMMS TracOS da Tractian e sistemas ERP de clientes, realizando sincronização automática de ordens de trabalho com tradução de dados, validação e recuperação de falhas.

## Arquitetura Escolhida

### Padrão Modular com Separation of Concerns
- **`client_adapter.py`** - Operações I/O com sistema cliente (arquivos JSON)
- **`tracos_adapter.py`** - Operações MongoDB com sistema TracOS
- **`translator.py`** - Conversão bidirecional de formatos de dados
- **`config.py`** - Configuração centralizada via variáveis de ambiente
- **`main.py`** - Orquestrador do pipeline principal

### Características Técnicas
- **Assíncrono**: Operações MongoDB não-bloqueantes com motor driver
- **Resiliente**: Retry logic para falhas temporárias + I/O error handling específico
- **Idempotente**: Operações seguras para retry (upsert com chave única)
- **Observável**: Logging estruturado com loguru para monitoramento

## Como o Sistema Funciona

### Fluxo Inbound (Cliente → TracOS)
```
Arquivos JSON → Validação → Tradução → MongoDB
data/inbound/   client_adapter  translator   tracos_adapter
```

### Fluxo Outbound (TracOS → Cliente)
```
MongoDB → Tradução → Arquivos JSON → Marcação Sincronizada
tracos_adapter  translator  client_adapter  tracos_adapter
```

### Pipeline Completo
1. **Leitura**: Processa arquivos `data/inbound/*.json`
2. **Validação**: Verifica campos obrigatórios (`orderNo`, `summary`, `creationDate`)
3. **Tradução**: Converte formato Cliente → TracOS (status boolean → enum)
4. **Persistência**: Salva no MongoDB com `isSynced=false`
5. **Sincronização**: Lê registros não sincronizados do MongoDB
6. **Conversão**: Traduz TracOS → Cliente (enum → boolean)
7. **Geração**: Cria arquivos `data/outbound/workorder_*.json`
8. **Controle**: Marca registros como `isSynced=true`

### Regra de Negócio: Status Padrão
**Importante**: Workorders do cliente sem status ativo (todos os campos `false`) recebem automaticamente `status="pending"` no TracOS. Isso garante que toda workorder tenha um estado válido no sistema. 

**Exemplo**: `isPending: false` → Sistema aplica `"pending"` → Retorna `isPending: true`

## Estrutura de Pastas

```
integrations-engineering-code-assessment/
├── docker-compose.yml              # Container MongoDB
├── pyproject.toml                  # Dependências Poetry
├── setup.py                        # Inicialização dados amostra
├── project_requirements.md         # Requisitos originais do projeto
├── .env                           # Variáveis ambiente
├── data/
│   ├── inbound/                   # JSONs entrada (Cliente → TracOS)
│   │   ├── 1.json                 # Workorder cliente #1
│   │   ├── 2.json                 # Workorder cliente #2
│   │   └── ...                    # Arquivos gerados pelo setup.py
│   └── outbound/                  # JSONs saída (TracOS → Cliente)
│       ├── workorder_1.json       # Workorder convertida #1
│       ├── workorder_2.json       # Workorder convertida #2
│       └── ...                    # Arquivos gerados pelo pipeline
├── src/
│   ├── main.py                    # Pipeline principal (ponto entrada)
│   ├── client_adapter.py          # Adaptador sistema cliente
│   ├── tracos_adapter.py          # Adaptador sistema TracOS
│   ├── translator.py              # Tradutor formatos dados
│   └── config.py                  # Configurações centralizadas
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

## Testes End-to-End

### Executar Testes
```bash
# Execução silenciosa (apenas resultados finais)
poetry run pytest

# Execução com nomes dos testes
poetry run pytest -v

# Execução completa com logs do sistema (RECOMENDADO para avaliação)
poetry run pytest -v -s


### Cobertura de Testes
Os testes validam:
- ✅ **Pipeline completo**: Fluxo inbound → MongoDB → outbound  
- ✅ **Mapeamento de campos**: Conversão correta Cliente ↔ TracOS
- ✅ **Compliance de schema**: Validação de enums e formatos TracOS
- ✅ **Integridade de dados**: Dados de entrada = dados de saída
- ✅ **Resiliência**: Ambiente limpo entre execuções

### Troubleshooting de Testes

**Se os testes falharem**:
```bash
# 1. Verificar se MongoDB está rodando
docker ps | grep mongo

# 2. Limpar dados e reinicializar
docker compose down -v
docker compose up -d
poetry run python setup.py
poetry run pytest -v -s

# 3. Verificar logs detalhados do sistema
poetry run python src/main.py
```

**Interpretação de Falhas Comuns**:
- `AssertionError: Campo X diferente` → Problema no mapeamento de dados
- `Connection refused` → MongoDB não está acessível  
- `FileNotFoundError` → Dados de amostra não foram criados (`setup.py`)

**Comandos Úteis para Troubleshooting**:
```bash
# Verificar container MongoDB
docker ps | grep mongo

# Apenas reiniciar (mantém dados)
docker compose restart

# Limpar completamente e recomeçar (remove dados)
docker compose down -v && docker compose up -d

# Verificar logs do MongoDB
docker logs tractian-mongo

# Verificar formato de arquivos JSON
cat data/inbound/1.json | jq .
```

---

## Configuração Detalhada

### Variáveis de Ambiente
O sistema usa valores padrão, mas você pode customizar criando um arquivo `.env`:
```bash
# Opcional: criar arquivo .env para customização
MONGO_URI=mongodb://localhost:27017
MONGO_DATABASE=tractian
MONGO_COLLECTION=workorders
DATA_INBOUND_DIR=./data/inbound  
DATA_OUTBOUND_DIR=./data/outbound
```

### Configuração MongoDB Padrão
- **Database**: `tractian`
- **Collection**: `workorders`
- **Porta**: `27017`

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

## Logs e Monitoramento

### Estrutura de Logs (Loguru)
```bash
# Exemplo de execução bem-sucedida
2025-10-29 17:21:43 | INFO | main:main:49 - === Iniciando Pipeline de Integração TracOS ↔ Cliente ===
2025-10-29 17:21:43 | INFO | main:inbound_flow:13 - Iniciando fluxo inbound (Cliente → TracOS)
2025-10-29 17:21:43 | INFO | client_adapter:read_inbound_files:24 - Arquivo lido: 1.json
2025-10-29 17:21:43 | INFO | tracos_adapter:_upsert:88 - Workorder 1 atualizado
2025-10-29 17:21:43 | INFO | main:inbound_flow:25 - Fluxo inbound finalizado: 10 workorders processadas
2025-10-29 17:21:43 | INFO | main:outbound_flow:30 - Iniciando fluxo outbound (TracOS → Cliente)
2025-10-29 17:21:43 | INFO | client_adapter:write_outbound_file:44 - Arquivo escrito: workorder_1.json
2025-10-29 17:21:43 | INFO | tracos_adapter:_mark:114 - Workorder 1 marcada como sincronizada
2025-10-29 17:21:43 | INFO | main:main:54 - === Pipeline de Integração Finalizado ===
```

### Visualização de Logs
- **Durante testes**: Use `poetry run pytest -v -s` para ver logs em tempo real
- **Durante execução**: `poetry run python src/main.py` mostra logs automaticamente
- **Para debugging**: Logs incluem módulo, função e linha para rastreabilidade

### Tratamento de Erros

#### I/O Errors (Arquivos)
```bash
ERROR | JSON corrompido em arquivo.json: Expecting property name...
WARNING | Arquivo não encontrado: missing.json
ERROR | Sem permissão para ler arquivo: restricted.json
```

#### MongoDB Errors (Rede)
```bash
ERROR | Erro ao ler workorders após tentativas: Connection refused
INFO | Workorder 5 atualizado (após retry automático)
```

### Recursos de Resiliência
- **Retry MongoDB**: 3 tentativas com 1s delay para falhas temporárias
- **I/O Error Handling**: Tratamento específico para arquivos corrompidos/inacessíveis
- **Pipeline Resiliente**: Continua processando mesmo com arquivos problemáticos
- **Logs Informativos**: Sem stack traces confusos, mensagens claras

## Desenvolvimento

### Arquitetura para Extensibilidade
O sistema foi projetado para fácil adição de novos sistemas:

```python
# Novo adaptador para sistema XYZ
class XYZAdapter:
    def read_data(self): pass
    def write_data(self): pass

# Novo tradutor para formato XYZ  
def xyz_to_tracos(xyz_data): pass
def tracos_to_xyz(tracos_data): pass
```

### Padrões Utilizados
- **Adapter Pattern**: Isolamento entre sistemas diferentes
- **Retry Pattern**: Recuperação automática de falhas temporárias  
- **Configuration Pattern**: Configuração centralizada via variáveis ambiente
- **Pipeline Pattern**: Fluxo sequencial de processamento de dados

### Decisões Arquiteturais

#### Por que Async/Await?
- **MongoDB é I/O intensivo**: Operações de rede se beneficiam de não-bloqueio
- **Escalabilidade**: Permite processamento concorrente de workorders
- **Motor Driver**: Driver oficial assíncrono do MongoDB para Python

#### Por que Loguru em vez de logging padrão?
- **Sintaxe simples**: `logger.info()` vs configuração complexa do logging
- **Formatação automática**: Timestamp, cores e estrutura sem configuração
- **Performance**: Mais rápido que logging padrão do Python

#### Por que Separação de Tradutores?
- **Single Responsibility**: Cada função faz uma conversão específica  
- **Testabilidade**: Fácil validar mapeamentos individuais
- **Manutenibilidade**: Mudanças de formato isoladas em funções específicas

---

## Tecnologias Utilizadas

- **Python 3.11** - Linguagem principal
- **Poetry** - Gerenciamento de dependências
- **Motor** - Driver assíncrono MongoDB
- **Loguru** - Logging estruturado
- **MongoDB** - Banco de dados TracOS
- **Docker** - Containerização MongoDB
- **Pytest** - Framework de testes
- **JSON** - Formato de intercâmbio de dados

---

*Sistema desenvolvido seguindo requisitos de integração TracOS ↔ Cliente com foco em resiliência, observabilidade e extensibilidade.*