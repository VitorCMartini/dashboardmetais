"""
🔬 Dashboard de Análise de Metais Pesados em Pólen - ICP-MS
==============================================================
Aplicação Streamlit para visualização e análise de dados analíticos

Versão: 2.5.0 (Dynamic File Ingestion)
Data: 1 de março de 2026
Linguagem: Python 3.8+

Módulos:
- src.etl: Pipeline ETL para processamento de dados ICP-MS
- streamlit_authenticator: Sistema de autenticação

Arquitetura:
1. Camada de Autenticação (Login)
2. Camada de Processamento (ETL)
3. Camada de Visualização (Dashboard)
4. Camada de Exportação (Relatórios)
"""

import streamlit as st
import streamlit_authenticator as stauth
import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from pathlib import Path
from datetime import datetime
from typing import Dict
import yaml
from yaml.loader import SafeLoader

# Importar módulo ETL próprio
from src.etl import ICPMSDataProcessor, processar_dados_icpms, QualityControlEngine

# Importar módulo de visualizações
from src.visuals import (
    criar_grafico_pizza_qc,
    calcular_comparativo_he_nogas,
    criar_grafico_curva_calibracao,
    classificar_amostras_laboratoriais,
    criar_grafico_distribuicao_amostras,
    calcular_porcentagem_lod,
    calcular_porcentagem_flags,
    calcular_metricas_validacao_amostras,
    calcular_desempenho_amostras_flags,
    criar_matriz_flags_por_leitura,
    criar_resumo_qc_por_elemento
)

# Importar módulos da etapa de Quantificação (µg/L → mg/kg)
from src import quantification, dilution, reference_materials


# ============================================
# CONFIGURAÇÃO DA PÁGINA
# ============================================

st.set_page_config(
    page_title="Dashboard ICP-MS | Metais Pesados em Pólen",
    page_icon="🔬",
    layout="wide",
    initial_sidebar_state="expanded",
    menu_items={
        'About': """
        **Dashboard de Análise ICP-MS**
        
        Sistema de visualização e análise de concentrações elementares
        em grãos de pólen por espectrometria de massa.
        
        Versão: 2.5.0
        """
    }
)


# ============================================
# ESTILOS CUSTOMIZADOS
# ============================================

st.markdown("""
<style>
    /* Título principal */
    .main-title {
        font-size: 2.5rem;
        font-weight: 700;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 0.5rem;
    }
    
    /* Subtítulo */
    .subtitle {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    
    /* Cards de estatística */
    .stat-card {
        background-color: #f0f2f6;
        padding: 1.5rem;
        border-radius: 10px;
        border-left: 5px solid #1f77b4;
        margin-bottom: 1rem;
    }
    
    .stat-value {
        font-size: 2rem;
        font-weight: 700;
        color: #1f77b4;
    }
    
    .stat-label {
        font-size: 0.9rem;
        color: #666;
        text-transform: uppercase;
    }
    
    /* Esconder elementos padrão do Streamlit */
    #MainMenu {visibility: hidden;}
    footer {visibility: hidden;}
    
    /* Melhorar aparência do login */
    .login-container {
        max-width: 400px;
        margin: 2rem auto;
        padding: 2rem;
        background-color: #f9f9f9;
        border-radius: 10px;
        box-shadow: 0 2px 10px rgba(0,0,0,0.1);
    }
</style>
""", unsafe_allow_html=True)


# ============================================
# CONFIGURAÇÃO DE AUTENTICAÇÃO
# ============================================

def configurar_autenticacao():
    """
    Configura o sistema de autenticação usando streamlit-authenticator.
    Lê credenciais do st.secrets e retorna o objeto authenticator.
    
    Returns:
        stauth.Authenticate: Objeto de autenticação configurado
    """
    try:
        # Converter secrets para formato dict
        config = {
            'credentials': st.secrets['credentials'].to_dict(),
            'cookie': st.secrets['cookie'].to_dict()
        }
        
        # Criar autenticador (sem preauthorized - removido na nova versão)
        authenticator = stauth.Authenticate(
            config['credentials'],
            config['cookie']['name'],
            config['cookie']['key'],
            config['cookie']['expiry_days']
        )
        
        return authenticator
    
    except Exception as e:
        st.error(f"❌ Erro ao configurar autenticação: {str(e)}")
        st.info("""
        ℹ️ **Instruções:**
        1. Certifique-se de que o arquivo `.streamlit/secrets.toml` existe
        2. Verifique se as credenciais estão configuradas corretamente
        3. Reinicie a aplicação após configurar os segredos
        """)
        st.stop()


# ============================================
# FUNÇÕES AUXILIARES
# ============================================

def exibir_tela_login():
    """Exibe a tela de login centralizada e estilizada."""
    st.markdown('<div class="login-container">', unsafe_allow_html=True)
    
    st.markdown("### 🔐 Acesso ao Sistema")
    st.markdown("---")
    st.info("👤 Entre com suas credenciais para acessar o dashboard")
    
    st.markdown('</div>', unsafe_allow_html=True)


def exibir_cabecalho(nome_usuario: str):
    """
    Exibe o cabeçalho do dashboard com informações do usuário.
    
    Args:
        nome_usuario (str): Nome do usuário autenticado
    """
    col1, col2, col3 = st.columns([2, 3, 2])
    
    with col1:
        st.image("https://img.icons8.com/color/96/000000/test-tube.png", width=80)
    
    with col2:
        st.markdown('<div class="main-title">🔬 Dashboard ICP-MS</div>', unsafe_allow_html=True)
        st.markdown('<div class="subtitle">Análise de Metais Pesados em Pólen</div>', unsafe_allow_html=True)
    
    with col3:
        st.markdown(f"**👤 Usuário:** {nome_usuario}")
        data_atual = datetime.now().strftime("%d/%m/%Y")
        st.markdown(f"**📅 Data:** {data_atual}")


def obter_caminhos_arquivos():
    """
    Retorna os caminhos dos arquivos de entrada.
    Apenas metadados é retornado, pois o arquivo original vem do upload.
    
    Returns:
        tuple: (caminho_original, caminho_metadados) - original é None por compatibilidade
    """
    base_dir = Path(__file__).parent
    
    # Caminho do arquivo de metadados (interno ao sistema)
    # Tentar primeiro em data/, depois na raiz
    arquivo_metadados = base_dir / "data" / "metadados.xlsx"
    if not arquivo_metadados.exists():
        arquivo_metadados = base_dir / "metadados.xlsx"
    
    return None, arquivo_metadados


def validar_arquivos_entrada(arquivo_metadados, arquivo_original=None):
    """
    Valida se os arquivos de entrada existem.
    
    Args:
        arquivo_metadados: Caminho do arquivo de metadados (obrigatório)
        arquivo_original: Caminho do arquivo original (opcional, para compatibilidade)
    
    Returns:
        bool: True se metadados existe, False caso contrário
    """
    erros = []
    
    if arquivo_original and not arquivo_original.exists():
        erros.append(f"📄 Arquivo `original.xlsx` não encontrado em: {arquivo_original}")
    
    if not arquivo_metadados.exists():
        erros.append(f"📄 Arquivo `metadados.xlsx` não encontrado em: {arquivo_metadados}")
    
    if erros:
        st.error("❌ **Arquivos de entrada não encontrados:**")
        for erro in erros:
            st.write(erro)
        
        st.info("""
        ℹ️ **Instruções:**
        - O arquivo `metadados.xlsx` deve estar na pasta `data/` ou na raiz do projeto
        - Este é um arquivo interno do sistema (regra de negócio do laboratório)
        - Reinicie a aplicação após corrigir
        """)
        return False
    
    return True


