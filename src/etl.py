"""
Módulo ETL para Processamento de Dados ICP-MS

Este módulo contém a lógica de extração, transformação e carga (ETL) para 
análises de espectrometria de massa com plasma indutivamente acoplado (ICP-MS)
aplicadas a grãos de pólen.

Autor: Engenharia de Dados - Setor Ambiental
Data: 28 de fevereiro de 2026
Versão: 2.5.0 (Dynamic File Ingestion)
"""

import pandas as pd
import numpy as np
from datetime import datetime
from pathlib import Path
from typing import Dict, Tuple, Optional, List, Union
import re
import warnings
from io import BytesIO

warnings.filterwarnings('ignore', category=UserWarning)


class ICPMSDataProcessor:
    """
    Classe principal para processamento de dados ICP-MS.
    
    Esta classe implementa um pipeline ETL completo para:
    1. Carregar e processar cabeçalhos multinível de arquivos Excel
    2. Aplicar mapeamento de metadados para padronização
    3. Sanitizar e validar dados analíticos
    4. Filtrar registros rejeitados
    5. Converter tipos de dados apropriadamente
    
    Attributes:
        arquivo_original (Union[str, Path, object]): Caminho ou objeto de arquivo em memória
        arquivo_metadados (str): Caminho para o arquivo de dicionário de dados
        df_metadados (pd.DataFrame): DataFrame com metadados carregados
        mapeamento (Dict[str, str]): Dicionário de mapeamento nome_original → nome_padronizado
        df_processado (pd.DataFrame): DataFrame final processado
        log_processamento (List[str]): Lista de mensagens de log
        _is_uploaded_file (bool): Flag indicando se arquivo_original é um objeto em memória
    """
    
    def __init__(self, arquivo_original: Union[str, Path, object] = 'original.xlsx', 
                 arquivo_metadados: str = 'metadados.xlsx'):
        """
        Inicializa o processador de dados ICP-MS.
        
        Args:
            arquivo_original: Caminho (str/Path) ou objeto UploadedFile do Streamlit
            arquivo_metadados: Caminho para o arquivo Excel com metadados
        """
        # Inicializar atributos de estado ANTES de qualquer operação
        self.df_metadados = None
        self.mapeamento = None
        self.df_processado = None
        self.log_processamento = []  # DEVE ser inicializado primeiro!
        
        # Detectar se é um objeto de arquivo em memória (UploadedFile do Streamlit)
        self._is_uploaded_file = hasattr(arquivo_original, 'read') and hasattr(arquivo_original, 'name')
        
        if self._is_uploaded_file:
            # É um objeto UploadedFile - guardar referência direta
            self.arquivo_original = arquivo_original
            self._log(f"Arquivo em memória detectado: {arquivo_original.name}")
        else:
            # É um caminho de arquivo
            self.arquivo_original = Path(arquivo_original)
        
        self.arquivo_metadados = Path(arquivo_metadados)
        
        # Validar existência dos arquivos
        self._validar_arquivos()
        
    def _validar_arquivos(self) -> None:
        """Valida a existência dos arquivos de entrada."""
        # Validar arquivo original
        if not self._is_uploaded_file:
            # É um caminho - verificar se existe
            if not self.arquivo_original.exists():
                raise FileNotFoundError(f"Arquivo não encontrado: {self.arquivo_original}")
        else:
            # É um UploadedFile - verificar se tem conteúdo
            if self.arquivo_original.size == 0:
                raise ValueError(f"Arquivo vazio: {self.arquivo_original.name}")
        
        # Validar arquivo de metadados
        if not self.arquivo_metadados.exists():
            raise FileNotFoundError(f"Arquivo não encontrado: {self.arquivo_metadados}")
    
    def _log(self, mensagem: str) -> None:
        """
        Adiciona mensagem ao log de processamento.
        
        Args:
            mensagem: Texto da mensagem
        """
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.log_processamento.append(f"[{timestamp}] {mensagem}")
    
    def _normalizar_nome(self, nome: str) -> str:
        """
        Normaliza nome de coluna para matching robusto.
        
        Aplica:
        - Strip de espaços externos
        - Lowercase
        - Redução de espaços múltiplos para único espaço
        
        Args:
            nome: Nome original da coluna
        
        Returns:
            Nome normalizado
        """
        if not isinstance(nome, str):
            return str(nome).strip().lower()
        
        # Strip, lowercase e reduzir espaços múltiplos
        nome_limpo = nome.strip().lower()
        # Substituir múltiplos espaços por um único espaço
        nome_limpo = ' '.join(nome_limpo.split())
        
        return nome_limpo
    
    def carregar_metadados(self) -> pd.DataFrame:
        """
        Carrega e processa o arquivo de metadados.
        
        Aplica sanitização conforme diretrizes:
        - Remove espaços em branco extras (strip)
        - Converte para minúsculas (case-insensitive matching)
        - Remove colunas vazias (Unnamed)
        
        Returns:
            DataFrame com metadados processados
        """
        self._log("Iniciando carregamento de metadados...")
        
        # Carregar arquivo
        df_meta = pd.read_excel(self.arquivo_metadados)
        
        # Remover colunas completamente vazias
        df_meta = df_meta.loc[:, ~df_meta.columns.str.contains('Unnamed')]
        
        # Sanitização: strip, lowercase e normalizar espaços
        if 'Nome Original na Planilha' in df_meta.columns:
            df_meta['Nome Original na Planilha'] = (
                df_meta['Nome Original na Planilha']
                .astype(str)
                .apply(self._normalizar_nome)
            )
        
        # Sanitização do nome padronizado
        if 'Nome Padronizado' in df_meta.columns:
            df_meta['Nome Padronizado'] = (
                df_meta['Nome Padronizado']
                .astype(str)
                .str.strip()
            )
        
        self.df_metadados = df_meta
        self._log(f"✓ Metadados carregados: {len(df_meta)} registros")
        
        return df_meta
    
    def criar_mapeamento(self) -> Dict[str, str]:
        """
        Cria dicionário de mapeamento entre nomes originais e padronizados.
        
        O mapeamento utiliza chaves sanitizadas (lowercase, strip) para
        garantir correspondência robusta.
        
        IMPORTANTE: Cria mapeamentos compostos para Conc/RSD:
        - '27 al [ no gas ]' → 'Al_NoGas' (base)
        - '27 al [ no gas ] conc' → 'Al_NoGas_Conc' (com sufixo)
        - '27 al [ no gas ] rsd' → 'Al_NoGas_RSD' (com sufixo)
        
        Returns:
            Dicionário {nome_original_sanitizado: nome_padronizado}
        """
        if self.df_metadados is None:
            self.carregar_metadados()
        
        # Criar mapeamento base
        mapeamento_base = dict(zip(
            self.df_metadados['Nome Original na Planilha'],
            self.df_metadados['Nome Padronizado']
        ))
        
        # Expandir mapeamento para incluir sufixos Conc e RSD
        self.mapeamento = {}
        
        for nome_original, nome_padronizado in mapeamento_base.items():
            # Mapeamento base (sem sufixo)
            self.mapeamento[nome_original] = nome_padronizado
            
            # Mapeamento com sufixo Conc
            self.mapeamento[f"{nome_original} conc"] = f"{nome_padronizado}_Conc"
            
            # Mapeamento com sufixo RSD
            self.mapeamento[f"{nome_original} rsd"] = f"{nome_padronizado}_RSD"
        
        self._log(f"✓ Mapeamento criado: {len(mapeamento_base)} elementos × 3 variantes = {len(self.mapeamento)} mapeamentos")
        
        return self.mapeamento
    
    def _combinar_cabecalho_multinivel(self, colunas_multi: pd.MultiIndex) -> List[str]:
        """
        Combina cabeçalho multinível em nomes de coluna únicos.
        
        Estratégia:
        - Para colunas de metadados (grupo 'Sample'): usa apenas o nível 1
        - Para colunas de elementos químicos: combina 'Elemento + Medida'
        
        Exemplo:
            ('27 Al [ No Gas ]', 'Conc. [ ug/l ]') → '27 Al [ No Gas ] Conc'
            ('Sample', 'Rjct') → 'Rjct'
        
        Args:
            colunas_multi: MultiIndex com dois níveis do pandas
        
        Returns:
            Lista de strings com nomes de colunas combinados
        """
        colunas_combinadas = []
        
        for nivel0, nivel1 in colunas_multi:
            # Se for coluna do grupo 'Sample', usar apenas o segundo nível
            if nivel0 == 'Sample':
                # Pular colunas 'Unnamed'
                if 'Unnamed' in str(nivel1):
                    colunas_combinadas.append('_index_')  # Será dropado depois
                else:
                    colunas_combinadas.append(nivel1)
            else:
                # Para elementos químicos, combinar elemento + tipo de medida
                # Extrair apenas a parte relevante da medida
                if 'Conc.' in nivel1 and 'RSD' not in nivel1:
                    medida = 'Conc'
                elif 'RSD' in nivel1:
                    medida = 'RSD'
                else:
                    medida = nivel1
                
                # Combinar: elemento + medida
                nome_combinado = f"{nivel0} {medida}".strip()
                colunas_combinadas.append(nome_combinado)
        
        return colunas_combinadas
    
    def carregar_dados_brutos(self) -> pd.DataFrame:
        """
        Carrega arquivo original com dados ICP-MS.
        
        Resolve o desafio do cabeçalho multinível:
        1. Lê com header=[0,1] para capturar ambos os níveis
        2. Combina os níveis em nomes únicos
        3. Aplica sanitização (strip, lowercase)
        
        Suporta:
        - Arquivos locais (Path)
        - Arquivos em memória (UploadedFile do Streamlit)
        
        Returns:
            DataFrame com dados brutos e colunas nomeadas
        """
        self._log("Iniciando carregamento de dados brutos...")
        
        # Ler com cabeçalho multinível
        if self._is_uploaded_file:
            # Arquivo em memória - ler do objeto UploadedFile
            # Resetar ponteiro para o início do arquivo
            self.arquivo_original.seek(0)
            df = pd.read_excel(self.arquivo_original, header=[0, 1])
            self._log(f"✓ Arquivo em memória carregado: {self.arquivo_original.name}")
        else:
            # Arquivo local - ler do caminho
            df = pd.read_excel(self.arquivo_original, header=[0, 1])
            self._log(f"✓ Arquivo local carregado: {self.arquivo_original}")
        
        self._log(f"✓ Arquivo carregado: {df.shape[0]} linhas × {df.shape[1]} colunas")
        
        # Combinar cabeçalho multinível
        colunas_combinadas = self._combinar_cabecalho_multinivel(df.columns)
        df.columns = colunas_combinadas
        
        # Remover coluna de índice se existir
        if '_index_' in df.columns:
            df = df.drop(columns=['_index_'])
        
        # Sanitização dos nomes de colunas (normalizar espaços)
        df.columns = [self._normalizar_nome(col) for col in df.columns]
        
        self._log(f"✓ Cabeçalho processado: {len(df.columns)} colunas válidas")
        
        return df
    
    def aplicar_mapeamento(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Aplica mapeamento de metadados para renomear colunas.
        
        Colunas que não existem no mapeamento são mantidas com nome original.
        
        Args:
            df: DataFrame com nomes de colunas originais (sanitizados)
        
        Returns:
            DataFrame com colunas renomeadas
        """
        if self.mapeamento is None:
            self.criar_mapeamento()
        
        # Renomear apenas colunas que existem no mapeamento
        colunas_renomeadas = {
            col: self.mapeamento.get(col, col)
            for col in df.columns
        }
        
        df_renomeado = df.rename(columns=colunas_renomeadas)
        
        # Contar quantas colunas foram mapeadas
        n_mapeadas = sum(1 for col in df.columns if col in self.mapeamento)
        
        self._log(f"✓ Mapeamento aplicado: {n_mapeadas} colunas renomeadas")
        
        return df_renomeado
    
    def filtrar_rejeitados(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Remove registros marcados como rejeitados (Rjct = True).
        
        Args:
            df: DataFrame com coluna 'rjct' ou similar
        
        Returns:
            DataFrame filtrado
        """
        # Procurar coluna de rejeição (case-insensitive)
        coluna_rjct = None
        for col in df.columns:
            if 'rjct' in col.lower() or 'reject' in col.lower():
                coluna_rjct = col
                break
        
        if coluna_rjct is None:
            self._log("⚠ Coluna 'Rjct' não encontrada - filtro não aplicado")
            return df
        
        # Contar rejeitados antes do filtro
        if df[coluna_rjct].dtype == bool:
            n_rejeitados = df[coluna_rjct].sum()
        else:
            # Converter para bool se necessário
            n_rejeitados = df[coluna_rjct].astype(str).str.lower().isin(['true', '1', 'yes']).sum()
        
        # Filtrar
        if df[coluna_rjct].dtype == bool:
            df_filtrado = df[df[coluna_rjct] == False].copy()
        else:
            df_filtrado = df[~df[coluna_rjct].astype(str).str.lower().isin(['true', '1', 'yes'])].copy()
        
        self._log(f"✓ Filtro aplicado: {n_rejeitados} registros rejeitados removidos")
        self._log(f"  Registros válidos: {len(df_filtrado)}")
        
        return df_filtrado
    
    def _limpar_valor_analitico(self, valor) -> Tuple[Optional[float], bool]:
        """
        Converte valor analítico para float, tratando casos especiais.
        
        IMPORTANTE: Valores com "<" (abaixo do limite de detecção) agora:
        - PRESERVAM o valor numérico (ex: "< 0.001" → 0.001)
        - Retornam flag=True para indicar que era "< LOD"
        
        Valores vazios ou não numéricos:
        - Retornam (NaN, False)
        
        Args:
            valor: Valor a ser convertido
        
        Returns:
            Tuple (valor_numerico, flag_menor_que_LOD)
            - valor_numerico: float ou NaN
            - flag_menor_que_LOD: True se tinha "<", False caso contrário
        """
        if pd.isna(valor):
            return (np.nan, False)
        
        if isinstance(valor, (int, float)):
            return (float(valor), False)
        
        # Converter string
        valor_str = str(valor).strip()
        
        # Detectar se tem símbolo "<" (menor que)
        if '<' in valor_str:
            # Extrair apenas o valor numérico
            # Exemplos: "< 0.001" → 0.001, "<0.5" → 0.5, "< LOD" → NaN
            valor_limpo = valor_str.replace('<', '').replace('LOD', '').strip()
            try:
                valor_numerico = float(valor_limpo)
                return (valor_numerico, True)  # Flag=True indica "< LOD"
            except (ValueError, TypeError):
                # Se não conseguir extrair número (ex: "< LOD" sem valor)
                return (np.nan, True)
        
        # Padrões que indicam valor não detectável SEM número
        valor_upper = valor_str.upper()
        padroes_nd = ['ND', 'N.D.', 'BLD', 'N/A', 'NA']
        
        if any(padrao == valor_upper for padrao in padroes_nd):
            return (np.nan, False)
        
        # Tentar converter para float
        try:
            return (float(valor_str), False)
        except (ValueError, TypeError):
            return (np.nan, False)
    
    def sanitizar_valores_analiticos(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Aplica limpeza em colunas de concentração.
        
        Identifica colunas numéricas (concentrações, RSD) e aplica conversão
        robusta para float, tratando valores problemáticos.
        
        NOVO: Cria colunas de flag para valores que eram "< LOD"
        Exemplo: Se 'Al_NoGas_Conc' tinha "< 0.001", cria 'Al_NoGas_Conc_Flag_LOD'
        
        Args:
            df: DataFrame com dados
        
        Returns:
            DataFrame com valores numéricos limpos e colunas de flag
        """
        self._log("Iniciando sanitização de valores analíticos...")
        
        # Identificar colunas de concentração/RSD (numéricas)
        colunas_concentracao = []
        
        for col in df.columns:
            col_lower = col.lower()
            # Identificar colunas de concentração e RSD
            if any(termo in col_lower for termo in ['conc', 'rsd', 'cps', 'ppb', 'ug/l']):
                colunas_concentracao.append(col)
        
        # Aplicar limpeza e coletar flags (otimização: criar todas as colunas de uma vez)
        colunas_flag_dict = {}
        n_valores_com_flag = 0
        
        for col in colunas_concentracao:
            # Aplicar limpeza (retorna tupla: valor, flag)
            resultados = df[col].apply(self._limpar_valor_analitico)
            
            # Separar valores e flags
            df[col] = resultados.apply(lambda x: x[0])
            flags = resultados.apply(lambda x: x[1])
            
            # Coletar flags se houver algum valor com "<"
            if flags.any():
                nome_flag = f"{col}_Flag_LOD"
                colunas_flag_dict[nome_flag] = flags
                n_valores_com_flag += flags.sum()
                self._log(f"  ✓ '{col}': {flags.sum()} valores < LOD detectados")
        
        # Adicionar todas as colunas de flag de uma vez (otimização de performance)
        if colunas_flag_dict:
            df_flags = pd.DataFrame(colunas_flag_dict, index=df.index)
            df = pd.concat([df, df_flags], axis=1)
        
        self._log(f"✓ Sanitização concluída:")
        self._log(f"  • {len(colunas_concentracao)} colunas analíticas processadas")
        self._log(f"  • {n_valores_com_flag} valores < LOD preservados com flag")
        self._log(f"  • {len(colunas_flag_dict)} colunas de flag criadas")
        
        return df
    
    def converter_tipos(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Converte tipos de dados apropriadamente.
        
        - Datas → datetime
        - Concentrações → float
        - Identificadores → string
        
        Args:
            df: DataFrame com dados
        
        Returns:
            DataFrame com tipos corretos
        """
        self._log("Aplicando conversão de tipos...")
        
        # Identificar e converter colunas de data
        for col in df.columns:
            col_lower = col.lower()
            
            # Datas
            if 'date' in col_lower or 'data' in col_lower:
                try:
                    df[col] = pd.to_datetime(df[col], errors='coerce')
                    self._log(f"  ✓ '{col}' → datetime")
                except Exception as e:
                    self._log(f"  ⚠ Erro ao converter '{col}': {e}")
            
            # Garantir que concentrações sejam float
            elif any(termo in col_lower for termo in ['conc', 'rsd', 'cps']):
                df[col] = pd.to_numeric(df[col], errors='coerce')
        
        return df
    
    def obter_estatisticas(self, df: pd.DataFrame) -> Dict:
        """
        Calcula estatísticas descritivas do dataset.
        
        Args:
            df: DataFrame processado
        
        Returns:
            Dicionário com estatísticas
        """
        # Identificar colunas de concentração
        colunas_conc = [col for col in df.columns if 'conc' in col.lower()]
        
        stats = {
            'n_amostras': len(df),
            'n_colunas': len(df.columns),
            'n_colunas_concentracao': len(colunas_conc),
            'data_processamento': datetime.now().strftime('%d/%m/%Y %H:%M:%S'),
            'valores_faltantes': df[colunas_conc].isna().sum().sum() if colunas_conc else 0,
            'percentual_completude': (
                100 * (1 - df[colunas_conc].isna().sum().sum() / (len(df) * len(colunas_conc)))
                if colunas_conc else 0
            )
        }
        
        return stats
    
    def processar(self, aplicar_filtro_rjct: bool = True) -> pd.DataFrame:
        """
        Executa pipeline ETL completo.
        
        Fluxo:
        1. Carregar metadados
        2. Criar mapeamento
        3. Carregar dados brutos
        4. Aplicar mapeamento de nomes
        5. Filtrar registros rejeitados (opcional)
        6. Sanitizar valores analíticos
        7. Converter tipos de dados
        
        Args:
            aplicar_filtro_rjct: Se True, remove registros com Rjct=True
        
        Returns:
            DataFrame processado e limpo
        """
        self._log("="*60)
        self._log("INICIANDO PIPELINE ETL - ICP-MS DATA PROCESSOR")
        self._log("="*60)
        
        # 1. Carregar metadados
        self.carregar_metadados()
        
        # 2. Criar mapeamento
        self.criar_mapeamento()
        
        # 3. Carregar dados brutos
        df = self.carregar_dados_brutos()
        
        # 4. Aplicar mapeamento
        df = self.aplicar_mapeamento(df)
        
        # 5. Filtrar rejeitados (se solicitado)
        if aplicar_filtro_rjct:
            df = self.filtrar_rejeitados(df)
        
        # 6. Sanitizar valores analíticos
        df = self.sanitizar_valores_analiticos(df)
        
        # 7. Converter tipos
        df = self.converter_tipos(df)
        
        # 8. Calcular estatísticas
        stats = self.obter_estatisticas(df)
        
        self._log("="*60)
        self._log("PIPELINE CONCLUÍDO COM SUCESSO")
        self._log(f"  • Amostras processadas: {stats['n_amostras']}")
        self._log(f"  • Colunas no dataset: {stats['n_colunas']}")
        self._log(f"  • Colunas de concentração: {stats['n_colunas_concentracao']}")
        self._log(f"  • Completude dos dados: {stats['percentual_completude']:.1f}%")
        self._log("="*60)
        
        self.df_processado = df
        return df
    
    def exportar_log(self, caminho: str = 'etl_log.txt') -> None:
        """
        Exporta log de processamento para arquivo texto.
        
        Args:
            caminho: Caminho do arquivo de saída
        """
        with open(caminho, 'w', encoding='utf-8') as f:
            f.write('\n'.join(self.log_processamento))
    
    def exportar_processado(self, caminho: str = 'dados_processados.xlsx') -> None:
        """
        Exporta dados processados para Excel.
        
        Args:
            caminho: Caminho do arquivo de saída
        """
        if self.df_processado is None:
            raise ValueError("Nenhum dado foi processado ainda. Execute .processar() primeiro.")
        
        self.df_processado.to_excel(caminho, index=False)
        self._log(f"✓ Dados exportados: {caminho}")


# Funções auxiliares para uso direto
def processar_dados_icpms(arquivo_original: str = 'original.xlsx',
                          arquivo_metadados: str = 'metadados.xlsx',
                          aplicar_filtro_rjct: bool = True) -> Tuple[pd.DataFrame, List[str]]:
    """
    Função de conveniência para processar dados ICP-MS em uma única chamada.
    
    Args:
        arquivo_original: Caminho para dados brutos
        arquivo_metadados: Caminho para metadados
        aplicar_filtro_rjct: Se True, remove registros rejeitados
    
    Returns:
        Tuple contendo (DataFrame processado, lista de mensagens de log)
    
    Example:
        >>> df, log = processar_dados_icpms()
        >>> print(f"Processadas {len(df)} amostras")
    """
    processor = ICPMSDataProcessor(arquivo_original, arquivo_metadados)
    df_processado = processor.processar(aplicar_filtro_rjct=aplicar_filtro_rjct)
    
    return df_processado, processor.log_processamento


class QualityControlEngine:
    """
    Motor de Validação de Qualidade (QC) para dados ICP-MS.
    
    Implementa as regras de química analítica:
    - Escolha de curva de calibração (A vs B)
    - Taxa de Recuperação (TR) com padrões Merck
    - Validação de amostras (Flags ICPOES e RSD)
    
    Attributes:
        df_processado (pd.DataFrame): DataFrame com dados processados
        elementos (List[str]): Lista de elementos químicos analisados
        curvas_escolhidas (Dict): Curva escolhida para cada elemento
        resultados_tr (Dict): Resultados de Taxa de Recuperação
        flags_geradas (Dict): Contadores de flags geradas
        log_qc (List[str]): Log de mensagens do QC
    """
    
    def __init__(self, df_processado: pd.DataFrame):
        """
        Inicializa o Motor de QC.
        
        Args:
            df_processado: DataFrame processado pelo ICPMSDataProcessor
        """
        self.df_processado = df_processado.copy()
        self.elementos = self._identificar_elementos()
        self.curvas_escolhidas = {}
        self.resultados_tr = {}
        self.flags_geradas = {'ICPOES': 0, 'RSD': 0, 'TR_Reprovado': 0}
        self.log_qc = []
        
    def _log(self, mensagem: str) -> None:
        """Adiciona mensagem ao log de QC."""
        timestamp = datetime.now().strftime('%H:%M:%S')
        self.log_qc.append(f"[{timestamp}] {mensagem}")
    
    def _identificar_elementos(self) -> List[str]:
        """
        Identifica elementos químicos analisados (colunas _Conc).
        
        Returns:
            Lista de nomes base dos elementos (ex: 'Al_NoGas', 'V_He')
        """
        elementos = []
        for col in self.df_processado.columns:
            if '_Conc' in col and '_Flag' not in col:
                # Remover sufixo '_Conc'
                elemento_base = col.replace('_Conc', '')
                elementos.append(elemento_base)
        
        return elementos
    
    def escolher_curva_calibracao(self, elemento: str) -> Dict:
        """
        Escolhe a melhor curva de calibração (A ou B) para um elemento.
        
        Lógica:
        - Isola amostras CalStd (P0, P1A-P6A, P1B-P7B)
        - Avalia qual série forma curva ascendente válida
        - Retorna a curva escolhida com P0, último ponto e série
        
        Args:
            elemento: Nome base do elemento (ex: 'Al_NoGas')
        
        Returns:
            Dict com {
                'serie': 'A' ou 'B',
                'p0': valor do P0,
                'p_max': valor do último ponto (P6A ou P7B),
                'nome_p_max': 'P6A' ou 'P7B',
                'valida': True/False
            }
        """
        col_conc = f"{elemento}_Conc"
        
        # Verificar se coluna existe
        if col_conc not in self.df_processado.columns:
            self._log(f"⚠ Coluna '{col_conc}' não encontrada")
            return None
        
        # Verificar se existe coluna Tipo_Amostra
        if 'Tipo_Amostra' not in self.df_processado.columns:
            self._log(f"⚠ Coluna 'Tipo_Amostra' não encontrada")
            return None
        
        # Filtrar CalStd
        df_calstd = self.df_processado[
            self.df_processado['Tipo_Amostra'] == 'CalStd'
        ].copy()
        
        if len(df_calstd) == 0:
            self._log(f"⚠ Nenhuma amostra CalStd encontrada para {elemento}")
            return None
        
        # Obter P0
        p0_row = df_calstd[df_calstd['Nome_Amostra'].str.contains('P0', case=False, na=False)]
        p0_valor = p0_row[col_conc].iloc[0] if len(p0_row) > 0 else np.nan
        
        # Verificar Série A (P1A a P6A)
        pontos_a = ['P1A', 'P2A', 'P3A', 'P4A', 'P5A', 'P6A']
        valores_a = []
        
        for ponto in pontos_a:
            row = df_calstd[df_calstd['Nome_Amostra'].str.contains(ponto, case=False, na=False)]
            if len(row) > 0:
                valores_a.append(row[col_conc].iloc[0])
            else:
                valores_a.append(np.nan)
        
        # Verificar Série B (P1B a P7B)
        pontos_b = ['P1B', 'P2B', 'P3B', 'P4B', 'P5B', 'P6B', 'P7B']
        valores_b = []
        
        for ponto in pontos_b:
            row = df_calstd[df_calstd['Nome_Amostra'].str.contains(ponto, case=False, na=False)]
            if len(row) > 0:
                valores_b.append(row[col_conc].iloc[0])
            else:
                valores_b.append(np.nan)
        
        # Avaliar qual série é ascendente e válida
        # Remove NaN para avaliação
        valores_a_validos = [v for v in valores_a if not pd.isna(v)]
        valores_b_validos = [v for v in valores_b if not pd.isna(v)]
        
        # Verificar se é ascendente (cada valor > anterior)
        def is_ascendente(valores):
            if len(valores) < 2:
                return False
            for i in range(1, len(valores)):
                if valores[i] <= valores[i-1]:
                    return False
            return True
        
        a_ascendente = is_ascendente(valores_a_validos)
        b_ascendente = is_ascendente(valores_b_validos)
        
        # Escolher melhor curva
        if b_ascendente and len(valores_b_validos) >= len(valores_a_validos):
            # Preferir B se tiver mais pontos ou ambas forem válidas
            return {
                'serie': 'B',
                'p0': p0_valor,
                'p_max': valores_b[-1] if len(valores_b) > 0 else np.nan,
                'nome_p_max': 'P7B',
                'valida': True
            }
        elif a_ascendente:
            return {
                'serie': 'A',
                'p0': p0_valor,
                'p_max': valores_a[-1] if len(valores_a) > 0 else np.nan,
                'nome_p_max': 'P6A',
                'valida': True
            }
        else:
            # Nenhuma curva válida
            return {
                'serie': None,
                'p0': p0_valor,
                'p_max': np.nan,
                'nome_p_max': None,
                'valida': False
            }
    
    def calcular_taxa_recuperacao(self, elemento: str) -> Dict:
        """
        Calcula Taxa de Recuperação (TR%) usando padrões Merck.
        
        TR% = (Média_Concentração * 100) / Valor_Esperado
        Válido se 90% <= TR% <= 110%
        
        Args:
            elemento: Nome base do elemento
        
        Returns:
            Dict com {
                'tr_50': TR% para Merck50 (50mg),
                'tr_200': TR% para Merck200 (200mg),
                'valido_50': True/False,
                'valido_200': True/False,
                'aprovado': True se ambos válidos
            }
        """
        col_conc = f"{elemento}_Conc"
        
        if col_conc not in self.df_processado.columns:
            return None
        
        # Filtrar amostras Merck
        df_merck = self.df_processado[
            self.df_processado['Nome_Amostra'].str.contains('Merck', case=False, na=False)
        ]
        
        if len(df_merck) == 0:
            return None
        
        # Merck50 (triplicatas A, B, C)
        merck50 = df_merck[
            df_merck['Nome_Amostra'].str.contains('Merck50', case=False, na=False)
        ]
        media_50 = merck50[col_conc].mean() if len(merck50) > 0 else np.nan
        tr_50 = (media_50 * 100) / 50 if not pd.isna(media_50) else np.nan
        valido_50 = 90 <= tr_50 <= 110 if not pd.isna(tr_50) else False
        
        # Merck200 (triplicatas A, B, C)
        merck200 = df_merck[
            df_merck['Nome_Amostra'].str.contains('Merck200', case=False, na=False)
        ]
        media_200 = merck200[col_conc].mean() if len(merck200) > 0 else np.nan
        tr_200 = (media_200 * 100) / 200 if not pd.isna(media_200) else np.nan
        valido_200 = 90 <= tr_200 <= 110 if not pd.isna(tr_200) else False
        
        # Elemento aprovado se ambos TR forem válidos
        aprovado = valido_50 and valido_200
        
        return {
            'tr_50': tr_50,
            'tr_200': tr_200,
            'media_50': media_50,
            'media_200': media_200,
            'valido_50': valido_50,
            'valido_200': valido_200,
            'aprovado': aprovado
        }
    
    def validar_amostras_reais(self, elemento: str, curva_info: Dict) -> pd.DataFrame:
        """
        Valida amostras reais aplicando flags ICPOES e RSD.
        
        FLAG ICPOES: Concentração > P_max da curva
        FLAG RSD: RSD acima do tolerado (15% perto de P0, 10% acima)
        
        Args:
            elemento: Nome base do elemento
            curva_info: Informações da curva de calibração
        
        Returns:
            DataFrame com colunas de flags adicionadas
        """
        if not curva_info or not curva_info['valida']:
            return self.df_processado
        
        col_conc = f"{elemento}_Conc"
        col_rsd = f"{elemento}_RSD"
        col_flag_icpoes = f"{elemento}_Flag_ICPOES"
        col_flag_rsd = f"{elemento}_Flag_RSD"
        
        # Verificar se colunas existem
        if col_conc not in self.df_processado.columns:
            return self.df_processado
        
        # Filtrar apenas amostras reais (Tipo_Amostra == 'Sample')
        mask_sample = self.df_processado['Tipo_Amostra'] == 'Sample'
        
        # FLAG ICPOES: Conc > P_max
        p_max = curva_info['p_max']
        self.df_processado[col_flag_icpoes] = False
        
        if not pd.isna(p_max):
            self.df_processado.loc[mask_sample, col_flag_icpoes] = (
                self.df_processado.loc[mask_sample, col_conc] > p_max
            )
            n_icpoes = self.df_processado[col_flag_icpoes].sum()
            self.flags_geradas['ICPOES'] += n_icpoes
        
        # FLAG RSD: Verificar RSD conforme proximidade do P0
        if col_rsd in self.df_processado.columns:
            p0 = curva_info['p0']
            self.df_processado[col_flag_rsd] = False
            
            if not pd.isna(p0):
                # Calcular margem de 10% do P0
                margem_p0 = p0 * 1.1
                
                # Amostras próximas ao P0: RSD max = 15%
                mask_proximo_p0 = (
                    mask_sample & 
                    (self.df_processado[col_conc] <= margem_p0)
                )
                self.df_processado.loc[mask_proximo_p0, col_flag_rsd] = (
                    self.df_processado.loc[mask_proximo_p0, col_rsd] > 15
                )
                
                # Amostras acima do P0: RSD max = 10%
                mask_acima_p0 = (
                    mask_sample & 
                    (self.df_processado[col_conc] > margem_p0)
                )
                self.df_processado.loc[mask_acima_p0, col_flag_rsd] = (
                    self.df_processado.loc[mask_acima_p0, col_rsd] > 10
                )
                
                n_rsd = self.df_processado[col_flag_rsd].sum()
                self.flags_geradas['RSD'] += n_rsd
        
        return self.df_processado
    
    def executar_qc_completo(self) -> Tuple[pd.DataFrame, Dict]:
        """
        Executa o controle de qualidade completo para todos os elementos.
        
        Fluxo:
        1. Para cada elemento, escolhe curva de calibração
        2. Calcula Taxa de Recuperação
        3. Valida amostras reais (flags)
        4. Gera relatório resumido
        
        Returns:
            Tuple (DataFrame com flags, Dict com resultados QC)
        """
        self._log("="*60)
        self._log("INICIANDO CONTROLE DE QUALIDADE (QC)")
        self._log("="*60)
        
        resultados_qc = {
            'curvas': {},
            'tr': {},
            'elementos_aprovados': [],
            'elementos_reprovados': [],
            'flags': self.flags_geradas
        }
        
        for elemento in self.elementos:
            self._log(f"\nProcessando elemento: {elemento}")
            
            # 1. Escolher curva
            curva_info = self.escolher_curva_calibracao(elemento)
            if curva_info:
                self.curvas_escolhidas[elemento] = curva_info
                resultados_qc['curvas'][elemento] = curva_info
                
                if curva_info['valida']:
                    self._log(f"  ✓ Curva {curva_info['serie']} escolhida")
                    self._log(f"    P0: {curva_info['p0']:.4f}, {curva_info['nome_p_max']}: {curva_info['p_max']:.4f}")
                else:
                    self._log(f"  ⚠ Nenhuma curva válida encontrada")
            
            # 2. Calcular TR
            tr_info = self.calcular_taxa_recuperacao(elemento)
            if tr_info:
                self.resultados_tr[elemento] = tr_info
                resultados_qc['tr'][elemento] = tr_info
                
                if tr_info['aprovado']:
                    resultados_qc['elementos_aprovados'].append(elemento)
                    self._log(f"  ✓ TR Aprovado: 50mg={tr_info['tr_50']:.1f}%, 200mg={tr_info['tr_200']:.1f}%")
                else:
                    resultados_qc['elementos_reprovados'].append(elemento)
                    self.flags_geradas['TR_Reprovado'] += 1
                    self._log(f"  ✗ TR Reprovado: 50mg={tr_info['tr_50']:.1f}%, 200mg={tr_info['tr_200']:.1f}%")
            
            # 3. Validar amostras reais
            if curva_info and curva_info['valida']:
                self.df_processado = self.validar_amostras_reais(elemento, curva_info)
        
        self._log("="*60)
        self._log("CONTROLE DE QUALIDADE CONCLUÍDO")
        self._log(f"  • Elementos Aprovados: {len(resultados_qc['elementos_aprovados'])}")
        self._log(f"  • Elementos Reprovados: {len(resultados_qc['elementos_reprovados'])}")
        self._log(f"  • Flags ICPOES: {self.flags_geradas['ICPOES']}")
        self._log(f"  • Flags RSD: {self.flags_geradas['RSD']}")
        self._log("="*60)
        
        return self.df_processado, resultados_qc


if __name__ == "__main__":
    # Exemplo de uso standalone
    print("Processador de Dados ICP-MS")
    print("-" * 60)
    
    try:
        processor = ICPMSDataProcessor()
        df = processor.processar()
        
        print("\n📊 RESUMO DO PROCESSAMENTO:")
        print(f"  • Amostras: {len(df)}")
        print(f"  • Variáveis: {len(df.columns)}")
        print(f"\n🔍 Primeiras colunas:")
        print(f"  {list(df.columns[:10])}")
        
        print("\n✅ Processamento concluído com sucesso!")
        print("\nPara exportar:")
        print("  processor.exportar_processado('dados_limpos.xlsx')")
        print("  processor.exportar_log('processamento.log')")
        
    except Exception as e:
        print(f"\n❌ Erro durante processamento: {e}")
        import traceback
        traceback.print_exc()
