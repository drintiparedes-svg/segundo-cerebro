# Payment Integrity — Reporte de priorización de auditoría

Períodos analizados: 2026-03 → 2026-08 | Médicos: 60 | Médico-períodos: 360

## Distribución por nivel (consolidado por médico)

| Nivel | Etiqueta | Médicos |
|---|---|---:|
| 0 | Normal | 48 |
| 1 | Anomalía operacional | 3 |
| 2 | Posible error administrativo | 1 |
| 3 | Posible pago indebido | 0 |
| 4 | Requiere auditoría | 8 |

## Top 15 médicos priorizados

### 1. MED0046 — 86/100 · Nivel 4 (Requiere auditoría)

Peer group: Medicina interna | telemedicina · Peor período: 2026-08 · Pagado total: $23,443,000 · Sin respaldo de actividad: $5,476,600 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 56/100 |
| Rendimiento anómalo | 96/100 |
| Diferencia frente a pares | 89/100 |
| Anomaly detection (IF + LOF) | 100/100 |
| **Risk Score (2026-08)** | **86/100** |

> Riesgo requiere auditoría — 86/100. Médico en percentil 99 de costo por paciente dentro de su peer group (Medicina interna | telemedicina, n=8). El 50% de las horas pagadas no presenta actividad clínica registrada (45.0 h; $1,773,000 sin respaldo). El rendimiento cayó 59% respecto de su propio histórico (2.3 → 0.9 pac/h), con señal CUSUM de cambio sostenido. Caso escalado a nivel ≥ 3 por regla crítica (R01). Reglas activadas: R01 horas pagadas sin actividad clínica, R02 rendimiento incompatible con lo esperado, R10 actividad concentrada artificialmente en el turno. Combinación atípica de variables según Isolation Forest/LOF (cost_per_patient_z (+9.5), edge_concentration (+4.3), performance_ratio (-4.2)).

### 2. MED0007 — 82/100 · Nivel 4 (Requiere auditoría)

Peer group: Medicina interna | presencial · Peor período: 2026-06 · Pagado total: $18,446,000 · Sin respaldo de actividad: $4,350,850 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 94/100 |
| Rendimiento anómalo | 3/100 |
| Diferencia frente a pares | 82/100 |
| Anomaly detection (IF + LOF) | 100/100 |
| **Risk Score (2026-06)** | **82/100** |

> Riesgo requiere auditoría — 82/100. Médico en percentil 92 de costo por paciente dentro de su peer group (Medicina interna | presencial, n=12). Caso escalado a nivel ≥ 3 por regla crítica (R03, R04, R05). Reglas activadas: R03 atenciones fuera del horario contratado, R04 consultas simultáneas (solapadas), R05 atención sin sesión activa del médico. Combinación atípica de variables según Isolation Forest/LOF (encounters_without_login (+38.0), off_schedule_encounters (+38.0), overlapping_encounters (+20.0)).

### 3. MED0030 — 82/100 · Nivel 4 (Requiere auditoría)

Peer group: Medicina interna | presencial · Peor período: 2026-05 · Pagado total: $18,472,800 · Sin respaldo de actividad: $6,415,600 · Sobre contrato/duplicado: $6,503,177

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 100/100 |
| Horas sin actividad / integridad del registro | 31/100 |
| Rendimiento anómalo | 13/100 |
| Diferencia frente a pares | 89/100 |
| Anomaly detection (IF + LOF) | 61/100 |
| **Risk Score (2026-05)** | **83/100** |

> Riesgo requiere auditoría — 83/100. Médico en percentil 99 de costo por paciente dentro de su peer group (Medicina interna | presencial, n=12). El 43% de las horas pagadas no presenta actividad clínica registrada (38.0 h; $1,307,200 sin respaldo). Pagos sobre contrato o duplicados por $1,814,027. Caso escalado a nivel ≥ 3 por regla crítica (R07, R08). Reglas activadas: R01 horas pagadas sin actividad clínica, R02 rendimiento incompatible con lo esperado, R07 horas pagadas superiores a contratadas, R08 pagos duplicados. Combinación atípica de variables según Isolation Forest/LOF (utilization_z (-4.9), idle_hours_ratio_z (+4.9), duplicate_payments (+4.0)).

### 4. MED0042 — 82/100 · Nivel 4 (Requiere auditoría)

Peer group: Medicina interna | telemedicina · Peor período: 2026-08 · Pagado total: $23,147,800 · Sin respaldo de actividad: $6,126,250 · Sobre contrato/duplicado: $8,497,580

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 100/100 |
| Horas sin actividad / integridad del registro | 0/100 |
| Rendimiento anómalo | 20/100 |
| Diferencia frente a pares | 84/100 |
| Anomaly detection (IF + LOF) | 92/100 |
| **Risk Score (2026-08)** | **82/100** |

