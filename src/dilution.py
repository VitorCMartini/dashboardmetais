"""
Módulo de Diluição e Fator de Diluição Total (FDT)
==================================================
Calcula, a partir das massas pesadas no laboratório, os fatores de diluição
que convertem a concentração lida no ICP-MS (µg/L) para mg/kg na matriz sólida.

    FDT          = FD1 × FD2
    FD1          = massa da solução ÷ massa da amostra pesada (micro-ondas)
    FD2          = (H2O − frasco vazio) ÷ (alíquota − frasco vazio)   (~2,5x pólen, ~5x MPA)
    FDT (mg/kg)  = FDT ÷ 1000        ← fator final
    resultado_mg/kg = conc_µg/L × FDT(mg/kg)

O cálculo é parametrizado por MATRIZ. Hoje: 'polen' e 'mpa'. As matrizes
'chamine' e 'mel' são ganchos (NotImplementedError) para evolução futura.

Fonte das fórmulas: planilhas-modelo do laboratório
('Massas amostras - Polen', 'Massas amostras - MPA'), abas FD1 / FD2 / FDT.

Autor: Engenharia de Dados - Setor Ambiental
Versão: 1.0.0
"""

import re
import numpy as np
import pandas as pd
from io import BytesIO
from typing import Dict, List, Tuple, Optional


# ============================================================
# HELPERS INTERNOS
# ============================================================
def _norm(texto) -> str:
    """Normaliza um rótulo de coluna: strip, lowercase, espaços únicos."""
    return re.sub(r"\s+", " ", str(texto).strip().lower())


def _col(df: pd.DataFrame, *termos: str) -> str:
    """Retorna o nome da 1ª coluna cujo cabeçalho (normalizado) contém um dos termos."""
    cols = {c: _norm(c) for c in df.columns}
    for termo in termos:
        tn = _norm(termo)
        for c, cn in cols.items():
            if tn in cn:
                return c
    raise KeyError(
        f"Coluna não encontrada (termos {termos}). Disponíveis: {list(df.columns)}"
    )


def _num(serie: pd.Series) -> pd.Series:
    """Converte para float, tolerando vírgula decimal (padrão brasileiro)."""
    if serie.dtype.kind in "biufc":
        return serie.astype(float)
    return pd.to_numeric(
        serie.astype(str).str.replace(",", ".", regex=False).str.strip(),
        errors="coerce",
    )


# ============================================================
# NORMALIZAÇÃO DE IDENTIFICADORES (matching concentração ↔ massas)
# ============================================================
def normalizar_id(nome) -> str:
    """
    Gera uma chave canônica para casar nomes de amostra entre a tabela de
    concentrações (ICP-MS) e a tabela de massas/FDT.

    Regras (derivadas dos dados reais do laboratório):
    - Lote: remove prefixo 'PQ25-'/'PQ26-'  → 'PQ25-1009A' vira '1009A'
    - NIST: 'Nist2A', 'Nist2B', 'NIST 2', 'MIT REF NIST 2' → 'NIST2'
            (réplicas de leitura compartilham a mesma digestão/FDT)
    - Branco: 'B4', 'Branco 4', 'BRANCO 4' → 'BRANCO4'
    - Interesse: mantém a réplica ('1009A' permanece '1009A')
    """
    if nome is None or (isinstance(nome, float) and pd.isna(nome)):
        return ""
    s = str(nome).strip().upper()
    s = re.sub(r"^PQ\d+\s*-\s*", "", s)          # remove prefixo de lote
    s = re.sub(r"\s+", " ", s).strip()

    m = re.search(r"NIST\s*0*(\d+)", s)          # NIST<n> (ignora letra de réplica)
    if m:
        return f"NIST{int(m.group(1))}"

    m = re.fullmatch(r"(?:B|BRANCO)\s*0*(\d+)", s)  # Branco<n>
    if m:
        return f"BRANCO{int(m.group(1))}"

    return s.replace(" ", "")


