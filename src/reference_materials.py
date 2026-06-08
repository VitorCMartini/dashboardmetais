"""
Módulo de Materiais de Referência Certificados (CRM)
====================================================
Armazena os valores certificados dos materiais de referência usados no
laboratório e calcula a Taxa de Recuperação (TR%) na etapa de quantificação
(mg/kg), comparando o valor medido com o valor de certificado.

TR% = (valor_medido_mg/kg / valor_certificado) * 100
Aprovado se 90% <= TR% <= 110% (fora disso → red flag).

A estrutura é aberta: para adicionar um novo material de referência basta
incluir uma entrada em CERTIFICADOS (e, se houver, em REFERENCIA_NAO_CERTIFICADA).

Autor: Engenharia de Dados - Setor Ambiental
Versão: 1.0.0
"""

import re
import numpy as np
import pandas as pd
from typing import Dict, Tuple, List

# ============================================================
# LIMITES DE ACEITAÇÃO DA TAXA DE RECUPERAÇÃO
# ============================================================
TR_MIN = 90.0
TR_MAX = 110.0

# ============================================================
# VALORES CERTIFICADOS (mg/kg) → (valor, incerteza_expandida_U95)
# ============================================================
# Fonte: certificados oficiais (NIST Certificate of Analysis).
CERTIFICADOS: Dict[str, Dict[str, Tuple[float, float]]] = {
    # SRM 1515 - Apple Leaves - Certificate of Analysis de 14/11/2022.
    # As e Se foram REMOVIDOS do certificado em 2017 (sem valor → sem TR%).
    "NIST 1515": {
        "Al": (284.5, 5.8),
        "Ba": (48.8, 2.3),
        "Cd": (0.0132, 0.0015),
        "Cu": (5.69, 0.13),
        "Fe": (82.7, 2.6),
        "Mn": (54.1, 1.1),
        "Mo": (0.095, 0.011),
        "Ni": (0.936, 0.094),
        "Pb": (0.470, 0.024),
        "Sr": (25.1, 1.1),
        "V": (0.254, 0.027),
        "Zn": (12.45, 0.43),
    },
    # TODO: adicionar os demais materiais usados no laboratório.
    # Ex.: "NIST 1547" (Peach Leaves), "BCR-482", etc.
    # "NIST 1547": { ... },
}

# ============================================================
# VALORES DE REFERÊNCIA NÃO-CERTIFICADOS (apenas informativos)
# ============================================================
# Não entram no critério de aprovação (90-110%); servem só de referência.
# Fonte: NIST 1515 Appendix B (Table B1) - "Values of Potential Interest".
REFERENCIA_NAO_CERTIFICADA: Dict[str, Dict[str, float]] = {
    "NIST 1515": {
        "Cr": 0.3,
        "Co": 0.09,
        "Sb": 0.013,
    },
}


def materiais_disponiveis() -> List[str]:
    """Retorna a lista de materiais de referência cadastrados."""
    return list(CERTIFICADOS.keys())


def elemento_base(nome: str) -> str:
    """
    Extrai o símbolo químico (sem isótopo, modo ou sufixo de medida).

    Ex.: 'Al_NoGas_Conc' → 'Al'; 'Cr52_He' → 'Cr'; '52  Cr  [ No Gas ]' → 'Cr'.
    """
    s = str(nome).strip()

    # Formato bruto do equipamento: '52  Cr  [ No Gas ]' → pega o símbolo entre número e colchete.
    m = re.match(r"^\s*\d+\s*([A-Za-z]{1,2})\b", s)
    if m:
        return m.group(1).capitalize()

    # Formato padronizado: 'Cr52_He_Conc'
    for suf in ("_Conc", "_RSD"):
        s = s.replace(suf, "")
    for modo in ("_NoGas", "_He"):
        if s.endswith(modo):
            s = s[: -len(modo)]
    s = re.sub(r"\d+$", "", s)  # remove número de isótopo (Cr52 → Cr)
    return s.capitalize()


def calcular_tr_certificado(
    valores_mgkg: Dict[str, float], material: str = "NIST 1515"
) -> pd.DataFrame:
    """
    Calcula a TR% de cada elemento certificado contra o valor medido.

    Args:
        valores_mgkg: dict {símbolo_elemento: concentração_medida_mg/kg}
                      (ex.: {'Al': 292.46, 'Pb': 0.47, ...})
        material: chave em CERTIFICADOS (ex.: 'NIST 1515')

    Returns:
        DataFrame com colunas:
        [Elemento, Medido_mgkg, Certificado, Incerteza_U95, TR_pct, Status, Red_Flag]
        Status ∈ {'Aprovado', 'Reprovado', 'Sem leitura'}.
    """
    cert = CERTIFICADOS.get(material, {})
    linhas = []

    for elem, (valor_cert, u95) in cert.items():
        medido = valores_mgkg.get(elem, np.nan)

        if pd.isna(medido) or not valor_cert:
            tr = np.nan
            status = "Sem leitura"
            red = False
        else:
            tr = (medido / valor_cert) * 100.0
            dentro = TR_MIN <= tr <= TR_MAX
            status = "Aprovado" if dentro else "Reprovado"
            red = not dentro

        linhas.append(
            {
                "Elemento": elem,
                "Medido_mgkg": medido,
                "Certificado": valor_cert,
                "Incerteza_U95": u95,
                "TR_pct": tr,
                "Status": status,
                "Red_Flag": red,
            }
        )

    df = pd.DataFrame(linhas)
    if len(df) > 0:
        df = df.sort_values("Elemento").reset_index(drop=True)
    return df
