# 📊 Dashboard de Análise de Metais Pesados em Pólen (ICP-MS)

![Python](https://img.shields.io/badge/Python-3.8+-blue.svg)
![Streamlit](https://img.shields.io/badge/Streamlit-1.28+-red.svg)
![Pandas](https://img.shields.io/badge/Pandas-2.0+-green.svg)
![Status](https://img.shields.io/badge/Status-v2.7.0-success.svg)
![License](https://img.shields.io/badge/License-Internal-orange.svg)

**Automação Analítica para Setor Ambiental e Laboratorial**

Aplicação web interativa (Streamlit) para análise, visualização e geração de relatórios técnicos a partir de dados de espectrometria de massa com plasma indutivamente acoplado (ICP-MS) aplicados a grãos de pólen.

---

## 🎯 Funcionalidades

- ✅ **Ingestão Inteligente:** Processa planilhas Excel com cabeçalhos mesclados multinível
- ✅ **Padronização Automática:** Aplica mapeamento de metadados para normalizar nomenclaturas
- ✅ **Limpeza de Dados:** Trata valores não numéricos (< LOD, N.D.) preservando valores com flags
- ✅ **Filtros de Qualidade:** Remove registros rejeitados automaticamente
- ✅ **Controle de Acesso:** Sistema de autenticação com streamlit-authenticator
- ✅ **Dashboard Interativo:** Interface web com Streamlit para visualização de dados
- ✅ **Exportação:** Download de dados processados em Excel e CSV
- ✅ **Controle de Qualidade (QC):** Curva de calibração, Taxa de Recuperação (TR%) e flags ICPOES/RSD por leitura
- ✅ **Quantificação (µg/L → mg/kg):** FDT (FD1×FD2) por matriz (Pólen/MPA), TR% do NIST e tabela final (triplicata e média)
- ✅ **Deploy em produção:** Streamlit Community Cloud (SaaS multiusuário, CI/CD a partir do GitHub)
- 🚧 **Relatórios Técnicos:** Geração de laudo PDF conforme padrões ABNT (planejado)

---

## 📁 Estrutura do Projeto

```
AutomacaoResultadosMetaisPesados/
│
├── 📘 CONTEXTO_TECNICO.md        # Memória técnica do projeto (LEITURA OBRIGATÓRIA)
├── 📄 README.md                  # Este arquivo
├── 📦 requirements.txt           # Dependências Python
├── 🔒 .gitignore                 # Arquivos não versionados
│
├── 🚀 app.py                     # Aplicação Streamlit principal (4 abas)
├── 🔐 gerar_senhas_terminal.py   # Script auxiliar para gerar hashes de senha
│
├── 📊 original.xlsx              # Dados brutos ICP-MS (não versionado)
├── 📖 metadados.xlsx             # Dicionário de dados (mapeamento de colunas)
│
├── 📁 src/                       # Módulos de código
│   ├── __init__.py
│   ├── etl.py                    # Pipeline ETL + Motor de QC (QualityControlEngine)
│   ├── visuals.py                # Visualizações e métricas de QC (Plotly)
│   ├── dilution.py               # FD1/FD2/FDT por matriz + auto-detecção
│   ├── quantification.py         # Seleção, RSD, conversão mg/kg, média
│   └── reference_materials.py    # Certificados (NIST 1515) + TR%
│
└── 📁 .streamlit/                # Configurações Streamlit (não versionado)
    └── secrets.toml              # Credenciais (gerar com gerar_senhas_terminal.py)
```

---

## 🚀 Instalação e Configuração

### Pré-requisitos

- Python 3.8 ou superior
- pip (gerenciador de pacotes Python)

### 1. Clone o repositório (ou baixe os arquivos)

```bash
cd "g:\Meu Drive\BACKUP\SCRIPTS\AutomacaoResultadosMetaisPesados"
```

### 2. (Opcional) Crie um ambiente virtual

```powershell
# Windows PowerShell
python -m venv venv
.\venv\Scripts\Activate.ps1
```

```bash
# Linux/Mac
python3 -m venv venv
source venv/bin/activate
```

### 3. Instale as dependências

```bash
pip install -r requirements.txt
```

---

## 📊 Uso do Módulo ETL

### Exemplo Básico

```python
from src.etl import ICPMSDataProcessor

# Inicializar processador
processor = ICPMSDataProcessor(
    arquivo_original='original.xlsx',
    arquivo_metadados='metadados.xlsx'
)

# Executar pipeline completo
df_limpo = processor.processar()

# Visualizar resultado
print(f"✅ {len(df_limpo)} amostras processadas")
print(f"📊 {len(df_limpo.columns)} variáveis disponíveis")

# Exportar dados limpos
processor.exportar_processado('dados_limpos.xlsx')
processor.exportar_log('processamento.log')
```

### Uso Simplificado (Função Auxiliar)

```python
from src.etl import processar_dados_icpms

df, log = processar_dados_icpms(
    arquivo_original='original.xlsx',
    arquivo_metadados='metadados.xlsx',
    aplicar_filtro_rjct=True
)

print(df.head())
```

### Execução Standalone

```bash
python -m src.etl
```

---

## 🧪 Testando o ETL

Execute o script de teste para validar o processamento:

```bash
python test_etl.py
```

**Saída esperada:**
```
✅ TESTE CONCLUÍDO COM SUCESSO!
📊 Shape: (77, 106) (linhas × colunas)
✓ 77 amostras processadas
✓ 106 variáveis disponíveis
✓ 72.9% de completude dos dados
```

---

## 📖 Documentação Técnica

### Pipeline ETL

O módulo `src/etl.py` implementa o seguinte fluxo:

```
┌─────────────────┐
│ original.xlsx   │ (Dados brutos do equipamento ICP-MS)
└────────┬────────┘
         │
         ├──► 1. Leitura com header=[0,1] (cabeçalho multinível)
         ├──► 2. Combinação de níveis do cabeçalho
         ├──► 3. Sanitização (strip, lowercase)
         │
┌────────▼────────┐
│ metadados.xlsx  │ (Dicionário de dados)
└────────┬────────┘
         │
         ├──► 4. Criação de mapeamento (nome_original → nome_padronizado)
         ├──► 5. Aplicação do mapeamento
         ├──► 6. Filtro de registros rejeitados (Rjct = True)
         ├──► 7. Sanitização de valores analíticos (< LOD → NaN)
         ├──► 8. Conversão de tipos (datetime, float, string)
         │
         ▼
┌─────────────────┐
│  DataFrame      │ (Dados limpos e padronizados)
│  Processado     │
└─────────────────┘
```

### Estratégia para Cabeçalhos Mesclados

O arquivo `original.xlsx` possui estrutura multinível:
- **Linha 0:** Nome do elemento químico + modo de análise (ex: `27 Al [ No Gas ]`)
- **Linha 1:** Tipo de medida (ex: `Conc. [ ug/l ]`, `Conc. RSD`)

**Solução implementada:**
```python
# Pandas lê com MultiIndex
('27 Al [ No Gas ]', 'Conc. [ ug/l ]')  →  '27 Al [ No Gas ] Conc'
('27 Al [ No Gas ]', 'Conc. RSD')        →  '27 Al [ No Gas ] RSD'
('Sample', 'Rjct')                       →  'Rjct'
```

Veja detalhes completos em: [CONTEXTO_TECNICO.md](CONTEXTO_TECNICO.md#log-de-sessão)

---

## 🛡️ Diretrizes de Qualidade

### 1. Sanitização de Dados
- Todas as chaves de mapeamento usam `.strip()` e `.lower()`
- Garante matching robusto entre arquivos

### 2. Padrões ABNT (Brasil)
- Datas: formato `DD/MM/AAAA`
- Números: vírgula decimal (`,`) e ponto milhar (`.`)
- Interface em português do Brasil

### 3. Tratamento de Valores Não Numéricos

| Valor Original | Conversão | Uso |
|----------------|-----------|-----|
| `< LOD` | `NaN` | Permite cálculos estatísticos |
| `N.D.` | `NaN` | Indica não detectável |
| `BLD` | `NaN` | Below Limit of Detection |
| Célula vazia | `NaN` | Dado ausente |

**Estratégias de substituição (a implementar no dashboard):**
- **LOD/2:** Método EPA (conservador para análises de risco)
- **Zero:** Para cálculos de carga total
- **Manter NaN:** Para estatísticas robustas

---

## 🔐 Segurança

### Arquivos Protegidos (não versionados)

- ✅ `original.xlsx` - Dados brutos com informações sensíveis
- ✅ `.streamlit/secrets.toml` - Credenciais de acesso
- ✅ `.env` - Variáveis de ambiente
- ✅ `*.log` - Logs de processamento

### Configuração de Autenticação

**📌 OBRIGATÓRIO antes de executar a aplicação:**

#### Método 1: Script Automatizado (Recomendado)

```bash
python gerar_hashes.py
```

Siga as instruções na tela:
1. Digite senhas para os 3 perfis (admin, analista, pesquisador)
2. O script gera automaticamente a configuração completa
3. Copie o conteúdo gerado para `.streamlit/secrets.toml`
4. Delete o arquivo temporário `secrets_gerados.toml`

#### Método 2: Manual

```python
import streamlit_authenticator as stauth

# Gerar hashes
senhas = ['senha_admin', 'senha_analista', 'senha_pesquisador']
hashes = stauth.Hasher(senhas).generate()

for i, hash_senha in enumerate(hashes):
    print(f"Senha {i+1}: {hash_senha}")
```

Edite `.streamlit/secrets.toml` com os hashes gerados (veja template no arquivo).

---

## 🚀 Como Executar a Aplicação

### 1. Certifique-se de que os arquivos estão no lugar

```
✅ original.xlsx (raiz do projeto)
✅ metadados.xlsx (raiz do projeto)
✅ .streamlit/secrets.toml (configurado com senhas)
```

### 2. Execute o dashboard

```bash
streamlit run app.py
```

### 3. Acesse no navegador

O Streamlit abrirá automaticamente em: `http://localhost:8501`

### 4. Faça login

Use um dos usuários configurados no `secrets.toml`:
- **admin** / [sua_senha_admin]
- **analista** / [sua_senha_analista]
- **pesquisador** / [sua_senha_pesquisador]

### 5. Processe os dados

1. Na aba "📊 Dados Processados"
2. Clique em "🔄 Processar Dados"
3. Aguarde o processamento (barra de progresso)
4. Visualize as estatísticas e a tabela
5. Download dos dados processados (Excel ou CSV)

---

## 📚 Referências Normativas

- **ABNT NBR ISO/IEC 17025:** Requisitos gerais para competência de laboratórios
- **EPA Method 200.8:** Determinação de elementos-traço por ICP-MS
- **CONAMA 420/2009:** Valores orientadores de qualidade do solo
- **INMETRO DOQ-CGCRE-008:** Orientação sobre validação de métodos analíticos

---

## 🛠️ Desenvolvimento

### Roadmap

**✅ v0.2.0** - Módulo ETL Validado
- [x] Pipeline completo de processamento
- [x] Sanitização e normalização
- [x] Tratamento de valores < LOD com flags
- [x] Exportação de dados limpos

**✅ v1.3.0** - Infraestrutura e Segurança
- [x] Estrutura de pastas, autenticação, dashboard, proteção de dados, exportação

**✅ v2.4.2** - Motor de Controle de Qualidade (QC)
- [x] Curva de calibração (A/B) e Taxa de Recuperação (TR%) com padrões Merck
- [x] Flags ICPOES (acima da curva) e RSD por leitura; visão elemento-cêntrica

**✅ v2.6.0** - Deploy em Produção
- [x] Streamlit Community Cloud, CI/CD, gestão segura de credenciais (SaaS multiusuário)

**✅ v2.7.0** - Quantificação (µg/L → mg/kg) (ATUAL)
- [x] Seleção de espécies/modo, RSD (≤15% e ≤25%), tabela reduzida
- [x] FDT (FD1×FD2) por matriz (Pólen/MPA), multi-arquivo com auto-detecção
- [x] TR% do material de referência (NIST 1515) com red flag 90–110%
- [x] Conversão para mg/kg e tabela final (triplicata e média)

**🔮 v3.0.0** - Geração de Relatórios (PRÓXIMA)
- [ ] Exportação para PDF, templates ABNT, laudo com gráficos
- [ ] Matrizes adicionais (chaminé, mel) e demais materiais de referência

### Contribuindo

1. Leia o [CONTEXTO_TECNICO.md](CONTEXTO_TECNICO.md) completamente
2. Siga os **Princípios de Desenvolvimento** e **Diretrizes de Qualidade**
3. Documente todas as funções com docstrings
4. Atualize o log de sessão no CONTEXTO_TECNICO.md

---

## 🆘 Troubleshooting

### Erro: "FileNotFoundError: original.xlsx"

**Solução:** Certifique-se de que o arquivo `original.xlsx` está no diretório raiz do projeto.

### Erro: "Coluna 'Rjct' não encontrada"

**Solução:** Verifique se o arquivo `metadados.xlsx` contém o mapeamento correto para a coluna de rejeição.

### Dados com muitos NaN após processamento

**Comportamento esperado:** Valores `< LOD`, células vazias e strings não numéricas são convertidos para `NaN` intencionalmente. Isso permite análises estatísticas corretas.

---

## 📄 Licença

Este projeto é de uso interno para análises ambientais e laboratoriais.  
**Dados sensíveis não devem ser compartilhados externamente.**

---

## 👤 Contato

**Desenvolvedor:** Engenharia de Dados - Setor Ambiental  
**Data de Criação:** 28 de fevereiro de 2026  
**Última Atualização:** 08 de junho de 2026 - **v2.7.0 (Quantificação µg/L → mg/kg)**

---

## 📎 Links Úteis

- [Documentação Streamlit](https://docs.streamlit.io/)
- [Pandas User Guide](https://pandas.pydata.org/docs/user_guide/index.html)
- [Plotly Python](https://plotly.com/python/)
- [EPA Method 200.8](https://www.epa.gov/esam/epa-method-2008-determination-trace-elements-waters-and-wastes-inductively-coupled-plasma)

---

**⭐ Para começar, leia o [CONTEXTO_TECNICO.md](CONTEXTO_TECNICO.md) para entender o contexto completo do projeto!**