# ============================================================
# CÁLCULO DE FD1 POR MATRIZ (devolve massa_amostra, massa_solucao)
# ============================================================
def _fd1_massas_polen(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    """
    Pólen: massa_amostra (M2 − M1) e massa_solução (M4 − M3).
    Prefere as colunas explícitas de massa (podem conter ajuste manual do
    laboratório); só recalcula a partir de M1–M4 se elas não existirem.
    """
    try:
        massa_amostra = _num(df[_col(df, "massa da amostra")])
    except KeyError:
        massa_amostra = _num(df[_col(df, "(m2)")]) - _num(df[_col(df, "(m1)")])
    try:
        massa_solucao = _num(df[_col(df, "massa da solu")])
    except KeyError:
        massa_solucao = _num(df[_col(df, "(m4)")]) - _num(df[_col(df, "(m3)")])
    return massa_amostra, massa_solucao


def _fd1_massas_mpa(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    """MPA: massa_amostra pesada direto ; massa_solução = coluna explícita ou (frasco+amostra) − frasco vazio."""
    massa_amostra = _num(df[_col(df, "massa da amostra")])
    try:
        massa_solucao = _num(df[_col(df, "massa solu")])
    except KeyError:
        massa_solucao = _num(df[_col(df, "frasco + amostra")]) - _num(df[_col(df, "frasco vazio")])
    return massa_amostra, massa_solucao


def _fd1_massas_stub(df: pd.DataFrame) -> Tuple[pd.Series, pd.Series]:
    raise NotImplementedError(
        "Cálculo de FD1 desta matriz ainda não implementado. "
        "Defina massa_amostra e massa_solução conforme o protocolo de digestão."
    )


# ============================================================
# CONFIGURAÇÃO DECLARATIVA DAS MATRIZES
# ============================================================
MATRIZES: Dict[str, dict] = {
    "polen": {
        "rotulo": "Pólen",
        "disponivel": True,
        "massa_sheet": "Massa polen",
        "massa_cols": [
            "Data da pesagem", "N do frasco", "Id da amostra",
            "Massa do frasco (M1)", "Massa do frasco + Amostra (M2)",
            "Massa da amostra (M2 - M1)", "Massa do Tubo de Centrifuga (M3)",
            "Massa do Tubo de Centrifuga + solução (M4)", "Massa da Solução (M4 - M3)",
        ],
        "diluicao_cols": ["ID Amostra", "Frasco vazio (g)", "Aliquota", "H2O"],
        "id_terms": ["id da amostra", "id amostra"],
        "fd1_massas": _fd1_massas_polen,
        # Brancos de pólen não têm massa de amostra pesada → massa nominal padrão.
        "nominal_massa_branco": 0.25,
    },
    "mpa": {
        "rotulo": "Material Particulado Atmosférico (MPA)",
        "disponivel": True,
        "massa_sheet": "Massa MPA",
        "massa_cols": [
            "Data da pesagem", "N do frasco", "Id da amostra",
            "Massa da Amostra", "Massa do frasco vazio",
            "Massa frasco + amostra", "Massa solução",
        ],
        "diluicao_cols": ["ID Amostra", "frasco vazio", "Aliquota", "H2O"],
        "id_terms": ["id da amostra", "id amostra"],
        "fd1_massas": _fd1_massas_mpa,
        "nominal_massa_branco": None,
    },
    # ---- Ganchos para matrizes futuras (UI desabilita até implementar) ----
    "chamine": {
        "rotulo": "Chaminé", "disponivel": False,
        "massa_sheet": "Massa chaminé", "massa_cols": [], "diluicao_cols": [],
        "id_terms": ["id da amostra", "id amostra"],
        "fd1_massas": _fd1_massas_stub, "nominal_massa_branco": None,
    },
    "mel": {
        "rotulo": "Mel", "disponivel": False,
        "massa_sheet": "Massa mel", "massa_cols": [], "diluicao_cols": [],
        "id_terms": ["id da amostra", "id amostra"],
        "fd1_massas": _fd1_massas_stub, "nominal_massa_branco": None,
    },
}


def listar_matrizes() -> List[Tuple[str, str, bool]]:
    """Retorna [(chave, rótulo, disponível)] para montar o seletor na UI."""
    return [(k, v["rotulo"], v["disponivel"]) for k, v in MATRIZES.items()]


# ============================================================
# GERAÇÃO DO TEMPLATE DE MASSAS (download para o pesquisador)
# ============================================================
def gerar_template_massas(matriz: str) -> bytes:
    """Gera um XLSX em branco com as colunas-padrão da matriz (abas Massa + Diluição)."""
    cfg = MATRIZES[matriz]
    if not cfg["disponivel"]:
        raise NotImplementedError(f"Matriz '{matriz}' ainda não disponível.")

    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        pd.DataFrame(columns=cfg["massa_cols"]).to_excel(
            writer, sheet_name=cfg["massa_sheet"][:31], index=False
        )
        pd.DataFrame(columns=cfg["diluicao_cols"]).to_excel(
            writer, sheet_name="Diluição ICP OS", index=False
        )
    buf.seek(0)
    return buf.getvalue()


# ============================================================
# LEITURA DO ARQUIVO DE MASSAS ENVIADO
# ============================================================
def _achar_sheet(sheets: List[str], termos: List[str]) -> Optional[str]:
    for termo in termos:
        for s in sheets:
            if termo in _norm(s):
                return s
    return None


def ler_planilha_massas(arquivo, matriz: Optional[str] = None) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Lê o arquivo de massas (template preenchido) e devolve (df_massa, df_diluicao).
    Localiza as abas de forma tolerante a variações de nome.
    """
    # Streamlit reutiliza o mesmo objeto de upload entre reruns; reposiciona o
    # ponteiro para o início para permitir releitura.
    if hasattr(arquivo, "seek"):
        try:
            arquivo.seek(0)
        except Exception:
            pass
    xls = pd.ExcelFile(arquivo)
    massa_sheet = _achar_sheet(xls.sheet_names, ["massa"]) or xls.sheet_names[0]
    dil_sheet = _achar_sheet(xls.sheet_names, ["dilu", "fd2"])
    df_massa = pd.read_excel(xls, sheet_name=massa_sheet)
    if dil_sheet is None:
        raise ValueError(
            "Aba de Diluição ICP OS não encontrada no arquivo de massas. "
            f"Abas disponíveis: {xls.sheet_names}"
        )
    df_dil = pd.read_excel(xls, sheet_name=dil_sheet)
    return df_massa, df_dil


# ============================================================
# CÁLCULO DE FD1, FD2 E FDT
# ============================================================
def calcular_fd1(df_massa: pd.DataFrame, matriz: str) -> pd.DataFrame:
    """Calcula FD1 = massa_solução / massa_amostra (com massa nominal p/ brancos quando aplicável)."""
    cfg = MATRIZES[matriz]
    idc = _col(df_massa, *cfg["id_terms"])
    ids = df_massa[idc].astype(str)

    massa_amostra, massa_solucao = cfg["fd1_massas"](df_massa)
    massa_amostra = massa_amostra.reset_index(drop=True)
    massa_solucao = massa_solucao.reset_index(drop=True)
    ids = ids.reset_index(drop=True)

    nominal = cfg.get("nominal_massa_branco")
    if nominal:
        eh_branco = ids.map(lambda x: normalizar_id(x).startswith("BRANCO"))
        falta = massa_amostra.isna() | (massa_amostra <= 0)
        massa_amostra = massa_amostra.where(~(eh_branco & falta), float(nominal))

    fd1 = massa_solucao / massa_amostra
    out = pd.DataFrame(
        {"ID_FD1": ids, "Massa_amostra": massa_amostra,
         "Massa_solucao": massa_solucao, "FD1": fd1}
    )
    return out.dropna(subset=["ID_FD1"])


def calcular_fd2(df_dil: pd.DataFrame) -> pd.DataFrame:
    """Calcula FD2 = (H2O − frasco_vazio) / (alíquota − frasco_vazio). Idêntico p/ pólen e MPA."""
    idc = _col(df_dil, "id amostra", "id da amostra")
    fvazio = _num(df_dil[_col(df_dil, "frasco vazio")])
    aliquota = _num(df_dil[_col(df_dil, "aliquota", "alíquota")])
    h2o = _num(df_dil[_col(df_dil, "h2o")])

    massa_aliquota = aliquota - fvazio
    massa_solucao = h2o - fvazio
    fd2 = massa_solucao / massa_aliquota
    return pd.DataFrame({"ID_FD2": df_dil[idc].astype(str), "FD2": fd2}).dropna(subset=["ID_FD2"])


def calcular_fdt(df_fd1: pd.DataFrame, df_fd2: pd.DataFrame) -> pd.DataFrame:
    """
    Junta FD1 e FD2 por ID normalizado e calcula FDT e FDT(mg/kg).

    Returns DataFrame [chave, ID_FD1, ID_FD2, FD1, FD2, FDT, FDT_mgkg, Casado].
    Linhas não casadas (só FD1 ou só FD2) ficam com Casado=False para revisão.
    """
    a = df_fd1.copy()
    a["chave"] = a["ID_FD1"].map(normalizar_id)
    a = a[a["chave"] != ""].drop_duplicates(subset="chave", keep="first")

    b = df_fd2.copy()
    b["chave"] = b["ID_FD2"].map(normalizar_id)
    b = b[b["chave"] != ""].drop_duplicates(subset="chave", keep="first")

    m = a.merge(b, on="chave", how="outer", indicator=True)
    m["FDT"] = m["FD1"] * m["FD2"]
    m["FDT_mgkg"] = m["FDT"] / 1000.0
    m["Casado"] = m["_merge"] == "both"

    cols = ["chave", "ID_FD1", "ID_FD2", "FD1", "FD2", "FDT", "FDT_mgkg", "Casado"]
    return m[cols].sort_values("chave").reset_index(drop=True)


def calcular_fdt_completo(arquivo, matriz: str) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Pipeline completo a partir do arquivo de massas: retorna (df_fdt, df_fd1, df_fd2)."""
    df_massa, df_dil = ler_planilha_massas(arquivo, matriz)
    df_fd1 = calcular_fd1(df_massa, matriz)
    df_fd2 = calcular_fd2(df_dil)
    df_fdt = calcular_fdt(df_fd1, df_fd2)
    return df_fdt, df_fd1, df_fd2


def detectar_matriz(df_massa: pd.DataFrame) -> Optional[str]:
    """
    Identifica a matriz pelas colunas da aba de massas: 'polen', 'mpa' ou None.
    Pólen tem M1–M4 / 'Tubo de Centrifuga'; MPA tem 'Massa da Amostra' + 'frasco vazio'.
    """
    blob = " | ".join(_norm(c) for c in df_massa.columns)
    if "(m4)" in blob or "tubo de centrifuga" in blob:
        return "polen"
    if "massa da amostra" in blob and "frasco vazio" in blob:
        return "mpa"
    return None


def processar_arquivo_massas(arquivo) -> Tuple[pd.DataFrame, str]:
    """
    Lê um arquivo de massas, detecta a matriz automaticamente e calcula o FDT.

    Returns (df_fdt, matriz). Levanta ValueError se a matriz não for reconhecida.
    """
    df_massa, df_dil = ler_planilha_massas(arquivo)
    matriz = detectar_matriz(df_massa)
    if matriz is None:
        raise ValueError(
            "não reconheci a matriz pelas colunas (esperado Pólen com M1–M4, ou "
            f"MPA com 'Massa da Amostra' + 'frasco vazio'). Colunas: {list(df_massa.columns)}"
        )
    df_fd1 = calcular_fd1(df_massa, matriz)
    df_fd2 = calcular_fd2(df_dil)
    df_fdt = calcular_fdt(df_fd1, df_fd2)
    return df_fdt, matriz


# ============================================================
# MAPEAMENTO FDT → AMOSTRAS DE CONCENTRAÇÃO
# ============================================================
def construir_fdt_map(
    nomes_conc: List[str], df_fdt: pd.DataFrame
) -> Tuple[Dict[str, float], List[str]]:
    """
    Casa os nomes de amostra da tabela de concentrações com o FDT(mg/kg).

    Returns:
        (mapa {nome_conc: FDT_mgkg}, lista_de_nomes_sem_FDT)
    """
    fdt_por_chave = {
        k: v for k, v in zip(df_fdt["chave"], df_fdt["FDT_mgkg"]) if not pd.isna(v)
    }
    casado: Dict[str, float] = {}
    faltando: List[str] = []
    for nome in nomes_conc:
        val = fdt_por_chave.get(normalizar_id(nome))
        if val is not None and not pd.isna(val):
            casado[nome] = float(val)
        else:
            faltando.append(nome)
    return casado, faltando