# ============================================
# DASHBOARD PRINCIPAL
# ============================================

def renderizar_dashboard(nome_usuario: str, username: str, authenticator):
    """
    Renderiza o dashboard principal após autenticação.
    
    Args:
        nome_usuario (str): Nome completo do usuário
        username (str): Username do usuário
        authenticator: Objeto de autenticação
    """
    # Cabeçalho
    exibir_cabecalho(nome_usuario)
    
    st.markdown("---")
    
    # Sidebar
    with st.sidebar:
        st.markdown("### ⚙️ Configurações")
        
        # Opção de processamento
        st.markdown("#### 📊 Processamento de Dados")
        aplicar_filtro = st.checkbox(
            "Filtrar amostras rejeitadas",
            value=True,
            help="Remove amostras marcadas como rejeitadas pelo equipamento",
            key="checkbox_filtrar_rejeitadas"
        )
        
        st.markdown("---")
        
        # Informações do sistema
        st.markdown("#### ℹ️ Informações")
        st.info(f"""
        **Versão:** 2.5.0  
        **Usuário:** {username}  
        **Sessão:** Ativa
        """)
        
        st.markdown("---")
        
        # Botão de logout
        authenticator.logout('Sair', 'sidebar', key='btn_logout_auth')
    
    # Conteúdo principal
    tab_dados, tab_analise, tab_quant, tab_relatorios = st.tabs([
        "📊 Dados Processados",
        "📈 Análises",
        "🧪 Quantificação (mg/kg)",
        "📄 Relatórios"
    ])

    with tab_dados:
        renderizar_tab_dados(aplicar_filtro)

    with tab_analise:
        renderizar_tab_analises()

    with tab_quant:
        renderizar_tab_quantificacao()

    with tab_relatorios:
        st.info("🚧 **Em Desenvolvimento** - Geração de relatórios técnicos será implementada na próxima fase")


def renderizar_tab_dados(aplicar_filtro: bool):
    """
    Renderiza a aba de dados processados.
    
    Args:
        aplicar_filtro (bool): Se deve filtrar amostras rejeitadas
    """
    st.markdown("### 📊 Processamento de Dados ICP-MS")
    
    # ============================================
    # SEÇÃO 1: UPLOAD DE ARQUIVO
    # ============================================
    
    st.markdown("#### 📤 Upload do Arquivo de Dados Analíticos")
    
    # Componente de upload
    arquivo_upload = st.file_uploader(
        "Selecione o arquivo de exportação do equipamento ICP-MS:",
        type=['xlsx', 'xls', 'csv'],
        help="Arraste o arquivo ou clique para selecionar",
        key="file_uploader_dados_brutos"
    )
    
    # Guia de Uso (Expander)
    with st.expander("ℹ️ Guia: Como estruturar o arquivo do equipamento?", expanded=False):
        st.markdown("""
        **📋 Formato Esperado do Arquivo**
        
        O sistema espera um arquivo Excel com cabeçalho multinível (2 linhas):
        - **Linha 1:** Nomes dos elementos químicos (ex: '27 Al [ No Gas ]', '137 Ba [ He ]')
        - **Linha 2:** Tipos de medida (ex: 'Conc. [ ug/l ]', 'RSD [ % ]')
        """)
        
        # Exibir imagem de exemplo
        try:
            st.image(
                "cabecalho.png",
                caption="Exemplo de formato esperado do cabeçalho",
                use_container_width=True
            )
        except:
            st.warning("⚠️ Imagem de exemplo não encontrada (cabecalho.png)")
        
        st.markdown("---")
        st.markdown("**📖 Dicionário de Variáveis**")
        st.caption("Seu arquivo deve conter exatamente estes nomes na primeira linha para que o sistema os reconheça:")
        
        # Carregar e exibir metadados
        try:
            base_dir = Path(__file__).parent
            arquivo_metadados = base_dir / "data" / "metadados.xlsx"
            
            # Verificar se existe em data/, senão tentar na raiz
            if not arquivo_metadados.exists():
                arquivo_metadados = base_dir / "metadados.xlsx"
            
            if arquivo_metadados.exists():
                df_metadados = pd.read_excel(arquivo_metadados)
                
                # Filtrar apenas colunas relevantes
                if 'Nome Original na Planilha' in df_metadados.columns and 'Descrição' in df_metadados.columns:
                    df_display = df_metadados[['Nome Original na Planilha', 'Descrição']].copy()
                    df_display = df_display.dropna(subset=['Nome Original na Planilha'])
                    
                    st.dataframe(
                        df_display,
                        use_container_width=True,
                        hide_index=True,
                        height=300
                    )
                else:
                    st.dataframe(df_metadados, use_container_width=True, hide_index=True, height=300)
            else:
                st.warning("⚠️ Arquivo de metadados não encontrado")
        except Exception as e:
            st.error(f"❌ Erro ao carregar metadados: {str(e)}")
    
    st.markdown("---")
    
    # ============================================
    # SEÇÃO 2: PROCESSAMENTO (Somente após upload)
    # ============================================
    
    # Verificar se arquivo foi carregado
    if arquivo_upload is None:
        st.info("📥 **Aguardando o upload do arquivo de dados analíticos para iniciar o processamento.**")
        st.caption("👆 Faça o upload do arquivo na seção acima para ativar o processamento")
        return
    
    # Arquivo foi carregado - Liberar interface
    st.success(f"✅ Arquivo carregado: **{arquivo_upload.name}** ({arquivo_upload.size / 1024:.1f} KB)")
    
    # Validar arquivo de metadados (interno)
    arquivo_original, arquivo_metadados = obter_caminhos_arquivos()
    
    if not validar_arquivos_entrada(arquivo_metadados=arquivo_metadados):
        return
    
    # Botão de processamento
    if st.button("🔄 Processar Dados", type="primary", use_container_width=True, key="btn_processar_dados"):
        processar_e_exibir_dados(arquivo_upload, arquivo_metadados, aplicar_filtro)
    
    # Exibir dados em cache se existirem (apenas se NÃO clicou no botão)
    elif 'df_com_qc' in st.session_state:
        exibir_dados_processados(
            st.session_state['df_com_qc'], 
            st.session_state.get('resultados_qc', None)
        )


