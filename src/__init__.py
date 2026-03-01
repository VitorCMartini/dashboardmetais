"""
Módulo de processamento de dados para análise de metais pesados em pólen.

Este pacote contém ferramentas para:
- ETL de dados ICP-MS
- Validação e normalização
- Geração de relatórios
"""

__version__ = "0.1.0"
__author__ = "Engenharia de Dados - Análise Ambiental"

from .etl import ICPMSDataProcessor

__all__ = ['ICPMSDataProcessor']
