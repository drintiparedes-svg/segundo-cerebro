"""Conectores V2: fuentes externas → Documents del pipeline de ingesta.

Cada conector produce objetos Document idénticos a los del vault Markdown;
la extracción, la memoria y el router no distinguen el origen. Los
conectores de Google soportan múltiples cuentas Gmail, cada una con su
propio token OAuth (alias: personal, falp, etc.).
"""
