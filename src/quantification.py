"""
Módulo de Quantificação (µg/L → mg/kg)
======================================
Implementa os passos finais do tratamento de dados ICP-MS, a partir do
DataFrame já validado pelo QC:

  1. Seleção de espécies (elemento+isótopo) e modo de análise (No Gas / He),
     com sugestão pela TR% do QC. Padrão = No Gas; He por exceção.
  3. Avaliação de RSD com dois limites (≤15% e ≤25%) — detecção + filtragem.
  4. Tabela reduzida [Nome_Amostra, concentração por espécie], só das classes
     de interesse (Amostra de Interesse + NIST + Branco).
  7. Conversão para mg/kg usando o FDT (conc_µg/L × FDT_mgkg), preservando <LOD.
  8. Agregação por amostra: saída em triplicata e em média.

Reaproveita regras de classificação de amostra e normalização do projeto.

Autor: Engenharia de Dados - Setor Ambiental
Versão: 1.0.0
"""

import numpy as np
import pandas as pd
from typing import Dict, List, Tuple, Optional

try:  # import robusto (rodando como pacote src.* ou de dentro de src/)
    from src.reference_materials import elemento_base
except ImportError:  # pragma: no cover
    from reference_materials import elemento_base

MODOS = ("NoGas", "He")
CLASSES_PADRAO = ("Interesse", "NIST", "Branco")


# ============================================================
# CLASSIFICAÇÃO POR LINHA (1 amostra → 1 classe)
# ============================================================
def classificar_amostra(nome) -> str:
    """Classe laboratorial de uma amostra pelo nome (mesmas regras do dashboard)."""
    s = str(nome).strip().upper()
    if s.startswith("P"):
        return "Calibração"
    if "HNO3" in s:
        return "HNO3"
    if "NIST" in s:
        return "NIST"
    if s.startswith("MERCK"):
        return "Merck"
    if s.startswith("B"):
        return "Branco"
    if s[:1].isdigit():
        return "Interesse"
    return "Outras"


# ============================================================
# PASSO 1 — SELEÇÃO DE ESPÉCIES E MODO
# ============================================================
def _especie_e_modo(base: str) -> Tuple[str, Optional[str]]:
    """'Al_NoGas' → ('Al','NoGas'); 'Cr52_He' → ('Cr52','He')."""
    for modo in MODOS:
        if base.endswith("_" + modo):
            return base[: -(len(modo) + 1)], modo
    return base, None


def listar_especies(df: pd.DataFrame, resultados_qc: Optional[Dict] = None) -> pd.DataFrame:
    """
    Monta a tabela de seleção de espécies para o usuário ajustar.

    Returns DataFrame [Incluir, Espécie, Elemento, Modo, Modos_disp, TR%_NoGas, TR%_He].
    'Modo' default = No Gas (mais estável); He só onde No Gas não existe.
    """
    tr = (resultados_qc or {}).get("tr", {})

    def tr_medio(base: str) -> float:
        d = tr.get(base, {})
        vals = [v for v in (d.get("tr_50"), d.get("tr_200"))
                if v is not None and not pd.isna(v)]
        return float(np.mean(vals)) if vals else np.nan

    especies: Dict[str, set] = {}
    for col in df.columns:
        if col.endswith("_Conc") and "_Flag" not in col:
            esp, modo = _especie_e_modo(col[: -len("_Conc")])
            if modo:
                especies.setdefault(esp, set()).add(modo)

    linhas = []
    for esp, modos in especies.items():
        linhas.append(
            {
                "Incluir": True,
                "Espécie": esp,
                "Elemento": elemento_base(esp),
                "Modo": "NoGas" if "NoGas" in modos else "He",
                "Modos_disp": "/".join(sorted(modos)),
                "TR%_NoGas": tr_medio(f"{esp}_NoGas"),
                "TR%_He": tr_medio(f"{esp}_He"),
            }
        )
    out = pd.DataFrame(linhas)
    if len(out):
        out = out.sort_values("Espécie").reset_index(drop=True)
    return out


def colunas_conc_escolhidas(selecao: pd.DataFrame) -> List[str]:
    """Converte a seleção do usuário em nomes de coluna de concentração ('Esp_Modo_Conc')."""
    cols = []
    for _, r in selecao.iterrows():
        if bool(r.get("Incluir", False)):
            cols.append(f"{r['Espécie']}_{r['Modo']}_Conc")
    return cols


# ============================================================
# PASSO 2 — OVERRIDE MANUAL ICP-OES (acima da curva)
# ============================================================
def aplicar_override_icpoes(df: pd.DataFrame, overrides: Dict[Tuple[str, str], float]) -> pd.DataFrame:
    """
    Substitui manualmente valores acima da curva pelo resultado do ICP-OES.

    Args:
        overrides: {(Nome_Amostra, coluna_conc): valor_icpoes_µg/L}
    """
    if not overrides:
        return df
    d = df.copy()
    for (nome, col), valor in overrides.items():
        if col in d.columns:
            d.loc[d["Nome_Amostra"] == nome, col] = valor
    return d