def processar_e_exibir_dados(arquivo_upload, arquivo_metadados, aplicar_filtro):
    """
    Processa os dados usando o módulo ETL e exibe resultados.
    
    Args:
        arquivo_upload: Objeto UploadedFile do Streamlit (arquivo em memória)
        arquivo_metadados: Caminho do arquivo de metadados
        aplicar_filtro (bool): Se deve filtrar rejeitadas
    """
    try:
        with st.spinner("🔄 Processando dados ICP-MS..."):
            # Criar processador com arquivo em memória
            processor = ICPMSDataProcessor(
                arquivo_upload,  # Passar objeto UploadedFile diretamente
                str(arquivo_metadados)
            )
            
            # Processar dados
            df_processado = processor.processar(aplicar_filtro_rjct=aplicar_filtro)
            
            # Salvar em session state
            st.session_state['df_processado'] = df_processado
            st.session_state['processor'] = processor
        
        # Executar Controle de Qualidade (QC)
        with st.spinner("🔬 Executando Controle de Qualidade (QC)..."):
            qc_engine = QualityControlEngine(df_processado)
            df_com_qc, resultados_qc = qc_engine.executar_qc_completo()
            
            # Salvar resultados QC em session state
            st.session_state['df_com_qc'] = df_com_qc
            st.session_state['resultados_qc'] = resultados_qc
            st.session_state['qc_engine'] = qc_engine
        
        # Feedback de sucesso
        st.success(f"✅ Processamento e QC concluídos! {len(df_com_qc)} amostras carregadas.")
        
        # Exibir dados com QC
        exibir_dados_processados(df_com_qc, resultados_qc)
    
    except Exception as e:
        st.error(f"❌ Erro durante o processamento: {str(e)}")
        st.exception(e)


