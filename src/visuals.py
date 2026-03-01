"""
Módulo de Visualizações para Dashboard ICP-MS

Este módulo contém funções especializadas para criar visualizações
analíticas usando Plotly para o dashboard de análise de metais pesados.

Autor: Engenharia de Dados - Setor Ambiental
Data: 28 de fevereiro de 2026
Versão: 2.1.0
"""

import pandas as pd
import numpy as np
import plotly.express as px
import plotly.graph_objects as go
from typing import Dict, List, Tuple, Optional
import re


def criar_grafico_pizza_qc(resultados_qc: Dict) -> go.Figure:
    """
    Cria gráfico de pizza para ensaios analíticos Aprovados vs Reprovados no TR%.
    
    Args:
        resultados_qc: Dicionário com resultados do QC
    
    Returns:
        Figura Plotly com gráfico de pizza
    """
    n_aprovados = len(resultados_qc.get('elementos_aprovados', []))
    n_reprovados = len(resultados_qc.get('elementos_reprovados', []))
    
    # Dados para o gráfico
    labels = ['Aprovados', 'Reprovados']
    values = [n_aprovados, n_reprovados]
    colors = ['#28a745', '#dc3545']  # Verde e Vermelho
    
    # Criar gráfico de pizza
    fig = go.Figure(data=[go.Pie(
        labels=labels,
        values=values,
        marker=dict(colors=colors),
        textinfo='label+value+percent',
        textfont_size=14,
        hole=0.3  # Donut chart
    )])
    
    fig.update_layout(
        title={
            'text': 'Taxa de Recuperação (TR%) - Status dos Ensaios Analíticos',
            'x': 0.5,
            'xanchor': 'center'
        },
        showlegend=True,
        height=350,
        margin=dict(t=50, b=20, l=20, r=20)
    )
    
    return fig


def calcular_comparativo_he_nogas(resultados_qc: Dict, df: pd.DataFrame) -> Dict:
    """
    Compara desempenho de elementos analisados com Hélio vs Sem Gás.
    
    Lógica: Para elementos que possuem leitura nos dois modos (ex: Al_He e Al_NoGas),
    compara TR% de cada modo. O "melhor" é aquele mais próximo de 100%.
    
    Args:
        resultados_qc: Resultados do QC com TR%
        df: DataFrame com dados processados
    
    Returns:
        Dict com {
            'melhor_he': número de elementos,
            'melhor_nogas': número de elementos,
            'empates': número de empates,
            'detalhes': lista de dicts com comparações
        }
    """
    tr_info = resultados_qc.get('tr', {})
    
    # Identificar elementos base (sem sufixo He ou NoGas)
    elementos_aprovados = resultados_qc.get('elementos_aprovados', [])
    
    # Mapear elementos por nome base
    elementos_por_base = {}
    
    for elemento in elementos_aprovados:
        # Remover sufixos _He ou _NoGas
        if elemento.endswith('_He'):
            base = elemento[:-3]
            modo = 'He'
        elif elemento.endswith('_NoGas'):
            base = elemento[:-6]
            modo = 'NoGas'
        else:
            continue
        
        if base not in elementos_por_base:
            elementos_por_base[base] = {}
        
        elementos_por_base[base][modo] = elemento
    
    # Calcular comparativos
    melhor_he = 0
    melhor_nogas = 0
    empates = 0
    detalhes = []
    
    for base, modos in elementos_por_base.items():
        if 'He' in modos and 'NoGas' in modos:
            elem_he = modos['He']
            elem_nogas = modos['NoGas']
            
            # Obter TR% de ambos (média de TR_50 e TR_200)
            tr_he = tr_info.get(elem_he, {})
            tr_nogas = tr_info.get(elem_nogas, {})
            
            # Calcular TR médio
            def calcular_tr_medio(tr_dict):
                tr_50 = tr_dict.get('tr_50', np.nan)
                tr_200 = tr_dict.get('tr_200', np.nan)
                
                valores = [v for v in [tr_50, tr_200] if not pd.isna(v)]
                if len(valores) > 0:
                    return np.mean(valores)
                return np.nan
            
            tr_medio_he = calcular_tr_medio(tr_he)
            tr_medio_nogas = calcular_tr_medio(tr_nogas)
            
            if pd.isna(tr_medio_he) or pd.isna(tr_medio_nogas):
                continue
            
            # Calcular distância de 100%
            dist_he = abs(100 - tr_medio_he)
            dist_nogas = abs(100 - tr_medio_nogas)
            
            # Determinar vencedor
            if dist_he < dist_nogas - 1:  # Margem de 1% para considerar empate
                melhor_he += 1
                vencedor = 'He'
            elif dist_nogas < dist_he - 1:
                melhor_nogas += 1
                vencedor = 'NoGas'
            else:
                empates += 1
                vencedor = 'Empate'
            
            detalhes.append({
                'elemento_base': base,
                'tr_he': tr_medio_he,
                'tr_nogas': tr_medio_nogas,
                'dist_he': dist_he,
                'dist_nogas': dist_nogas,
                'vencedor': vencedor
            })
    
    return {
        'melhor_he': melhor_he,
        'melhor_nogas': melhor_nogas,
        'empates': empates,
        'detalhes': detalhes
    }