> Riesgo requiere auditoría — 82/100. El 35% de las horas pagadas no presenta actividad clínica registrada (36.5 h; $1,376,050 sin respaldo). Pagos sobre contrato o duplicados por $2,458,040. Caso escalado a nivel ≥ 3 por regla crítica (R07, R08). Reglas activadas: R01 horas pagadas sin actividad clínica, R07 horas pagadas superiores a contratadas, R08 pagos duplicados. Combinación atípica de variables según Isolation Forest/LOF (duplicate_payments (+3.0), idle_hours_ratio_z (+2.7), utilization_z (-2.7)).

### 5. MED0045 — 80/100 · Nivel 4 (Requiere auditoría)

Peer group: Medicina interna | telemedicina · Peor período: 2026-08 · Pagado total: $31,339,000 · Sin respaldo de actividad: $17,926,500 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 90/100 |
| Rendimiento anómalo | 0/100 |
| Diferencia frente a pares | 83/100 |
| Anomaly detection (IF + LOF) | 74/100 |
| **Risk Score (2026-08)** | **80/100** |

> Riesgo requiere auditoría — 80/100. El 57% de las horas pagadas no presenta actividad clínica registrada (72.0 h; $2,664,000 sin respaldo). Caso escalado a nivel ≥ 3 por regla crítica (R01). Reglas activadas: R01 horas pagadas sin actividad clínica, R10 actividad concentrada artificialmente en el turno. Combinación atípica de variables según Isolation Forest/LOF (edge_concentration (+10.9), mean_duration_min_z (-5.2), idle_hours_ratio_z (+4.9)).

### 6. MED0006 — 79/100 · Nivel 4 (Requiere auditoría)

Peer group: Oncología médica | presencial · Peor período: 2026-04 · Pagado total: $24,442,000 · Sin respaldo de actividad: $14,665,200 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 100/100 |
| Rendimiento anómalo | 0/100 |
| Diferencia frente a pares | 42/100 |
| Anomaly detection (IF + LOF) | 100/100 |
| **Risk Score (2026-04)** | **79/100** |

> Riesgo requiere auditoría — 79/100. El 60% de las horas pagadas no presenta actividad clínica registrada (54.0 h; $2,613,600 sin respaldo). Caso escalado a nivel ≥ 3 por regla crítica (R01). Reglas activadas: R01 horas pagadas sin actividad clínica, R10 actividad concentrada artificialmente en el turno. Combinación atípica de variables según Isolation Forest/LOF (edge_concentration (+10.9), idle_hours_ratio_z (+3.1), utilization_z (-3.1)).

### 7. MED0008 — 78/100 · Nivel 4 (Requiere auditoría)

Peer group: Medicina interna | presencial · Peor período: 2026-03 · Pagado total: $30,146,200 · Sin respaldo de actividad: $2,188,600 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 75/100 |
| Rendimiento anómalo | 0/100 |
| Diferencia frente a pares | 57/100 |
| Anomaly detection (IF + LOF) | 100/100 |
| **Risk Score (2026-03)** | **78/100** |

> Riesgo requiere auditoría — 78/100. Caso escalado a nivel ≥ 3 por regla crítica (R12). Reglas activadas: R06 mismo paciente contabilizado múltiples veces, R11 consultas con duración físicamente improbable, R12 atenciones sin registro clínico, R13 registro clínico creado retrospectivamente. Combinación atípica de variables según Isolation Forest/LOF (duplicate_patient_days (+19.0), mean_duration_min_z (-2.2), cost_per_patient_z (-1.8)).

### 8. MED0057 — 77/100 · Nivel 4 (Requiere auditoría)

Peer group: Pediatría | telemedicina · Peor período: 2026-03 · Pagado total: $16,709,700 · Sin respaldo de actividad: $1,814,850 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 96/100 |
| Rendimiento anómalo | 0/100 |
| Diferencia frente a pares | 23/100 |
| Anomaly detection (IF + LOF) | 100/100 |
| **Risk Score (2026-03)** | **77/100** |

> Riesgo requiere auditoría — 77/100. Caso escalado a nivel ≥ 3 por regla crítica (R12). Reglas activadas: R06 mismo paciente contabilizado múltiples veces, R11 consultas con duración físicamente improbable, R12 atenciones sin registro clínico. Combinación atípica de variables según Isolation Forest/LOF (duplicate_patient_days (+13.0), patients_per_hour_z (+5.7), mean_duration_min_z (-0.7)).

### 9. MED0050 — 49/100 · Nivel 2 (Posible error administrativo)

Peer group: Medicina general | telemedicina · Peor período: 2026-08 · Pagado total: $17,047,800 · Sin respaldo de actividad: $2,855,650 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 32/100 |
| Rendimiento anómalo | 94/100 |
| Diferencia frente a pares | 44/100 |
| Anomaly detection (IF + LOF) | 89/100 |
| **Risk Score (2026-08)** | **49/100** |

> Riesgo posible error administrativo — 49/100. El 43% de las horas pagadas no presenta actividad clínica registrada (41.5 h; $1,191,050 sin respaldo). El rendimiento cayó 58% respecto de su propio histórico (3.2 → 1.2 pac/h), con señal CUSUM de cambio sostenido. Reglas activadas: R01 horas pagadas sin actividad clínica, R02 rendimiento incompatible con lo esperado, R10 actividad concentrada artificialmente en el turno. Combinación atípica de variables según Isolation Forest/LOF (cost_per_patient_z (+8.4), utilization_z (-5.1), idle_hours_ratio_z (+5.1)).