def exibir_dados_processados(df: pd.DataFrame, resultados_qc: Dict = None):
    """
    Exibe os dados processados com estatísticas e visualização.
    
    Args:
        df (pd.DataFrame): DataFrame processado
        resultados_qc (Dict): Resultados do Controle de Qualidade (opcional)
    """
    st.markdown("---")
    
    # ============================================
    # SEÇÃO 1: ESTATÍSTICAS DO DATASET (Dashboard Executivo)
    # ============================================
    
    st.markdown("### 📊 Estatísticas do Dataset")
    
    # Calcular classificação e estatísticas
    df_contagem, estatisticas_detalhadas = classificar_amostras_laboratoriais(df)
    
    # KPIs Principais (Topo da seção)
    col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
    
    with col_kpi1:
        # Total de Amostras de Interesse Únicas
        amostras_interesse = estatisticas_detalhadas.get('Amostra de Interesse', {})
        n_amostras_unicas = amostras_interesse.get('amostras_unicas', 0)
        n_leituras_interesse = amostras_interesse.get('leituras_totais', 0)
        
        st.metric(
            label="🎯 Amostras de Interesse",
            value=f"{n_amostras_unicas} únicas",
            delta=f"{n_leituras_interesse} leituras",
            help="Amostras principais do lote (triplicatas contadas como 1)"
        )
    
    with col_kpi2:
        # Total de Leituras no Lote
        total_leituras = len(df[df['Tipo_Amostra'] == 'Sample'])
        
        st.metric(
            label="📋 Total de Leituras",
            value=f"{total_leituras}",
            help="Soma de todas as linhas de amostras do lote (incluindo réplicas)"
        )
    
    with col_kpi3:
        # Valores < LOD
        pct_lod = calcular_porcentagem_lod(df)
        colunas_flag_lod = [col for col in df.columns if 'Flag_LOD' in col]
        total_lod_absolute = int(df[colunas_flag_lod].sum().sum()) if colunas_flag_lod else 0
        
        # Calcular total de células de dados analíticos
        colunas_concentracao = [col.replace('_Flag_LOD', '') for col in colunas_flag_lod]
        colunas_concentracao = [col for col in colunas_concentracao if col in df.columns]
        
        if len(colunas_concentracao) > 0:
            total_celulas_esperadas = len(df) * len(colunas_concentracao)
            info_celulas = f"{total_lod_absolute} / {total_celulas_esperadas}"
        else:
            info_celulas = f"{total_lod_absolute}"
        
        st.metric(
            label="🔬 Valores < LOD",
            value=f"{pct_lod:.1f}%",
            delta=info_celulas,
            delta_color="off",
            help="Porcentagem de valores abaixo do limite de detecção (INFORMATIVO - não invalida amostra)"
        )
    
    # Nota explicativa sobre flags
    st.info("""
    ℹ️ **Classificação de Flags:**  
    • **< LOD** (Informativo): Valores abaixo do limite de detecção são NORMAIS em análises ambientais e NÃO invalidam a amostra.  
    • **ICPOES/RSD** (Críticos): Apenas estas flags invalidam amostras (concentração fora da curva ou variação excessiva).
    """)
    
    st.markdown("---")
    
    # Visualização de Distribuição + Tabela de Detalhamento
    if len(df_contagem) > 0:
        col_grafico, col_tabela = st.columns([3, 2])
        
        with col_grafico:
            st.markdown("**📊 Distribuição de Classes de Amostras no Lote**")
            fig_donut = criar_grafico_distribuicao_amostras(df_contagem)
            
            if fig_donut:
                st.plotly_chart(fig_donut, use_container_width=True)
            else:
                st.warning("⚠️ Não foi possível gerar o gráfico de distribuição.")
        
        with col_tabela:
            st.markdown("**📋 Detalhamento por Classe**")
            
            # Preparar DataFrame para exibição
            df_display = df_contagem[['Classe', 'Regra de Contagem', 'Valor', 'Leituras Totais']].copy()
            
            # Renomear colunas para exibição
            df_display.columns = ['Classe', 'Regra', 'Valor', 'Leituras']
            
            st.dataframe(
                df_display,
                use_container_width=True,
                hide_index=True,
                height=350
            )
    else:
        st.info("ℹ️ Nenhuma amostra classificada encontrada.")
    
    st.markdown("---")
    
    # ============================================
    # SEÇÃO 2: PIPELINE DE CONTROLE DE QUALIDADE (QC)
    # ============================================
    
    if resultados_qc:
        st.markdown("### 🔬 Pipeline de Controle de Qualidade (QC)")
        st.caption("Validação hierárquica: Elementos → Amostras → Dados Finais")
        
        # ============================================
        # ETAPA 1: VALIDAÇÃO INSTRUMENTAL (ENSAIOS ANALÍTICOS)
        # ============================================
        
        st.markdown("#### 1️⃣ Validação Instrumental (Ensaios Analíticos)")
        st.caption("Avaliação da Taxa de Recuperação (TR%) para cada ensaio analítico (elemento + modo de ionização)")
        
        col_etapa1_grafico, col_etapa1_info = st.columns([2, 1])
        
        with col_etapa1_grafico:
            fig_pizza = criar_grafico_pizza_qc(resultados_qc)
            st.plotly_chart(fig_pizza, use_container_width=True)
        
        with col_etapa1_info:
            n_aprovados = len(resultados_qc.get('elementos_aprovados', []))
            n_reprovados = len(resultados_qc.get('elementos_reprovados', []))
            total_elementos = n_aprovados + n_reprovados
            pct_aprovacao = (n_aprovados / total_elementos * 100) if total_elementos > 0 else 0
            
            st.metric(
                label="✅ Taxa de Aprovação",
                value=f"{pct_aprovacao:.1f}%",
                delta=f"{n_aprovados} de {total_elementos} ensaios",
                help="Ensaios analíticos aprovados no teste de Taxa de Recuperação (TR%)"
            )
            
            if n_reprovados > 0:
                elementos_reprovados = resultados_qc.get('elementos_reprovados', [])
                with st.expander("⚠️ Ver ensaios reprovados"):
                    for elem in elementos_reprovados:
                        st.text(f"• {elem}")
        
        # Comparativo de gases (informação secundária)
        with st.expander("ℹ️ Ver Desempenho de Gases (He vs NoGas)"):
            st.markdown("**Comparativo de Desempenho: Hélio vs Sem Gás**")
            st.caption("Análise secundária: Qual modo de ionização apresentou melhor TR% para elementos que possuem ambas leituras")
            
            comparativo = calcular_comparativo_he_nogas(resultados_qc, df)
            
            col_he, col_nogas, col_empate = st.columns(3)
            
            with col_he:
                st.metric(
                    label="🔵 Melhor com Hélio",
                    value=f"{comparativo['melhor_he']} ensaios"
                )
            
            with col_nogas:
                st.metric(
                    label="⚪ Melhor Sem Gás",
                    value=f"{comparativo['melhor_nogas']} ensaios"
                )
            
            with col_empate:
                st.metric(
                    label="🤝 Empates",
                    value=f"{comparativo['empates']} ensaios"
                )
            
            if len(comparativo['detalhes']) > 0:
                st.markdown("**Detalhes por Elemento:**")
                df_comparativo = pd.DataFrame(comparativo['detalhes'])
                df_comparativo = df_comparativo[['elemento_base', 'tr_he', 'tr_nogas', 'vencedor']]
                df_comparativo.columns = ['Elemento', 'TR% He', 'TR% NoGas', 'Vencedor']
                df_comparativo['TR% He'] = df_comparativo['TR% He'].apply(lambda x: f"{x:.1f}%")
                df_comparativo['TR% NoGas'] = df_comparativo['TR% NoGas'].apply(lambda x: f"{x:.1f}%")
                st.dataframe(df_comparativo, use_container_width=True, hide_index=True)
        
        st.divider()
        
        # ============================================
        # ETAPA 2: VALIDAÇÃO ANALÍTICA (VISÃO ELEMENTO-CÊNCRICA)
        # ============================================
        
        st.markdown("#### 2️⃣ Validação Analítica (Análise por Elemento Químico)")
        st.caption("🧪 Visão centrada no ELEMENTO • Considera apenas elementos aprovados na Etapa 1")
        
        # Criar resumo por elemento
        df_resumo_elementos, metricas_resumo = criar_resumo_qc_por_elemento(df, resultados_qc)
        
        # Mostrar universo de cálculo
        if metricas_resumo['universo_total'] > 0:
            st.info(f"""
            📊 **Universo de Avaliação:** {metricas_resumo['universo_total']} leituras possíveis  
            ({metricas_resumo['total_linhas']} linhas de amostras × {metricas_resumo['total_elementos_aprovados']} elementos aprovados)  
            🧑‍🔬 Contexto: {metricas_resumo['total_amostras_unicas']} amostras únicas de interesse
            """)
        
        # KPIs de Resumo (Topo)
        col_kpi1, col_kpi2, col_kpi3 = st.columns(3)
        
        with col_kpi1:
            pct_aprovadas = (metricas_resumo['leituras_aprovadas'] / metricas_resumo['universo_total'] * 100) if metricas_resumo['universo_total'] > 0 else 0
            st.metric(
                label="✅ Leituras Aprovadas",
                value=f"{metricas_resumo['leituras_aprovadas']}",
                delta=f"{pct_aprovadas:.1f}% do universo",
                delta_color="normal",
                help="Total de leituras (linhas) sem flags ICPOES e sem flags RSD em todos os elementos"
            )
        
        with col_kpi2:
            st.metric(
                label="⚠️ Leituras com FLAG ICPOES",
                value=f"{metricas_resumo['leituras_icpoes']}",
                delta="Acima da curva",
                delta_color="off",
                help="Total de leituras com concentração acima do limite da curva de calibração"
            )
        
        with col_kpi3:
            st.metric(
                label="⚠️ Leituras com FLAG RSD",
                value=f"{metricas_resumo['leituras_rsd']}",
                delta="RSD elevado",
                delta_color="off",
                help="Total de leituras com desvio padrão relativo acima do tolerado"
            )
        
        st.markdown("")
        
        # Tabela de Resumo por Elemento
        if len(df_resumo_elementos) > 0:
            st.markdown("**🧪 Resumo de Qualidade por Elemento Químico**")
            st.caption("🔍 Cada linha = 1 elemento • Valores = leituras aprovadas/reprovadas para aquele metal")
            
            # Preparar DataFrame para exibição com barra de progresso
            df_display = df_resumo_elementos[[
                'Elemento', 
                'Amostras_Unicas', 
                'Leituras_Aprovadas', 
                'Flags_ICPOES', 
                'Flags_RSD',
                'Pct_Aprovadas'
            ]].copy()
            
            # Renomear colunas
            df_display.columns = [
                'Elemento', 
                'Amostras Únicas', 
                'Leituras Aprovadas', 
                'Flags ICPOES', 
                'Flags RSD',
                '% Aprovadas'
            ]
            
            # Ordenar por % Aprovadas (decrescente) para mostrar melhores primeiro
            df_display = df_display.sort_values('% Aprovadas', ascending=False)
            
            # Configurar exibição com barra de progresso
            st.dataframe(
                df_display,
                use_container_width=True,
                height=400,
                hide_index=True,
                column_config={
                    'Elemento': st.column_config.TextColumn(
                        'Elemento Químico',
                        help="Elemento aprovado na Etapa 1 (TR%)",
                        width="medium"
                    ),
                    'Amostras Únicas': st.column_config.NumberColumn(
                        'Amostras Únicas',
                        help="Número de amostras de interesse únicas avaliadas",
                        format="%d"
                    ),
                    'Leituras Aprovadas': st.column_config.NumberColumn(
                        'Leituras Aprovadas',
                        help="Número de linhas (leituras) sem flags críticas",
                        format="%d"
                    ),
                    'Flags ICPOES': st.column_config.NumberColumn(
                        'Flags ICPOES',
                        help="Leituras com concentração acima da curva",
                        format="%d"
                    ),
                    'Flags RSD': st.column_config.NumberColumn(
                        'Flags RSD',
                        help="Leituras com desvio padrão elevado",
                        format="%d"
                    ),
                    '% Aprovadas': st.column_config.ProgressColumn(
                        '% Aprovadas',
                        help="Porcentagem de leituras aprovadas para este elemento",
                        format="%.1f%%",
                        min_value=0,
                        max_value=100
                    )
                }
            )
            
            # Legenda
            st.caption("""
            🟢 **Barra de Progresso (% Aprovadas):** Quanto mais próxima de 100%, melhor o desempenho do elemento • 
            🔴 **Flags ICPOES/RSD:** Leituras que precisam correção (diluição ou repetição)
            """)
        else:
            st.info("ℹ️ Nenhum elemento encontrado para análise.")
        
        st.markdown("---")
        
        # ============================================
        # SEÇÃO 3: VISUALIZAÇÃO DAS CURVAS DE CALIBRAÇÃO
        # ============================================
        
        st.markdown("### 📉 Visualização das Curvas de Calibração")
        
        elementos_aprovados = resultados_qc.get('elementos_aprovados', [])
        
        if len(elementos_aprovados) > 0:
            col_select, col_grafico = st.columns([1, 3])
            
            with col_select:
                elemento_selecionado = st.selectbox(
                    "Selecione um elemento aprovado:",
                    options=elementos_aprovados,
                    key="selectbox_curva_calibracao"
                )
            
            with col_grafico:
                if elemento_selecionado:
                    curvas_info = resultados_qc.get('curvas', {})
                    curva_elemento = curvas_info.get(elemento_selecionado)
                    
                    if curva_elemento:
                        fig_curva = criar_grafico_curva_calibracao(
                            elemento_selecionado,
                            df,
                            curva_elemento
                        )
                        
                        if fig_curva:
                            st.plotly_chart(fig_curva, use_container_width=True)
                        else:
                            st.warning("⚠️ Não foi possível gerar o gráfico da curva.")
                    else:
                        st.warning("⚠️ Informações de curva não disponíveis para este elemento.")
        else:
            st.info("ℹ️ Nenhum elemento aprovado no QC disponível para visualização de curvas.")
        
        st.markdown("---")
    
    # Visualização da tabela
    st.markdown("### 📋 Dados Processados")
    
    # Filtro de colunas
    col_filtro1, col_filtro2 = st.columns(2)
    
    with col_filtro1:
        tipo_colunas = st.multiselect(
            "🔍 Filtrar por tipo de coluna:",
            ["Concentrações", "RSD", "Flags LOD", "Flags de Qualidade (ICPOES/RSD)", "Metadados"],
            default=["Concentrações", "Metadados"],
            key="filtro_tipo_colunas"
        )
    
    # Aplicar filtro de colunas
    colunas_exibir = []
    
    # Sempre incluir colunas de identificação
    colunas_id = ['Nome_Amostra', 'Arquivo_Dados', 'Data_Hora_Aquisicao']
    colunas_exibir.extend([col for col in colunas_id if col in df.columns])
    
    if "Concentrações" in tipo_colunas:
        colunas_exibir.extend([col for col in df.columns if '_Conc' in col and 'Flag' not in col])
    
    if "RSD" in tipo_colunas:
        colunas_exibir.extend([col for col in df.columns if '_RSD' in col])
    
    if "Flags LOD" in tipo_colunas:
        colunas_exibir.extend([col for col in df.columns if 'Flag_LOD' in col])
    
    if "Flags de Qualidade (ICPOES/RSD)" in tipo_colunas:
        colunas_exibir.extend([col for col in df.columns if 'Flag_ICPOES' in col or 'Flag_RSD' in col])
    
    if "Metadados" in tipo_colunas:
        colunas_meta = [col for col in df.columns if col not in colunas_exibir and '_Conc' not in col and '_RSD' not in col and 'Flag' not in col]
        colunas_exibir.extend(colunas_meta)
    
    # Remover duplicatas mantendo ordem
    colunas_exibir = list(dict.fromkeys(colunas_exibir))
    
    # Exibir DataFrame
    df_exibir = df[colunas_exibir]
    
    st.dataframe(
        df_exibir,
        use_container_width=True,
        height=400
    )
    
    # Botão de download
    st.markdown("---")
    st.markdown("### 💾 Exportar Dados")
    
    col_down1, col_down2 = st.columns(2)
    
    with col_down1:
        # Download como Excel
        from io import BytesIO
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine='openpyxl') as writer:
            df.to_excel(writer, index=False, sheet_name='Dados Processados')
        buffer.seek(0)
        
        st.download_button(
            label="📥 Download Excel",
            data=buffer,
            file_name=f"dados_processados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True,
            key="btn_download_excel"
        )
    
    with col_down2:
        # Download como CSV
        csv = df.to_csv(index=False).encode('utf-8-sig')  # utf-8-sig para Excel brasileiro
        
        st.download_button(
            label="📥 Download CSV",
            data=csv,
            file_name=f"dados_processados_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="btn_download_csv"
        )