def criar_grafico_curva_calibracao(elemento: str, df: pd.DataFrame, 
                                   curva_info: Dict) -> Optional[go.Figure]:
    """
    Cria gráfico da curva de calibração para um elemento específico.
    
    Args:
        elemento: Nome do elemento (ex: 'Al_NoGas')
        df: DataFrame com dados processados
        curva_info: Informações da curva do QC
    
    Returns:
        Figura Plotly com scatter/line plot ou None se não houver dados
    """
    if not curva_info or not curva_info.get('valida'):
        return None
    
    col_conc = f"{elemento}_Conc"
    
    if col_conc not in df.columns or 'Tipo_Amostra' not in df.columns:
        return None
    
    # Filtrar CalStd
    df_calstd = df[df['Tipo_Amostra'] == 'CalStd'].copy()
    
    if len(df_calstd) == 0:
        return None
    
    # Identificar série escolhida
    serie = curva_info.get('serie')
    
    if serie == 'A':
        pontos_nomes = ['P0', 'P1A', 'P2A', 'P3A', 'P4A', 'P5A', 'P6A']
        # Concentrações teóricas (ajuste conforme necessário)
        conc_teoricas = [0, 10, 20, 30, 40, 50, 60]  # Exemplo - deve ser ajustado
    elif serie == 'B':
        pontos_nomes = ['P0', 'P1B', 'P2B', 'P3B', 'P4B', 'P5B', 'P6B', 'P7B']
        conc_teoricas = [0, 10, 20, 30, 40, 50, 60, 70]  # Exemplo - deve ser ajustado
    else:
        return None
    
    # Extrair valores medidos
    conc_medidas = []
    pontos_validos = []
    conc_teoricas_validas = []
    
    for i, ponto in enumerate(pontos_nomes):
        row = df_calstd[df_calstd['Nome_Amostra'].str.contains(ponto, case=False, na=False)]
        
        if len(row) > 0:
            valor = row[col_conc].iloc[0]
            if not pd.isna(valor):
                conc_medidas.append(valor)
                pontos_validos.append(ponto)
                conc_teoricas_validas.append(conc_teoricas[i])
    
    if len(conc_medidas) == 0:
        return None
    
    # Criar gráfico
    fig = go.Figure()
    
    # Pontos da curva
    fig.add_trace(go.Scatter(
        x=conc_teoricas_validas,
        y=conc_medidas,
        mode='markers+lines',
        name='Curva de Calibração',
        marker=dict(size=10, color='#1f77b4'),
        line=dict(width=2, color='#1f77b4'),
        text=pontos_validos,
        hovertemplate='<b>%{text}</b><br>Teórico: %{x}<br>Medido: %{y:.4f}<extra></extra>'
    ))
    
    # Linha de referência ideal (y=x)
    fig.add_trace(go.Scatter(
        x=[0, max(conc_teoricas_validas)],
        y=[0, max(conc_teoricas_validas)],
        mode='lines',
        name='Ideal (y=x)',
        line=dict(width=1, dash='dash', color='gray'),
        hoverinfo='skip'
    ))
    
    fig.update_layout(
        title=f'Curva de Calibração - {elemento} (Série {serie})',
        xaxis_title='Concentração Teórica (µg/L)',
        yaxis_title='Concentração Medida (µg/L)',
        template='plotly_white',
        height=400,
        hovermode='closest',
        showlegend=True
    )
    
    return fig