# ============================================================
# PASSOS 3 e 4 — RSD + TABELA REDUZIDA
# ============================================================
def reduzir_tabela(
    df: pd.DataFrame,
    cols_conc: List[str],
    limite_rsd: float = 15.0,
    classes: Tuple[str, ...] = CLASSES_PADRAO,
) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Gera a tabela reduzida (só concentrações das classes de interesse), a máscara
    de RSD acima do limite e o sub-DataFrame completo (com flags) para uso interno.

    Returns:
        (conc_view, mask_rsd, d_full)
        - conc_view : [Nome_Amostra, Classe, <Esp_Modo_Conc>...]  (sem colunas RSD)
        - mask_rsd  : booleana, True onde RSD > limite (para destacar/“cor”)
        - d_full    : linhas filtradas com todas as colunas (conc, RSD, flags)
    """
    d = df[df["Tipo_Amostra"] == "Sample"].copy()
    d["Classe"] = d["Nome_Amostra"].map(classificar_amostra)
    d = d[d["Classe"].isin(classes)].copy().reset_index(drop=True)

    cols_presentes = [c for c in cols_conc if c in d.columns]
    conc_view = d[["Nome_Amostra", "Classe"] + cols_presentes].copy()

    mask = pd.DataFrame(False, index=conc_view.index, columns=cols_presentes)
    for c in cols_presentes:
        rsd_col = c.replace("_Conc", "_RSD")
        if rsd_col in d.columns:
            mask[c] = pd.to_numeric(d[rsd_col], errors="coerce") > limite_rsd

    return conc_view, mask, d


def aplicar_filtro_rsd(conc_view: pd.DataFrame, mask_rsd: pd.DataFrame) -> pd.DataFrame:
    """Versão filtrada: zera (NaN) as concentrações com RSD acima do limite."""
    out = conc_view.copy()
    for c in mask_rsd.columns:
        out.loc[mask_rsd[c], c] = np.nan
    return out


# ============================================================
# PASSO 7 — CONVERSÃO PARA mg/kg
# ============================================================
def _fmt_lod(valor: float) -> str:
    """Formata valor < LOD no padrão do laboratório ('<1,433') com vírgula decimal."""
    return "<" + f"{valor:.4g}".replace(".", ",")


def converter_mgkg(
    d_full: pd.DataFrame, cols_conc: List[str], fdt_map: Dict[str, float]
) -> pd.DataFrame:
    """
    Converte concentração (µg/L) para mg/kg usando o FDT(mg/kg) de cada amostra.

    resultado_mg/kg = conc_µg/L × FDT_mgkg
    Mantém leituras < LOD como texto '<x,xxx'. Amostras sem FDT viram NaN.
    """
    cols_presentes = [c for c in cols_conc if c in d_full.columns]
    rows = []
    for _, r in d_full.iterrows():
        nome = r["Nome_Amostra"]
        fdt = fdt_map.get(nome)
        linha = {"Nome_Amostra": nome, "Classe": r.get("Classe")}
        for c in cols_presentes:
            elem_col = c.replace("_Conc", "")  # 'Al_NoGas'
            val = r[c]
            flag_lod = bool(r.get(f"{c}_Flag_LOD", False))
            if fdt is None or pd.isna(val):
                linha[elem_col] = np.nan
            else:
                mgkg = float(val) * float(fdt)
                linha[elem_col] = _fmt_lod(mgkg) if flag_lod else mgkg
        rows.append(linha)
    return pd.DataFrame(rows)


# ============================================================
# PASSO 8 — AGREGAÇÃO POR AMOSTRA (triplicata → média)
# ============================================================
def _base_id(nome) -> str:
    """Remove a letra de réplica final: '1009A'→'1009'; 'Nist2A'→'Nist2'; 'B4'→'B4'."""
    s = str(nome).strip()
    if s and s[-1].isalpha():
        return s[:-1]
    return s


def agregar_media(df_mgkg: pd.DataFrame) -> pd.DataFrame:
    """
    Agrega réplicas por amostra-base calculando a média dos elementos.

    - Média apenas dos valores numéricos da réplica (ignora < LOD).
    - Se todas as réplicas forem < LOD, propaga o '<LOD' (conservador).
    """
    d = df_mgkg.copy()
    d["_base"] = d["Nome_Amostra"].map(_base_id)
    elem_cols = [c for c in d.columns if c not in ("Nome_Amostra", "Classe", "_base")]

    rows = []
    for base, g in d.groupby("_base", sort=False):
        linha = {"Amostra": base, "Classe": g["Classe"].iloc[0], "N_replicas": len(g)}
        for c in elem_cols:
            vals = list(g[c])
            numeric = [v for v in vals if isinstance(v, (int, float)) and not pd.isna(v)]
            if numeric:
                linha[c] = float(np.mean(numeric))
            else:
                lods = [v for v in vals if isinstance(v, str) and v.startswith("<")]
                linha[c] = lods[0] if lods else np.nan
        rows.append(linha)
    return pd.DataFrame(rows)