def renderizar_tab_analises():
    """
    Renderiza a Tab 2 (Análises) com filtros, gráficos e estatísticas.
    """
    st.markdown("### 📈 Análises de Qualidade")
    
    # Verificar se dados estão disponíveis
    if 'df_com_qc' not in st.session_state:
        st.warning("⚠️ Nenhum dado processado disponível. Por favor, processe os dados na aba 'Dados Processados' primeiro.")
        return
    
    df = st.session_state['df_com_qc']
    resultados_qc = st.session_state.get('resultados_qc', None)
    
    # Verificar se existem resultados de QC
    if not resultados_qc:
        st.warning("⚠️ Controle de Qualidade não foi executado. Por favor, reprocesse os dados.")
        return
    
    # Obter elementos aprovados no QC
    elementos_aprovados = resultados_qc.get('elementos_aprovados', [])
    
    if len(elementos_aprovados) == 0:
        st.warning("⚠️ Nenhum elemento foi aprovado no Controle de Qualidade (TR%).")
        return
    
    st.markdown("---")
    
    # Filtro lateral (Sidebar)
    with st.sidebar:
        st.markdown("### 🔍 Filtros de Análise")
        st.markdown("#### Elementos Químicos")
        
        # Multiselect para escolher elementos
        elementos_selecionados = st.multiselect(
            "Selecione os elementos para análise:",
            options=elementos_aprovados,
            default=elementos_aprovados[:3] if len(elementos_aprovados) >= 3 else elementos_aprovados,
            help="Apenas elementos aprovados no Controle de Qualidade (TR%)",
            key="multiselect_elementos_analise"
        )
        
        st.markdown("---")
        st.markdown("#### Filtros de Qualidade")
        
        excluir_flags_icpoes = st.checkbox(
            "Excluir amostras com Flag ICPOES",
            value=True,
            help="Remove amostras com concentração acima da curva de calibração",
            key="checkbox_excluir_icpoes"
        )
        
        excluir_flags_rsd = st.checkbox(
            "Excluir amostras com Flag RSD",
            value=True,
            help="Remove amostras com RSD acima do tolerado",
            key="checkbox_excluir_rsd"
        )
    
    # Verificar se algum elemento foi selecionado
    if len(elementos_selecionados) == 0:
        st.info("ℹ️ Selecione pelo menos um elemento na barra lateral para visualizar as análises.")
        return
    
    # Filtrar DataFrame: apenas amostras reais (Sample) sem flags
    df_analise = df[df['Tipo_Amostra'] == 'Sample'].copy()
    
    if len(df_analise) == 0:
        st.warning("⚠️ Nenhuma amostra real (Sample) encontrada nos dados.")
        return
    
    # Aplicar filtros de flags
    n_total = len(df_analise)
    n_excluidos = 0
    
    for elemento in elementos_selecionados:
        col_flag_icpoes = f"{elemento}_Flag_ICPOES"
        col_flag_rsd = f"{elemento}_Flag_RSD"
        
        # Excluir amostras com flag ICPOES
        if excluir_flags_icpoes and col_flag_icpoes in df_analise.columns:
            mask_icpoes = df_analise[col_flag_icpoes] == False
            n_excluidos += (~mask_icpoes).sum()
            df_analise = df_analise[mask_icpoes]
        
        # Excluir amostras com flag RSD
        if excluir_flags_rsd and col_flag_rsd in df_analise.columns:
            mask_rsd = df_analise[col_flag_rsd] == False
            n_excluidos += (~mask_rsd).sum()
            df_analise = df_analise[mask_rsd]
    
    st.info(f"📊 Análise com {len(df_analise)} amostras (excluídas {n_excluidos} por flags de qualidade)")
    
    st.markdown("---")
    
    # ============================================
    # GRÁFICO 1: Barras - Comparação de Concentrações
    # ============================================
    
    st.markdown("### 📊 Comparação de Concentrações por Amostra")
    
    # Preparar dados para gráfico de barras
    # Criar DataFrame long format para Plotly
    dados_grafico = []
    
    for elemento in elementos_selecionados:
        col_conc = f"{elemento}_Conc"
        
        if col_conc in df_analise.columns:
            for idx, row in df_analise.iterrows():
                dados_grafico.append({
                    'Amostra': row.get('Nome_Amostra', f'Amostra_{idx}'),
                    'Elemento': elemento,
                    'Concentração': row[col_conc]
                })
    
    df_grafico_barras = pd.DataFrame(dados_grafico)
    
    if len(df_grafico_barras) > 0:
        # Criar gráfico de barras agrupadas
        fig_barras = px.bar(
            df_grafico_barras,
            x='Amostra',
            y='Concentração',
            color='Elemento',
            barmode='group',
            title='Concentrações Elementares por Amostra',
            labels={'Concentração': 'Concentração (µg/L)', 'Amostra': 'Nome da Amostra'},
            template='plotly_white',
            height=500
        )
        
        fig_barras.update_layout(
            xaxis_tickangle=-45,
            legend=dict(
                orientation="h",
                yanchor="bottom",
                y=1.02,
                xanchor="right",
                x=1
            )
        )
        
        st.plotly_chart(fig_barras, use_container_width=True)
    else:
        st.warning("⚠️ Nenhum dado disponível para gráfico de barras.")
    
    st.markdown("---")
    
    # ============================================
    # GRÁFICO 2: Linhas - Monitoramento ISTD
    # ============================================
    
    st.markdown("### 📉 Monitoramento de Padrões Internos (ISTD)")
    
    # Identificar colunas ISTD
    colunas_istd = [col for col in df.columns if col.startswith('ISTD_') and '_Conc' in col]
    
    if len(colunas_istd) > 0:
        # Filtrar apenas amostras reais
        df_istd = df[df['Tipo_Amostra'] == 'Sample'].copy()
        
        # Preparar dados para gráfico de linhas
        dados_istd = []
        
        for idx, row in df_istd.iterrows():
            amostra_nome = row.get('Nome_Amostra', f'Amostra_{idx}')
            
            for col_istd in colunas_istd:
                istd_nome = col_istd.replace('_Conc', '').replace('ISTD_', '')
                dados_istd.append({
                    'Amostra': amostra_nome,
                    'ISTD': istd_nome,
                    'Concentração': row[col_istd],
                    'Ordem': idx  # Para manter ordem correta
                })
        
        df_grafico_istd = pd.DataFrame(dados_istd)
        
        if len(df_grafico_istd) > 0:
            # Criar gráfico de linhas
            fig_linhas = px.line(
                df_grafico_istd.sort_values('Ordem'),
                x='Amostra',
                y='Concentração',
                color='ISTD',
                markers=True,
                title='Estabilidade dos Padrões Internos (ISTD)',
                labels={'Concentração': 'Concentração (µg/L)', 'Amostra': 'Sequência de Amostras'},
                template='plotly_white',
                height=400
            )
            
            fig_linhas.update_layout(
                xaxis_tickangle=-45,
                legend=dict(
                    orientation="h",
                    yanchor="bottom",
                    y=1.02,
                    xanchor="right",
                    x=1
                )
            )
            
            st.plotly_chart(fig_linhas, use_container_width=True)
            
            st.info("💡 **Interpretação:** A linha dos ISTD deve permanecer relativamente estável ao longo da sequência analítica. Grandes variações podem indicar problemas instrumentais.")
        else:
            st.warning("⚠️ Nenhum dado de ISTD disponível para o gráfico.")
    else:
        st.info("ℹ️ Nenhuma coluna de Padrão Interno (ISTD) encontrada nos dados.")
    
    st.markdown("---")
    
    # ============================================
    # TABELA: Estatísticas Descritivas
    # ============================================
    
    st.markdown("### 📋 Estatísticas Descritivas dos Elementos Selecionados")
    
    # Calcular estatísticas apenas para elementos selecionados
    estatisticas = []
    
    for elemento in elementos_selecionados:
        col_conc = f"{elemento}_Conc"
        
        if col_conc in df_analise.columns:
            serie = df_analise[col_conc].dropna()
            
            if len(serie) > 0:
                estatisticas.append({
                    'Elemento': elemento,
                    'Média': serie.mean(),
                    'Desvio Padrão': serie.std(),
                    'Mínimo': serie.min(),
                    'Máximo': serie.max(),
                    'Mediana': serie.median(),
                    'N Amostras': len(serie)
                })
    
    if len(estatisticas) > 0:
        df_estatisticas = pd.DataFrame(estatisticas)
        
        # Formatar números
        df_estatisticas['Média'] = df_estatisticas['Média'].apply(lambda x: f"{x:.4f}")
        df_estatisticas['Desvio Padrão'] = df_estatisticas['Desvio Padrão'].apply(lambda x: f"{x:.4f}")
        df_estatisticas['Mínimo'] = df_estatisticas['Mínimo'].apply(lambda x: f"{x:.4f}")
        df_estatisticas['Máximo'] = df_estatisticas['Máximo'].apply(lambda x: f"{x:.4f}")
        df_estatisticas['Mediana'] = df_estatisticas['Mediana'].apply(lambda x: f"{x:.4f}")
        
        st.dataframe(
            df_estatisticas,
            use_container_width=True,
            hide_index=True
        )
        
        # Botão de download
        st.markdown("---")
        st.markdown("### 💾 Exportar Análises")
        
        csv_estatisticas = df_estatisticas.to_csv(index=False).encode('utf-8-sig')
        
        st.download_button(
            label="📥 Download Estatísticas (CSV)",
            data=csv_estatisticas,
            file_name=f"estatisticas_elementos_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv",
            mime="text/csv",
            use_container_width=True,
            key="btn_download_estatisticas"
        )
    else:
        st.warning("⚠️ Nenhuma estatística disponível para os elementos selecionados.")