def classificar_amostras_laboratoriais(df: pd.DataFrame) -> Tuple[pd.DataFrame, Dict]:
    """
    Classifica amostras com regras laboratoriais rigorosas e trata triplicatas.
    
    Regras de Classificação (ordem de prioridade, case-insensitive):
    1. Calibração: Nome inicia com 'P' (ex: P0, P1A, P7B)
    2. Padrão HNO3: Nome contém 'HNO3'
    3. Branco: Nome inicia com 'B' (ex: B1, B2)
    4. Solução Merck: Nome inicia com 'Merck' (ex: Merck50A)
    5. Padrão NIST: Nome contém 'Nist'
    6. Amostra de Interesse: Nome inicia com número (ex: 1130A)
    
    Regras de Contagem:
    - Amostras de Interesse: Triplicatas (ex: 1130A, 1130B, 1130C) → conta únicos (base numérica)
    - Solução Merck: Triplicatas (ex: Merck50A, B, C) → conta únicos (base Merck50)
    - Demais: Contagem total de leituras
    
    Args:
        df: DataFrame com dados processados
    
    Returns:
        Tuple contendo:
        - DataFrame com contagem por categoria e regra aplicada
        - Dict com estatísticas detalhadas
    """
    # Filtrar apenas amostras reais
    if 'Tipo_Amostra' not in df.columns or 'Nome_Amostra' not in df.columns:
        return pd.DataFrame(), {}
    
    df_samples = df[df['Tipo_Amostra'] == 'Sample'].copy()
    
    if len(df_samples) == 0:
        return pd.DataFrame(), {}
    
    # Função de classificação (ordem de prioridade)
    def classificar(nome: str) -> str:
        nome_str = str(nome).strip()
        nome_upper = nome_str.upper()
        
        # 1. Calibração: inicia com 'P'
        if nome_upper.startswith('P'):
            return 'Calibração'
        
        # 2. Padrão HNO3: contém 'HNO3'
        if 'HNO3' in nome_upper:
            return 'Padrão HNO3'
        
        # 3. Branco: inicia com 'B'
        if nome_upper.startswith('B'):
            return 'Branco'
        
        # 4. Solução Merck: inicia com 'Merck'
        if nome_upper.startswith('MERCK'):
            return 'Solução Merck'
        
        # 5. Padrão NIST: contém 'Nist'
        if 'NIST' in nome_upper:
            return 'Padrão NIST'
        
        # 6. Amostra de Interesse: inicia com número
        if nome_str and nome_str[0].isdigit():
            return 'Amostra de Interesse'
        
        # Caso padrão
        return 'Outras'
    
    # Aplicar classificação
    df_samples['Categoria_Lab'] = df_samples['Nome_Amostra'].apply(classificar)
    
    # Função para extrair base numérica (remove última letra)
    def extrair_base_numerica(nome: str) -> str:
        nome_str = str(nome).strip()
        # Se termina com letra (A, B, C), remove
        if len(nome_str) > 0 and nome_str[-1].isalpha():
            return nome_str[:-1]
        return nome_str
    
    # Função para extrair base Merck (ex: Merck50A → Merck50)
    def extrair_base_merck(nome: str) -> str:
        nome_str = str(nome).strip()
        # Remove última letra se existir
        if len(nome_str) > 0 and nome_str[-1].isalpha() and nome_str.upper().startswith('MERCK'):
            return nome_str[:-1]
        return nome_str
    
    # Contar por categoria aplicando regras específicas
    resultados = []
    estatisticas_detalhadas = {}
    
    for categoria in df_samples['Categoria_Lab'].unique():
        df_cat = df_samples[df_samples['Categoria_Lab'] == categoria]
        
        if categoria == 'Amostra de Interesse':
            # Triplicatas: extrair base e contar únicos
            df_cat['Base'] = df_cat['Nome_Amostra'].apply(extrair_base_numerica)
            n_unicos = df_cat['Base'].nunique()
            n_leituras = len(df_cat)
            
            resultados.append({
                'Classe': categoria,
                'Regra de Contagem': 'Únicas',
                'Valor': n_unicos,
                'Leituras Totais': n_leituras,
                'Ordem': 6
            })
            
            estatisticas_detalhadas[categoria] = {
                'amostras_unicas': n_unicos,
                'leituras_totais': n_leituras,
                'bases': df_cat['Base'].unique().tolist()
            }
        
        elif categoria == 'Solução Merck':
            # Triplicatas Merck: extrair base e contar únicos
            df_cat['Base_Merck'] = df_cat['Nome_Amostra'].apply(extrair_base_merck)
            n_unicos = df_cat['Base_Merck'].nunique()
            n_leituras = len(df_cat)
            
            resultados.append({
                'Classe': categoria,
                'Regra de Contagem': 'Únicas',
                'Valor': n_unicos,
                'Leituras Totais': n_leituras,
                'Ordem': 4
            })
            
            estatisticas_detalhadas[categoria] = {
                'amostras_unicas': n_unicos,
                'leituras_totais': n_leituras,
                'bases': df_cat['Base_Merck'].unique().tolist()
            }
        
        else:
            # Demais: contagem total
            n_leituras = len(df_cat)
            
            # Mapear ordem
            ordem_map = {
                'Calibração': 1,
                'Padrão HNO3': 2,
                'Branco': 3,
                'Padrão NIST': 5,
                'Outras': 7
            }
            
            resultados.append({
                'Classe': categoria,
                'Regra de Contagem': 'Total de Leituras',
                'Valor': n_leituras,
                'Leituras Totais': n_leituras,
                'Ordem': ordem_map.get(categoria, 99)
            })
            
            estatisticas_detalhadas[categoria] = {
                'leituras_totais': n_leituras,
                'amostras': df_cat['Nome_Amostra'].tolist()
            }
    
    # Criar DataFrame de resultados
    df_resultados = pd.DataFrame(resultados)
    
    if len(df_resultados) > 0:
        df_resultados = df_resultados.sort_values('Ordem').drop(columns=['Ordem'])
    
    return df_resultados, estatisticas_detalhadas


def criar_grafico_distribuicao_amostras(df_contagem: pd.DataFrame) -> go.Figure:
    """
    Cria gráfico de rosca (donut chart) com distribuição de classes de amostras.
    
    Args:
        df_contagem: DataFrame com colunas 'Classe' e 'Leituras Totais'
    
    Returns:
        Figura Plotly com gráfico de rosca
    """
    if len(df_contagem) == 0:
        return None
    
    # Definir cores para cada classe
    color_map = {
        'Calibração': '#6c757d',         # Cinza
        'Padrão HNO3': '#17a2b8',        # Ciano
        'Branco': '#ffc107',             # Amarelo
        'Solução Merck': '#28a745',      # Verde
        'Padrão NIST': '#007bff',        # Azul
        'Amostra de Interesse': '#dc3545',  # Vermelho
        'Outras': '#e9ecef'              # Cinza claro
    }
    
    # Mapear cores
    cores = [color_map.get(classe, '#cccccc') for classe in df_contagem['Classe']]
    
    # Criar gráfico de rosca
    fig = go.Figure(data=[go.Pie(
        labels=df_contagem['Classe'],
        values=df_contagem['Leituras Totais'],
        marker=dict(colors=cores),
        textinfo='label+percent',
        textfont_size=12,
        hole=0.4  # Donut chart
    )])
    
    fig.update_layout(
        title={
            'text': 'Distribuição de Classes de Amostras',
            'x': 0.5,
            'xanchor': 'center'
        },
        showlegend=True,
        height=400,
        margin=dict(t=50, b=20, l=20, r=20),
        legend=dict(
            orientation="v",
            yanchor="middle",
            y=0.5,
            xanchor="left",
            x=1.05
        )
    )
    
    return fig