### 10. MED0048 — 32/100 · Nivel 1 (Anomalía operacional)

Peer group: Medicina general | presencial · Peor período: 2026-08 · Pagado total: $11,717,600 · Sin respaldo de actividad: $951,300 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 0/100 |
| Rendimiento anómalo | 2/100 |
| Diferencia frente a pares | 83/100 |
| Anomaly detection (IF + LOF) | 100/100 |
| **Risk Score (2026-08)** | **32/100** |

> Riesgo anomalía operacional — 32/100. Médico en percentil 90 de costo por paciente dentro de su peer group (Medicina general | presencial, n=21). Combinación atípica de variables según Isolation Forest/LOF (no_show_ratio_z (+6.4), utilization_z (-2.2), idle_hours_ratio_z (+2.2)).

### 11. MED0047 — 29/100 · Nivel 1 (Anomalía operacional)

Peer group: Medicina general | presencial · Peor período: 2026-08 · Pagado total: $30,940,000 · Sin respaldo de actividad: $1,738,750 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 0/100 |
| Rendimiento anómalo | 1/100 |
| Diferencia frente a pares | 72/100 |
| Anomaly detection (IF + LOF) | 94/100 |
| **Risk Score (2026-08)** | **29/100** |

> Riesgo anomalía operacional — 29/100. Médico en percentil 99 de costo por paciente dentro de su peer group (Medicina general | presencial, n=21). Combinación atípica de variables según Isolation Forest/LOF (no_show_ratio_z (+4.9), cost_per_patient_z (+1.3), edge_concentration (-1.3)).

### 12. MED0009 — 20/100 · Nivel 1 (Anomalía operacional)

Peer group: Medicina general | presencial · Peor período: 2026-04 · Pagado total: $12,009,600 · Sin respaldo de actividad: $1,070,300 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 0/100 |
| Rendimiento anómalo | 1/100 |
| Diferencia frente a pares | 84/100 |
| Anomaly detection (IF + LOF) | 40/100 |
| **Risk Score (2026-04)** | **23/100** |

> Riesgo anomalía operacional — 23/100. Médico en percentil 95 de costo por paciente dentro de su peer group (Medicina general | presencial, n=21).

### 13. MED0044 — 20/100 · Nivel 0 (Normal)

Peer group: Medicina general | telemedicina · Peor período: 2026-06 · Pagado total: $17,523,000 · Sin respaldo de actividad: $1,681,500 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 0/100 |
| Rendimiento anómalo | 10/100 |
| Diferencia frente a pares | 41/100 |
| Anomaly detection (IF + LOF) | 86/100 |
| **Risk Score (2026-06)** | **23/100** |

> Riesgo anomalía operacional — 23/100. Combinación atípica de variables según Isolation Forest/LOF (utilization_z (-15.2), idle_hours_ratio_z (+15.2), cost_per_patient_z (+1.1)).

### 14. MED0020 — 18/100 · Nivel 0 (Normal)

Peer group: Pediatría | telemedicina · Peor período: 2026-03 · Pagado total: $20,650,000 · Sin respaldo de actividad: $1,460,250 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 0/100 |
| Rendimiento anómalo | 0/100 |
| Diferencia frente a pares | 40/100 |
| Anomaly detection (IF + LOF) | 89/100 |
| **Risk Score (2026-03)** | **21/100** |

> Riesgo anomalía operacional — 21/100. Combinación atípica de variables según Isolation Forest/LOF (patients_per_hour_z (+7.9), no_show_ratio_z (+1.5), cost_per_patient_z (-0.8)).

### 15. MED0031 — 17/100 · Nivel 0 (Normal)

Peer group: Medicina interna | presencial · Peor período: 2026-04 · Pagado total: $26,849,600 · Sin respaldo de actividad: $4,013,600 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 0/100 |
| Rendimiento anómalo | 2/100 |
| Diferencia frente a pares | 85/100 |
| Anomaly detection (IF + LOF) | 17/100 |
| **Risk Score (2026-04)** | **20/100** |

> Riesgo anomalía operacional — 20/100. Médico en percentil 92 de costo por paciente dentro de su peer group (Medicina interna | presencial, n=12).

## Validación contra escenarios inyectados (solo data sintética)

- Precision@k (k=9): 1.00
- Médicos inyectados en nivel ≥ 3: 89%
- Médicos normales en nivel ≥ 3 (falsos positivos): 0.0%
- Médicos normales en nivel ≥ 2 / ≥ 1: 0.0% / 5.9%
- Score medio inyectados vs normales: 77.3 vs 9.2
- Ranking por escenario: ghost_records → [7, 8]; hours_overbilling → [3, 4]; off_schedule → [2]; phantom_hours → [5, 6]; productivity_collapse → [1, 9]