# ============================================
# TAB 3 - QUANTIFICAÇÃO (µg/L → mg/kg)
# ============================================

def renderizar_tab_quantificacao():
    """
    Etapa de quantificação: a partir dos dados validados pelo QC, aplica RSD,
    calcula o FDT (massas), verifica TR% do NIST e converte para mg/kg,
    gerando a tabela final por amostra (triplicata e média).
    """
    st.markdown("### 🧪 Quantificação: µg/L → mg/kg (FDT, TR% e Resultado Final)")

    if 'df_com_qc' not in st.session_state:
        st.warning("⚠️ Processe os dados na aba '📊 Dados Processados' primeiro.")
        return

    df = st.session_state['df_com_qc']
    resultados_qc = st.session_state.get('resultados_qc')

    sub1, sub2, sub3, sub4 = st.tabs([
        "1️⃣ Seleção & RSD",
        "2️⃣ Diluição (FDT)",
        "3️⃣ TR% (NIST)",
        "4️⃣ Resultado mg/kg",
    ])

    with sub1:
        _quant_sub_selecao_rsd(df, resultados_qc)
    with sub2:
        _quant_sub_fdt(df)
    with sub3:
        _quant_sub_tr(df)
    with sub4:
        _quant_sub_resultado(df)


def _mostrar_tabela_destacada(tabela: pd.DataFrame, mask: pd.DataFrame):
    """Exibe um DataFrame destacando em vermelho as células marcadas na máscara."""
    def _style(_):
        out = pd.DataFrame('', index=tabela.index, columns=tabela.columns)
        for c in mask.columns:
            if c in out.columns:
                out.loc[mask[c].values, c] = 'background-color: #ffd6d6'
        return out

    styler = tabela.style.apply(_style, axis=None).format(precision=4, na_rep='—')
    st.dataframe(styler, use_container_width=True, height=320)