def calcular_porcentagem_lod(df: pd.DataFrame) -> float:
    """
    Calcula porcentagem de valores < LOD em relação ao total de dados analíticos.
    
    Args:
        df: DataFrame com dados processados
    
    Returns:
        Porcentagem de valores < LOD (0-100)
    """
    # Identificar colunas de flag LOD
    colunas_flag_lod = [col for col in df.columns if 'Flag_LOD' in col]
    
    if len(colunas_flag_lod) == 0:
        return 0.0
    
    # Identificar colunas de concentração correspondentes
    colunas_concentracao = [col.replace('_Flag_LOD', '') for col in colunas_flag_lod]
    colunas_concentracao = [col for col in colunas_concentracao if col in df.columns]
    
    if len(colunas_concentracao) == 0:
        return 0.0
    
    # Contar total de valores analíticos não-nulos
    total_valores = df[colunas_concentracao].notna().sum().sum()
    
    if total_valores == 0:
        return 0.0
    
    # Contar valores com flag LOD
    total_lod = df[colunas_flag_lod].sum().sum()
    
    # Calcular porcentagem
    porcentagem = (total_lod / total_valores) * 100
    
    return porcentagem


def calcular_metricas_validacao_amostras(df: pd.DataFrame, resultados_qc: Dict) -> Dict:
    """
    Calcula métricas de validação de Amostras de Interesse (únicas vs leituras).
    
    Diferencia:
    - Amostras Únicas: Valores únicos ignorando sufixo de triplicata (ex: 1130A, 1130B, 1130C = 1 amostra)
    - Leituras: Cada linha individual no dataset
    
    ⚠️ IMPORTANTE - CLASSIFICAÇÃO DE FLAGS:
    - Flags CRÍTICAS (invalidam amostra): ICPOES e RSD
    - Flag INFORMATIVA (NÃO invalida): LOD (< Limite de Detecção)
    
    A presença de valores < LOD é NORMAL em análises ambientais e NÃO desqualifica
    a amostra. Apenas ICPOES (concentração acima da curva) e RSD (variação excessiva)
    são considerados problemas críticos que invalidam a leitura.
    
    Args:
        df: DataFrame com dados processados
        resultados_qc: Resultados do QC
    
    Returns:
        Dict com {
            'total_amostras_unicas': número total de amostras únicas,
            'amostras_validadas': amostras sem flags CRÍTICAS (ICPOES/RSD),
            'amostras_com_flags': amostras com pelo menos uma flag CRÍTICA,
            'leituras_flag_icpoes': total de linhas com flag ICPOES,
            'leituras_flag_rsd': total de linhas com flag RSD,
            'pct_amostras_validadas': porcentagem de amostras validadas
        }
    """
    # Filtrar apenas Amostras de Interesse
    if 'Tipo_Amostra' not in df.columns or 'Nome_Amostra' not in df.columns:
        return {
            'total_amostras_unicas': 0,
            'amostras_validadas': 0,
            'amostras_com_flags': 0,
            'leituras_flag_icpoes': 0,
            'leituras_flag_rsd': 0,
            'pct_amostras_validadas': 0.0
        }
    
    df_amostras = df[df['Tipo_Amostra'] == 'Sample'].copy()
    
    # Filtrar apenas amostras que iniciam com número (Amostra de Interesse)
    df_amostras = df_amostras[
        df_amostras['Nome_Amostra'].astype(str).str[0].str.isdigit()
    ]
    
    if len(df_amostras) == 0:
        return {
            'total_amostras_unicas': 0,
            'amostras_validadas': 0,
            'amostras_com_flags': 0,
            'leituras_flag_icpoes': 0,
            'leituras_flag_rsd': 0,
            'pct_amostras_validadas': 0.0
        }
    
    # Extrair base numérica (remove última letra para agrupar triplicatas)
    def extrair_base(nome: str) -> str:
        nome_str = str(nome).strip()
        if len(nome_str) > 0 and nome_str[-1].isalpha():
            return nome_str[:-1]
        return nome_str
    
    df_amostras['Base_Amostra'] = df_amostras['Nome_Amostra'].apply(extrair_base)
    
    # Contar amostras únicas
    total_amostras_unicas = df_amostras['Base_Amostra'].nunique()
    
    # Identificar colunas de flags CRÍTICAS (apenas elementos aprovados)
    # NOTA: Flag_LOD NÃO é considerada aqui - é apenas informativa
    elementos_aprovados = resultados_qc.get('elementos_aprovados', [])
    
    colunas_flag_icpoes = [f"{elem}_Flag_ICPOES" for elem in elementos_aprovados 
                           if f"{elem}_Flag_ICPOES" in df_amostras.columns]
    colunas_flag_rsd = [f"{elem}_Flag_RSD" for elem in elementos_aprovados 
                        if f"{elem}_Flag_RSD" in df_amostras.columns]
    
    # Contar leituras (linhas) com flags
    leituras_flag_icpoes = 0
    leituras_flag_rsd = 0
    
    if len(colunas_flag_icpoes) > 0:
        # Linha tem flag ICPOES se qualquer coluna for True
        leituras_flag_icpoes = df_amostras[colunas_flag_icpoes].any(axis=1).sum()
    
    if len(colunas_flag_rsd) > 0:
        # Linha tem flag RSD se qualquer coluna for True
        leituras_flag_rsd = df_amostras[colunas_flag_rsd].any(axis=1).sum()
    
    # Identificar amostras únicas que NÃO possuem NENHUMA flag em suas leituras
    # Uma amostra é validada se TODAS as suas leituras (triplicatas) não têm flags
    
    amostras_com_flags = set()
    
    for _, row in df_amostras.iterrows():
        base = row['Base_Amostra']
        tem_flag = False
        
        # Verificar se esta linha tem alguma flag
        if len(colunas_flag_icpoes) > 0:
            if row[colunas_flag_icpoes].any():
                tem_flag = True
        
        if len(colunas_flag_rsd) > 0:
            if row[colunas_flag_rsd].any():
                tem_flag = True
        
        if tem_flag:
            amostras_com_flags.add(base)
    
    amostras_com_flags_count = len(amostras_com_flags)
    amostras_validadas = total_amostras_unicas - amostras_com_flags_count
    
    pct_validadas = (amostras_validadas / total_amostras_unicas * 100) if total_amostras_unicas > 0 else 0.0
    
    return {
        'total_amostras_unicas': total_amostras_unicas,
        'amostras_validadas': amostras_validadas,
        'amostras_com_flags': amostras_com_flags_count,
        'leituras_flag_icpoes': int(leituras_flag_icpoes),
        'leituras_flag_rsd': int(leituras_flag_rsd),
        'pct_amostras_validadas': pct_validadas
    }