def _render_overrides_icpoes(df, cols_conc, classes):
    """Passo 2: lista leituras acima da curva (flag ICPOES) e permite override manual do ICP-OES."""
    st.caption(
        "Amostras com concentração acima do último ponto da curva (flag ICPOES). "
        "Informe o valor obtido no ICP-OES (µg/L) para substituir; deixe 0 para manter o valor original."
    )
    d = df[df['Tipo_Amostra'] == 'Sample'].copy()
    d['Classe'] = d['Nome_Amostra'].map(quantification.classificar_amostra)
    d = d[d['Classe'].isin(classes)]

    overrides = st.session_state.get('quant_overrides', {})
    achou = False
    for c in cols_conc:
        flag = c.replace('_Conc', '_Flag_ICPOES')
        if flag not in d.columns:
            continue
        for _, r in d[d[flag] == True].iterrows():
            achou = True
            nome = r['Nome_Amostra']
            atual = r[c]
            val = st.number_input(
                f"{nome} · {c.replace('_Conc', '')} (atual: {atual:.4f} µg/L)",
                min_value=0.0, value=0.0, format="%.4f",
                key=f"ovr_{nome}_{c}",
            )
            if val > 0:
                overrides[(nome, c)] = val
            else:
                overrides.pop((nome, c), None)

    if not achou:
        st.success("✅ Nenhum valor acima da curva nas espécies/classes selecionadas.")
    st.session_state['quant_overrides'] = overrides


def _quant_sub_selecao_rsd(df, resultados_qc):
    st.markdown("#### Passo 1 — Seleção de espécies e modo de análise")
    st.caption(
        "Padrão **No Gas** (mais estável e indicado). Marque **He** por exceção, "
        "para elementos onde reduz interferências. As colunas TR% (do QC) ajudam a escolher o modo."
    )

    if 'quant_selecao' not in st.session_state:
        st.session_state['quant_selecao'] = quantification.listar_especies(df, resultados_qc)

    selecao = st.data_editor(
        st.session_state['quant_selecao'],
        key='editor_especies',
        use_container_width=True,
        hide_index=True,
        column_config={
            'Incluir': st.column_config.CheckboxColumn('Incluir'),
            'Espécie': st.column_config.TextColumn('Espécie', disabled=True),
            'Elemento': st.column_config.TextColumn('Elemento', disabled=True),
            'Modo': st.column_config.SelectboxColumn('Modo', options=list(quantification.MODOS)),
            'Modos_disp': st.column_config.TextColumn('Modos disp.', disabled=True),
            'TR%_NoGas': st.column_config.NumberColumn('TR% NoGas', format="%.1f", disabled=True),
            'TR%_He': st.column_config.NumberColumn('TR% He', format="%.1f", disabled=True),
        },
    )
    st.session_state['quant_selecao'] = selecao
    cols_conc = quantification.colunas_conc_escolhidas(selecao)
    st.session_state['quant_cols_conc'] = cols_conc
    st.info(f"🎯 {len(cols_conc)} espécie(s) selecionada(s).")

    st.markdown("#### Passos 3-4 — Classes de amostra e RSD")
    classes = st.multiselect(
        "Classes de amostra a incluir na tabela:",
        options=['Interesse', 'NIST', 'Branco', 'HNO3', 'Merck'],
        default=list(quantification.CLASSES_PADRAO),
        key='quant_classes',
    )

    with st.expander("⚠️ Passo 2 — Valores acima da curva (substituição manual por ICP-OES)"):
        _render_overrides_icpoes(df, cols_conc, classes)

    if st.button("🔄 Gerar tabelas reduzidas (RSD ≤15% e ≤25%)", type="primary", key="btn_reduzir"):
        if not cols_conc:
            st.error("Selecione ao menos uma espécie.")
        elif not classes:
            st.error("Selecione ao menos uma classe de amostra.")
        else:
            df_base = quantification.aplicar_override_icpoes(
                df, st.session_state.get('quant_overrides', {})
            )
            tabelas = {}
            for lim in (15.0, 25.0):
                conc_view, mask, d_full = quantification.reduzir_tabela(
                    df_base, cols_conc, lim, tuple(classes)
                )
                tabelas[lim] = {'conc': conc_view, 'mask': mask, 'full': d_full}
            st.session_state['quant_tabelas_rsd'] = tabelas
            st.success(f"✅ Tabelas geradas para {len(conc_view)} amostra(s).")

    tabelas = st.session_state.get('quant_tabelas_rsd')
    if tabelas:
        for lim in (15.0, 25.0):
            st.markdown(f"**📋 Tabela reduzida — RSD ≤ {int(lim)}%**  ·  células 🟥 = RSD acima do limite")
            _mostrar_tabela_destacada(tabelas[lim]['conc'], tabelas[lim]['mask'])


def _nomes_conc_atual(df):
    """Nomes de amostra (da concentração) a casar com o FDT — usa a tabela reduzida se existir."""
    tabelas = st.session_state.get('quant_tabelas_rsd')
    if tabelas:
        return tabelas[15.0]['conc']['Nome_Amostra'].astype(str).tolist()
    d = df[df['Tipo_Amostra'] == 'Sample']
    return d['Nome_Amostra'].astype(str).tolist()


def _quant_sub_fdt(df):
    st.markdown("#### Passo 5 — Fator de Diluição Total (FDT = FD1 × FD2)")

    opcoes = dilution.listar_matrizes()
    rotulos = {k: (rot if disp else f"{rot} (em breve)") for k, rot, disp in opcoes}
    disponiveis = [k for k, _, disp in opcoes if disp]

    matriz = st.radio(
        "Matriz analisada:",
        options=[k for k, _, _ in opcoes],
        format_func=lambda k: rotulos[k],
        horizontal=True,
        key='quant_matriz',
    )

    if matriz not in disponiveis:
        st.info(
            "🚧 Matriz ainda não implementada. Deixe um arquivo-modelo de massas desta matriz "
            "para configurarmos o cálculo de FD1 (chaminé / mel)."
        )
        return

    st.download_button(
        "📥 Baixar template de massas (em branco)",
        data=dilution.gerar_template_massas(matriz),
        file_name=f"template_massas_{matriz}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key='btn_tpl_massas',
    )
    st.caption(
        "Preencha o template com as massas pesadas e a diluição do ICP-OES, depois faça o upload abaixo."
    )

    arq = st.file_uploader(
        "Upload do arquivo de massas preenchido:",
        type=['xlsx', 'xls'], key='upl_massas',
    )
    if arq is None:
        st.info("📥 Aguardando o upload das massas para calcular o FDT.")
        return

    try:
        fdt, fd1, fd2 = dilution.calcular_fdt_completo(arq, matriz)
    except Exception as e:
        st.error(f"❌ Erro ao calcular o FDT: {e}")
        return

    st.session_state['quant_fdt'] = fdt
    st.success(f"✅ FDT calculado · {int(fdt['Casado'].sum())} amostra(s) com FD1 e FD2 casados.")

    with st.expander("Ver tabela de FDT (FD1, FD2, FDT, FDT mg/kg)", expanded=False):
        st.dataframe(fdt, use_container_width=True, height=320)

    # Casamento com a tabela de concentração
    nomes_conc = _nomes_conc_atual(df)
    fdt_map, faltando = dilution.construir_fdt_map(nomes_conc, fdt)
    st.session_state['quant_fdt_map'] = fdt_map

    c1, c2 = st.columns(2)
    c1.metric("✅ Amostras casadas (conc ↔ FDT)", len(fdt_map))
    c2.metric("⚠️ Sem FDT", len(faltando))
    if faltando:
        with st.expander(f"⚠️ {len(faltando)} amostra(s) de concentração sem FDT — revisar nomes"):
            st.write(faltando)