def calcular_desempenho_amostras_flags(df: pd.DataFrame, resultados_qc: Dict) -> Dict:
    """
    Calcula o desempenho das amostras de interesse em relação aos flags CRÍTICOS.
    
    Analisa quantas amostras têm diferentes proporções de flags:
    - 0 flags (100% aprovadas)
    - 1/3 das leituras com flag (~33%)
    - 2/3 das leituras com flag (~67%)
    - 3/3 das leituras com flag (100%)
    
    ⚠️ IMPORTANTE: Considera apenas flags CRÍTICAS (ICPOES e RSD).
    Flag_LOD NÃO é considerada pois é apenas informativa.
    
    Args:
        df: DataFrame com dados processados
        resultados_qc: Resultados do QC
    
    Returns:
        Dict com distribuição de amostras por proporção de flags críticas
    """
    # Filtrar apenas Amostras de Interesse
    if 'Tipo_Amostra' not in df.columns or 'Nome_Amostra' not in df.columns:
        return {
            'sem_flags': 0,
            'com_33_flags': 0,
            'com_67_flags': 0,
            'com_100_flags': 0,
            'total_amostras': 0,
            'detalhes': []
        }
    
    df_amostras = df[df['Tipo_Amostra'] == 'Sample'].copy()
    df_amostras = df_amostras[
        df_amostras['Nome_Amostra'].astype(str).str[0].str.isdigit()
    ]
    
    if len(df_amostras) == 0:
        return {
            'sem_flags': 0,
            'com_33_flags': 0,
            'com_67_flags': 0,
            'com_100_flags': 0,
            'total_amostras': 0,
            'detalhes': []
        }
    
    # Extrair base numérica
    def extrair_base(nome: str) -> str:
        nome_str = str(nome).strip()
        if len(nome_str) > 0 and nome_str[-1].isalpha():
            return nome_str[:-1]
        return nome_str
    
    df_amostras['Base_Amostra'] = df_amostras['Nome_Amostra'].apply(extrair_base)
    
    # Identificar colunas de flags CRÍTICAS (apenas elementos aprovados)
    # NOTA: Flag_LOD NÃO é incluída - é apenas informativa, não invalida amostra
    elementos_aprovados = resultados_qc.get('elementos_aprovados', [])
    
    colunas_flag_icpoes = [f"{elem}_Flag_ICPOES" for elem in elementos_aprovados 
                           if f"{elem}_Flag_ICPOES" in df_amostras.columns]
    colunas_flag_rsd = [f"{elem}_Flag_RSD" for elem in elementos_aprovados 
                        if f"{elem}_Flag_RSD" in df_amostras.columns]
    
    colunas_flags = colunas_flag_icpoes + colunas_flag_rsd
    
    if len(colunas_flags) == 0:
        return {
            'sem_flags': len(df_amostras['Base_Amostra'].unique()),
            'com_33_flags': 0,
            'com_67_flags': 0,
            'com_100_flags': 0,
            'total_amostras': len(df_amostras['Base_Amostra'].unique()),
            'detalhes': []
        }
    
    # Analisar cada amostra única
    amostras_unicas = df_amostras['Base_Amostra'].unique()
    
    sem_flags = 0
    com_33_flags = 0
    com_67_flags = 0
    com_100_flags = 0
    detalhes = []
    
    for base in amostras_unicas:
        # Pegar todas as leituras desta amostra
        leituras_amostra = df_amostras[df_amostras['Base_Amostra'] == base]
        n_leituras = len(leituras_amostra)
        
        # Contar quantas leituras têm flags
        leituras_com_flag = 0
        
        for _, row in leituras_amostra.iterrows():
            tem_flag = False
            
            if len(colunas_flags) > 0:
                if row[colunas_flags].any():
                    tem_flag = True
            
            if tem_flag:
                leituras_com_flag += 1
        
        # Calcular proporção
        proporcao = leituras_com_flag / n_leituras if n_leituras > 0 else 0
        
        # Classificar
        if leituras_com_flag == 0:
            categoria = 'Sem flags (100% aprovadas)'
            sem_flags += 1
        elif proporcao <= 0.4:  # ~33%
            categoria = '~33% com flags (1 de 3)'
            com_33_flags += 1
        elif proporcao <= 0.75:  # ~67%
            categoria = '~67% com flags (2 de 3)'
            com_67_flags += 1
        else:  # 100%
            categoria = '100% com flags (todas)'
            com_100_flags += 1
        
        detalhes.append({
            'base': base,
            'n_leituras': n_leituras,
            'leituras_com_flag': leituras_com_flag,
            'proporcao': proporcao,
            'categoria': categoria
        })
    
    return {
        'sem_flags': sem_flags,
        'com_33_flags': com_33_flags,
        'com_67_flags': com_67_flags,
        'com_100_flags': com_100_flags,
        'total_amostras': len(amostras_unicas),
        'detalhes': detalhes
    }


def criar_resumo_qc_por_elemento(df: pd.DataFrame, resultados_qc: Dict) -> tuple:
    """
    Cria resumo de qualidade centrado no ELEMENTO (não na amostra).
    
    Para cada elemento aprovado no TR%, conta:
    - Total de linhas (leituras) de amostras de interesse disponíveis
    - Leituras aprovadas (sem flags críticas)
    - Leituras com Flag ICPOES
    - Leituras com Flag RSD
    
    ⚠️ MATEMÁTICA CORRETA:
    Para cada elemento: Aprovadas + ICPOES + RSD = Total de Linhas
    
    Args:
        df: DataFrame com dados processados
        resultados_qc: Resultados do QC
    
    Returns:
        Tupla (df_resumo_elementos, metricas_resumo) com:
        - df_resumo_elementos: DataFrame [Elemento, Amostras_Unicas, Leituras_Aprovadas, 
                                          Flags_ICPOES, Flags_RSD, Pct_Aprovadas]
        - metricas_resumo: Dict com totais do lote
    """
    # Filtrar apenas Amostras de Interesse
    if 'Tipo_Amostra' not in df.columns or 'Nome_Amostra' not in df.columns:
        return pd.DataFrame(), {
            'universo_total': 0,
            'leituras_aprovadas': 0,
            'leituras_icpoes': 0,
            'leituras_rsd': 0,
            'total_amostras_unicas': 0,
            'total_elementos_aprovados': 0,
            'total_linhas': 0
        }
    
    df_amostras = df[df['Tipo_Amostra'] == 'Sample'].copy()
    df_amostras = df_amostras[
        df_amostras['Nome_Amostra'].astype(str).str[0].str.isdigit()
    ]
    
    if len(df_amostras) == 0:
        return pd.DataFrame(), {
            'universo_total': 0,
            'leituras_aprovadas': 0,
            'leituras_icpoes': 0,
            'leituras_rsd': 0,
            'total_amostras_unicas': 0,
            'total_elementos_aprovados': 0,
            'total_linhas': 0
        }
    
    # Extrair base numérica para contar amostras únicas (contexto)
    def extrair_base(nome: str) -> str:
        nome_str = str(nome).strip()
        if len(nome_str) > 0 and nome_str[-1].isalpha():
            return nome_str[:-1]
        return nome_str
    
    df_amostras['Base_Amostra'] = df_amostras['Nome_Amostra'].apply(extrair_base)
    total_amostras_unicas = df_amostras['Base_Amostra'].nunique()
    
    # Total de LINHAS (rows) de amostras de interesse
    total_linhas = len(df_amostras)
    
    # Identificar elementos aprovados
    elementos_aprovados = resultados_qc.get('elementos_aprovados', [])
    total_elementos_aprovados = len(elementos_aprovados)
    
    # Para cada elemento, contar leituras (linhas) por status
    resumo_elementos = []
    
    total_leituras_aprovadas_lote = 0
    total_leituras_icpoes_lote = 0
    total_leituras_rsd_lote = 0
    
    for elemento in elementos_aprovados:
        col_icpoes = f"{elemento}_Flag_ICPOES"
        col_rsd = f"{elemento}_Flag_RSD"
        
        # Verificar se colunas existem
        if col_icpoes not in df_amostras.columns or col_rsd not in df_amostras.columns:
            continue
        
        # Contar linhas por status
        # Aprovadas: sem ICPOES E sem RSD
        aprovadas = ((df_amostras[col_icpoes] == False) & (df_amostras[col_rsd] == False)).sum()
        
        # Flags ICPOES
        flags_icpoes = (df_amostras[col_icpoes] == True).sum()
        
        # Flags RSD
        flags_rsd = (df_amostras[col_rsd] == True).sum()
        
        # Calcular porcentagem de aprovadas
        pct_aprovadas = (aprovadas / total_linhas * 100) if total_linhas > 0 else 0
        
        # Acumular totais do lote
        total_leituras_aprovadas_lote += aprovadas
        total_leituras_icpoes_lote += flags_icpoes
        total_leituras_rsd_lote += flags_rsd
        
        resumo_elementos.append({
            'Elemento': elemento,
            'Amostras_Unicas': total_amostras_unicas,
            'Leituras_Aprovadas': int(aprovadas),
            'Flags_ICPOES': int(flags_icpoes),
            'Flags_RSD': int(flags_rsd),
            'Pct_Aprovadas': pct_aprovadas
        })
    
    df_resumo = pd.DataFrame(resumo_elementos)
    
    # Universo total = Total de linhas × Total de elementos
    universo_total = total_linhas * total_elementos_aprovados
    
    # Métricas de resumo do lote
    metricas_resumo = {
        'universo_total': universo_total,
        'leituras_aprovadas': int(total_leituras_aprovadas_lote),
        'leituras_icpoes': int(total_leituras_icpoes_lote),
        'leituras_rsd': int(total_leituras_rsd_lote),
        'total_amostras_unicas': total_amostras_unicas,
        'total_elementos_aprovados': total_elementos_aprovados,
        'total_linhas': total_linhas
    }
    
    return df_resumo, metricas_resumo