def _quant_sub_tr(df):
    st.markdown("#### Passo 6 — Taxa de Recuperação (TR%) do material de referência")

    fdt_map = st.session_state.get('quant_fdt_map')
    cols_conc = st.session_state.get('quant_cols_conc')
    if not fdt_map or not cols_conc:
        st.warning("⚠️ Complete o Passo 1 (Seleção) e o Passo 5 (FDT) primeiro.")
        return

    material = st.selectbox(
        "Material de referência:",
        reference_materials.materiais_disponiveis(),
        key='quant_material',
    )
    st.caption("🚩 TR% fora da faixa 90–110% é destacada em vermelho (red flag).")

    d = df[df['Tipo_Amostra'] == 'Sample'].copy()
    d['Classe'] = d['Nome_Amostra'].map(quantification.classificar_amostra)
    nist = d[d['Classe'] == 'NIST']
    if len(nist) == 0:
        st.info("ℹ️ Nenhuma amostra NIST encontrada nos dados.")
        return

    mgkg = quantification.converter_mgkg(nist, cols_conc, fdt_map)

    for _, row in mgkg.iterrows():
        nome = row['Nome_Amostra']
        valores = {}
        for c in cols_conc:
            elem_col = c.replace('_Conc', '')
            v = row.get(elem_col)
            if isinstance(v, (int, float)) and not pd.isna(v):
                valores[reference_materials.elemento_base(elem_col)] = v
        tr = reference_materials.calcular_tr_certificado(valores, material)
        st.markdown(f"**🧫 {nome}**")
        _mostrar_tr(tr)


def _mostrar_tr(tr: pd.DataFrame):
    show = tr[tr['Status'] != 'Sem leitura'].reset_index(drop=True)
    if len(show) == 0:
        st.caption("Sem elementos certificados com leitura para esta amostra.")
        return

    disp = show[['Elemento', 'Medido_mgkg', 'Certificado', 'TR_pct', 'Status']].copy()
    reds = show['Red_Flag'].values

    def _style(_):
        out = pd.DataFrame('', index=disp.index, columns=disp.columns)
        out.loc[reds, :] = 'background-color: #ffd6d6'
        return out

    styler = disp.style.apply(_style, axis=None).format(
        {'Medido_mgkg': '{:.4f}', 'Certificado': '{:.4f}', 'TR_pct': '{:.1f}'}
    )
    st.dataframe(styler, use_container_width=True, hide_index=True)


def _aplicar_filtro_full(d_full: pd.DataFrame, mask: pd.DataFrame) -> pd.DataFrame:
    """Zera (NaN) as concentrações cujo RSD ultrapassou o limite (versão filtrada)."""
    d = d_full.copy().reset_index(drop=True)
    for c in mask.columns:
        if c in d.columns:
            d.loc[mask[c].values, c] = np.nan
    return d


def _download_resultado(df_res: pd.DataFrame, base: str, meta: dict = None):
    from io import BytesIO
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine='openpyxl') as writer:
        startrow = 0
        if meta:
            meta_df = pd.DataFrame(list(meta.items()), columns=['Campo', 'Valor'])
            meta_df.to_excel(writer, index=False, sheet_name='Resultado', startrow=0)
            startrow = len(meta_df) + 2
        df_res.to_excel(writer, index=False, sheet_name='Resultado', startrow=startrow)
    buf.seek(0)
    st.download_button(
        "📥 Excel",
        data=buf.getvalue(),
        file_name=f"{base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
        mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        key=f"dl_{base}",
    )


def _quant_sub_resultado(df):
    st.markdown("#### Passos 7-8 — Resultado em mg/kg (triplicata e média)")

    tabelas = st.session_state.get('quant_tabelas_rsd')
    fdt_map = st.session_state.get('quant_fdt_map')
    cols_conc = st.session_state.get('quant_cols_conc')

    if not tabelas or not fdt_map or not cols_conc:
        st.warning("⚠️ Complete o Passo 1 (Seleção & RSD) e o Passo 5 (FDT) primeiro.")
        return

    with st.expander("📝 Cabeçalho do laudo (opcional)"):
        meta = {
            'Solicitante': st.text_input("Solicitante", key='meta_solic'),
            'Data': st.text_input("Data", value=datetime.now().strftime('%d/%m/%Y'), key='meta_data'),
            'Equipamento': st.text_input("Equipamento", value="ICP-MS Agilent 7700x", key='meta_equip'),
        }

    filtrar = st.checkbox(
        "Remover (deixar em branco) valores com RSD acima do limite",
        value=False, key='quant_filtrar_rsd',
    )

    for lim in (15.0, 25.0):
        st.markdown(f"### RSD ≤ {int(lim)}%")
        d_full = tabelas[lim]['full']
        if filtrar:
            d_full = _aplicar_filtro_full(d_full, tabelas[lim]['mask'])

        tri = quantification.converter_mgkg(d_full, cols_conc, fdt_map)
        med = quantification.agregar_media(tri)

        c1, c2 = st.columns(2)
        with c1:
            st.markdown("**Triplicata (réplicas individuais)**")
            st.dataframe(tri, use_container_width=True, height=340)
            _download_resultado(tri, f"resultado_mgkg_triplicata_rsd{int(lim)}", meta)
        with c2:
            st.markdown("**Média por amostra**")
            st.dataframe(med, use_container_width=True, height=340)
            _download_resultado(med, f"resultado_mgkg_media_rsd{int(lim)}", meta)


# ============================================
# APLICAÇÃO PRINCIPAL
# ============================================

def main():
    """Função principal da aplicação."""
    
    # Configurar autenticação
    authenticator = configurar_autenticacao()
    
    # Tentar login (nova API do streamlit-authenticator >= 0.3.0)
    authenticator.login(location='main')
    
    # Verificar status de autenticação (valores agora estão em st.session_state)
    if st.session_state.get("authentication_status") == False:
        st.error('❌ Usuário ou senha incorretos')
        exibir_tela_login()
    
    elif st.session_state.get("authentication_status") == None:
        st.warning('⚠️ Por favor, entre com seu usuário e senha')
        exibir_tela_login()
    
    elif st.session_state.get("authentication_status"):
        # Autenticado com sucesso
        name = st.session_state.get("name")
        username = st.session_state.get("username")
        renderizar_dashboard(name, username, authenticator)


# ============================================
# PONTO DE ENTRADA
# ============================================

if __name__ == "__main__":
    main()