def criar_matriz_flags_por_leitura(df: pd.DataFrame, resultados_qc: Dict) -> tuple:
    """
    Cria matriz de flags por leitura individual para Raio-X de qualidade.
    
    Analisa cada leitura (linha) das Amostras de Interesse e conta quantos
    elementos químicos dispararam cada tipo de flag.
    
    ⚠️ GRANULARIDADE CORRETA: Leitura = Amostra × Elemento
    Universo de avaliação = N_amostras_únicas × N_elementos_aprovados
    
    Exemplo: 14 amostras × 32 elementos = 448 leituras possíveis
    
    ⚠️ IMPORTANTE: Considera apenas elementos aprovados na Etapa 1 (TR%).
    
    Args:
        df: DataFrame com dados processados
        resultados_qc: Resultados do QC
    
    Returns:
        Tupla (df_matriz, metricas_resumo) com:
        - df_matriz: DataFrame [Amostra, Qtd_Aprovadas, Qtd_ICPOES, Qtd_RSD, Qtd_LOD]
        - metricas_resumo: Dict com leituras (Amostra × Elemento)
    """
    # Filtrar apenas Amostras de Interesse
    if 'Tipo_Amostra' not in df.columns or 'Nome_Amostra' not in df.columns:
        return pd.DataFrame(), {
            'universo_total': 0,
            'leituras_aprovadas': 0,
            'leituras_icpoes': 0,
            'leituras_rsd': 0,
            'leituras_lod': 0,
            'total_amostras_unicas': 0,
            'total_elementos_aprovados': 0
        }
    
    df_amostras = df[df['Tipo_Amostra'] == 'Sample'].copy()
    df_amostras = df_amostras[
        df_amostras['Nome_Amostra'].astype(str).str[0].str.isdigit()
    ]
    
    if len(df_amostras) == 0:
        return pd.DataFrame(), {
            'universo_total': 0,
            'leituras_aprovadas': 0,
            'leituras_icpoes': 0,
            'leituras_rsd': 0,
            'leituras_lod': 0,
            'total_amostras_unicas': 0,
            'total_elementos_aprovados': 0
        }
    
    # Extrair base numérica para contabilizar amostras únicas
    def extrair_base(nome: str) -> str:
        nome_str = str(nome).strip()
        if len(nome_str) > 0 and nome_str[-1].isalpha():
            return nome_str[:-1]
        return nome_str
    
    df_amostras['Base_Amostra'] = df_amostras['Nome_Amostra'].apply(extrair_base)
    total_amostras_unicas = df_amostras['Base_Amostra'].nunique()
    
    # Identificar colunas de flags (apenas elementos aprovados)
    elementos_aprovados = resultados_qc.get('elementos_aprovados', [])
    total_elementos_aprovados = len(elementos_aprovados)
    
    # Calcular universo total: Amostras × Elementos
    universo_total = total_amostras_unicas * total_elementos_aprovados
    
    colunas_flag_icpoes = [f"{elem}_Flag_ICPOES" for elem in elementos_aprovados 
                           if f"{elem}_Flag_ICPOES" in df_amostras.columns]
    colunas_flag_rsd = [f"{elem}_Flag_RSD" for elem in elementos_aprovados 
                        if f"{elem}_Flag_RSD" in df_amostras.columns]
    colunas_flag_lod = [f"{elem}_Flag_LOD" for elem in elementos_aprovados 
                        if f"{elem}_Flag_LOD" in df_amostras.columns]
    
    # Construir matriz: linha por leitura (amostra individual)
    matriz = []
    
    # Contadores globais de leituras (Amostra × Elemento)
    total_leituras_icpoes = 0
    total_leituras_rsd = 0
    total_leituras_lod = 0
    
    for idx, row in df_amostras.iterrows():
        nome_amostra = row['Nome_Amostra']
        
        # Contar quantos elementos dispararam cada flag
        qtd_icpoes = 0
        qtd_rsd = 0
        qtd_lod = 0
        
        if len(colunas_flag_icpoes) > 0:
            qtd_icpoes = int(row[colunas_flag_icpoes].sum())
        
        if len(colunas_flag_rsd) > 0:
            qtd_rsd = int(row[colunas_flag_rsd].sum())
        
        if len(colunas_flag_lod) > 0:
            qtd_lod = int(row[colunas_flag_lod].sum())
        
        # Calcular aprovadas: elementos sem flags críticas
        # Total de elementos - (elementos com ICPOES ou RSD)
        # Nota: Um elemento pode ter ICPOES E RSD, precisamos contar união
        qtd_com_flags_criticas = 0
        
        if len(colunas_flag_icpoes) > 0 or len(colunas_flag_rsd) > 0:
            # Para cada elemento, verificar se tem qualquer flag crítica
            for elem in elementos_aprovados:
                col_icpoes = f"{elem}_Flag_ICPOES"
                col_rsd = f"{elem}_Flag_RSD"
                
                tem_flag = False
                
                if col_icpoes in df_amostras.columns and row[col_icpoes]:
                    tem_flag = True
                
                if col_rsd in df_amostras.columns and row[col_rsd]:
                    tem_flag = True
                
                if tem_flag:
                    qtd_com_flags_criticas += 1
        
        qtd_aprovadas = total_elementos_aprovados - qtd_com_flags_criticas
        
        # Acumular totais globais
        total_leituras_icpoes += qtd_icpoes
        total_leituras_rsd += qtd_rsd
        total_leituras_lod += qtd_lod
        
        matriz.append({
            'Amostra': nome_amostra,
            'Qtd_Aprovadas': qtd_aprovadas,
            'Qtd_ICPOES': qtd_icpoes,
            'Qtd_RSD': qtd_rsd,
            'Qtd_LOD': qtd_lod
        })
    
    df_matriz = pd.DataFrame(matriz)
    
    # Calcular total de leituras aprovadas
    # Aprovadas = Total de leituras - (ICPOES + RSD)
    # Nota: Preciso usar união (elemento pode ter ICPOES E RSD)
    total_leituras_aprovadas = int(df_matriz['Qtd_Aprovadas'].sum())
    
    # Métricas de resumo baseadas em leituras (Amostra × Elemento)
    metricas_resumo = {
        'universo_total': universo_total,
        'leituras_aprovadas': total_leituras_aprovadas,
        'leituras_icpoes': total_leituras_icpoes,
        'leituras_rsd': total_leituras_rsd,
        'leituras_lod': total_leituras_lod,
        'total_amostras_unicas': total_amostras_unicas,
        'total_elementos_aprovados': total_elementos_aprovados
    }
    
    return df_matriz, metricas_resumo


def calcular_porcentagem_flags(df: pd.DataFrame, resultados_qc: Dict) -> Dict:
    """
    Calcula porcentagem de amostras com flags ICPOES e RSD.
    
    Args:
        df: DataFrame com dados processados
        resultados_qc: Resultados do QC
    
    Returns:
        Dict com {
            'pct_icpoes': porcentagem,
            'pct_rsd': porcentagem,
            'n_amostras': total de amostras válidas
        }
    """
    # Filtrar apenas amostras reais
    if 'Tipo_Amostra' not in df.columns:
        return {'pct_icpoes': 0.0, 'pct_rsd': 0.0, 'n_amostras': 0}
    
    df_samples = df[df['Tipo_Amostra'] == 'Sample']
    n_amostras = len(df_samples)
    
    if n_amostras == 0:
        return {'pct_icpoes': 0.0, 'pct_rsd': 0.0, 'n_amostras': 0}
    
    # Contar amostras com flags
    colunas_icpoes = [col for col in df.columns if 'Flag_ICPOES' in col]
    colunas_rsd = [col for col in df.columns if 'Flag_RSD' in col]
    
    # Contar amostras que têm pelo menos uma flag em qualquer elemento
    amostras_com_icpoes = 0
    amostras_com_rsd = 0
    
    if len(colunas_icpoes) > 0:
        # Amostra tem flag ICPOES se qualquer coluna de ICPOES for True
        mask_icpoes = df_samples[colunas_icpoes].any(axis=1)
        amostras_com_icpoes = mask_icpoes.sum()
    
    if len(colunas_rsd) > 0:
        # Amostra tem flag RSD se qualquer coluna de RSD for True
        mask_rsd = df_samples[colunas_rsd].any(axis=1)
        amostras_com_rsd = mask_rsd.sum()
    
    # Calcular porcentagens
    pct_icpoes = (amostras_com_icpoes / n_amostras) * 100 if n_amostras > 0 else 0.0
    pct_rsd = (amostras_com_rsd / n_amostras) * 100 if n_amostras > 0 else 0.0
    
    return {
        'pct_icpoes': pct_icpoes,
        'pct_rsd': pct_rsd,
        'n_amostras': n_amostras,
        'n_com_icpoes': amostras_com_icpoes,
        'n_com_rsd': amostras_com_rsd
    }
