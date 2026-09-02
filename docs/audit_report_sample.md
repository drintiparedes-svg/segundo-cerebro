# Payment Integrity — Reporte de priorización de auditoría

Períodos analizados: 2026-03 → 2026-08 | Médicos: 60 | Médico-períodos: 360

## Distribución por nivel (consolidado por médico)

| Nivel | Etiqueta | Médicos |
|---|---|---:|
| 0 | Normal | 50 |
| 1 | Anomalía operacional | 1 |
| 2 | Posible error administrativo | 1 |
| 3 | Posible pago indebido | 0 |
| 4 | Requiere auditoría | 8 |

## Top 15 médicos priorizados

### 1. MED0046 — 87/100 · Nivel 4 (Requiere auditoría)

Peer group: Medicina interna | telemedicina · Peor período: 2026-08 · Pagado total: $15,917,600 · Sin respaldo de actividad: $4,058,200 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 84/100 |
| Rendimiento anómalo | 100/100 |
| Diferencia frente a pares | 91/100 |
| Anomaly detection (IF + LOF) | 100/100 |
| Relaciones médico–paciente (grafo) | 0/100 |
| **Risk Score (2026-08)** | **87/100** |

> Riesgo requiere auditoría — 87/100. Médico en percentil 99 de costo por paciente dentro de su peer group (Medicina interna | telemedicina, n=8). El 58% de las horas pagadas no presenta actividad clínica registrada (37.0 h; $1,457,800 sin respaldo). El rendimiento cayó 60% respecto de su propio histórico (2.2 → 0.8 pac/h), con señal CUSUM de cambio sostenido. Caso escalado a nivel ≥ 3 por regla crítica (R01). Reglas activadas: R01 horas pagadas sin actividad clínica, R02 rendimiento incompatible con lo esperado, R10 actividad concentrada artificialmente en el turno. Combinación atípica de variables según Isolation Forest/LOF (utilization_z (-14.0), idle_hours_ratio_z (+14.0), cost_per_patient_z (+12.7)).

### 2. MED0057 — 82/100 · Nivel 4 (Requiere auditoría)

Peer group: Medicina interna | presencial · Peor período: 2026-07 · Pagado total: $18,835,200 · Sin respaldo de actividad: $1,455,150 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 94/100 |
| Rendimiento anómalo | 1/100 |
| Diferencia frente a pares | 64/100 |
| Anomaly detection (IF + LOF) | 100/100 |
| Relaciones médico–paciente (grafo) | 100/100 |
| **Risk Score (2026-07)** | **82/100** |

> Riesgo requiere auditoría — 82/100. Caso escalado a nivel ≥ 3 por regla crítica (R04, G01). Reglas activadas: R04 consultas simultáneas (solapadas), R06 mismo paciente contabilizado múltiples veces. 52 atenciones a 32 pacientes coinciden en el tiempo con atenciones de otro médico al mismo paciente (físicamente incompatible). Comparte 100% de sus pacientes con otros médicos (mediana del grupo 12%); vínculo más fuerte con MED0030 (40 pacientes en común, Jaccard 1.00). Actividad concentrada: 5 pacientes reúnen 18% de las atenciones (7.9 atenciones por paciente vs 1.4 del grupo). 40 pacientes (100% de su cartera) con frecuencia de visitas implausible en el mes. Pertenece a una comunidad de 2 médicos que comparten un pool de pacientes. Combinación atípica de variables según Isolation Forest/LOF (overlapping_encounters (+13.0), duplicate_patient_days (+6.0), mean_duration_min_z (-2.5)).

### 3. MED0007 — 80/100 · Nivel 4 (Requiere auditoría)

Peer group: Medicina interna | presencial · Peor período: 2026-08 · Pagado total: $24,461,000 · Sin respaldo de actividad: $5,834,550 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 94/100 |
| Rendimiento anómalo | 0/100 |
| Diferencia frente a pares | 86/100 |
| Anomaly detection (IF + LOF) | 100/100 |
| Relaciones médico–paciente (grafo) | 2/100 |
| **Risk Score (2026-08)** | **80/100** |

> Riesgo requiere auditoría — 80/100. Médico en percentil 99 de costo por paciente dentro de su peer group (Medicina interna | presencial, n=13). El 28% de las horas pagadas no presenta actividad clínica registrada (26.5 h; $1,062,650 sin respaldo). Caso escalado a nivel ≥ 3 por regla crítica (R03, R04, R05). Reglas activadas: R03 atenciones fuera del horario contratado, R04 consultas simultáneas (solapadas), R05 atención sin sesión activa del médico. 1 pacientes (1% de su cartera) con frecuencia de visitas implausible en el mes. Combinación atípica de variables según Isolation Forest/LOF (encounters_without_login (+53.0), off_schedule_encounters (+53.0), overlapping_encounters (+25.0)).

### 4. MED0030 — 80/100 · Nivel 4 (Requiere auditoría)

Peer group: Medicina interna | presencial · Peor período: 2026-05 · Pagado total: $20,640,000 · Sin respaldo de actividad: $2,304,800 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 90/100 |
| Rendimiento anómalo | 0/100 |
| Diferencia frente a pares | 32/100 |
| Anomaly detection (IF + LOF) | 100/100 |
| Relaciones médico–paciente (grafo) | 100/100 |
| **Risk Score (2026-05)** | **80/100** |

> Riesgo requiere auditoría — 80/100. Caso escalado a nivel ≥ 3 por regla crítica (R04, G01). Reglas activadas: R04 consultas simultáneas (solapadas), R06 mismo paciente contabilizado múltiples veces. 33 atenciones a 22 pacientes coinciden en el tiempo con atenciones de otro médico al mismo paciente (físicamente incompatible). Comparte 100% de sus pacientes con otros médicos (mediana del grupo 13%); vínculo más fuerte con MED0057 (40 pacientes en común, Jaccard 1.00). Actividad concentrada: 5 pacientes reúnen 21% de las atenciones (6.1 atenciones por paciente vs 1.4 del grupo). 37 pacientes (92% de su cartera) con frecuencia de visitas implausible en el mes. Pertenece a una comunidad de 2 médicos que comparten un pool de pacientes. Combinación atípica de variables según Isolation Forest/LOF (overlapping_encounters (+15.0), duplicate_patient_days (+5.0), mean_duration_min_z (-1.1)).

### 5. MED0042 — 79/100 · Nivel 4 (Requiere auditoría)

Peer group: Medicina interna | telemedicina · Peor período: 2026-04 · Pagado total: $46,521,800 · Sin respaldo de actividad: $11,441,950 · Sobre contrato/duplicado: $14,891,719

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 100/100 |
| Horas sin actividad / integridad del registro | 0/100 |
| Rendimiento anómalo | 2/100 |
| Diferencia frente a pares | 83/100 |
| Anomaly detection (IF + LOF) | 100/100 |
| Relaciones médico–paciente (grafo) | 4/100 |
| **Risk Score (2026-04)** | **79/100** |

> Riesgo requiere auditoría — 79/100. Médico en percentil 99 de costo por paciente dentro de su peer group (Medicina interna | telemedicina, n=8). Pagos sobre contrato o duplicados por $2,353,274. Caso escalado a nivel ≥ 3 por regla crítica (R07, R08). Reglas activadas: R07 horas pagadas superiores a contratadas, R08 pagos duplicados. 4 pacientes (2% de su cartera) con frecuencia de visitas implausible en el mes. Combinación atípica de variables según Isolation Forest/LOF (utilization_z (-6.3), idle_hours_ratio_z (+6.3), duplicate_payments (+2.0)).

### 6. MED0006 — 78/100 · Nivel 4 (Requiere auditoría)

Peer group: Oncología médica | presencial · Peor período: 2026-07 · Pagado total: $24,200,000 · Sin respaldo de actividad: $14,520,000 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 100/100 |
| Rendimiento anómalo | 0/100 |
| Diferencia frente a pares | 42/100 |
| Anomaly detection (IF + LOF) | 96/100 |
| Relaciones médico–paciente (grafo) | 12/100 |
| **Risk Score (2026-07)** | **78/100** |

> Riesgo requiere auditoría — 78/100. El 60% de las horas pagadas no presenta actividad clínica registrada (51.0 h; $2,468,400 sin respaldo). Caso escalado a nivel ≥ 3 por regla crítica (R01). Reglas activadas: R01 horas pagadas sin actividad clínica, R10 actividad concentrada artificialmente en el turno. 1 atenciones a 1 pacientes coinciden en el tiempo con atenciones de otro médico al mismo paciente (físicamente incompatible). 1 pacientes (1% de su cartera) con frecuencia de visitas implausible en el mes. Combinación atípica de variables según Isolation Forest/LOF (edge_concentration (+9.3), utilization_z (-6.4), idle_hours_ratio_z (+6.4)).

### 7. MED0045 — 77/100 · Nivel 4 (Requiere auditoría)

Peer group: Medicina interna | telemedicina · Peor período: 2026-07 · Pagado total: $14,800,000 · Sin respaldo de actividad: $7,400,000 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 66/100 |
| Rendimiento anómalo | 4/100 |
| Diferencia frente a pares | 82/100 |
| Anomaly detection (IF + LOF) | 100/100 |
| Relaciones médico–paciente (grafo) | 0/100 |
| **Risk Score (2026-07)** | **78/100** |

> Riesgo requiere auditoría — 78/100. El 50% de las horas pagadas no presenta actividad clínica registrada (32.0 h; $1,184,000 sin respaldo). Caso escalado a nivel ≥ 3 por regla crítica (R01). Reglas activadas: R01 horas pagadas sin actividad clínica, R10 actividad concentrada artificialmente en el turno. Combinación atípica de variables según Isolation Forest/LOF (mean_duration_min_z (-12.0), edge_concentration (+9.3), idle_hours_ratio_z (+5.0)).

### 8. MED0008 — 77/100 · Nivel 4 (Requiere auditoría)

Peer group: Medicina interna | presencial · Peor período: 2026-04 · Pagado total: $17,120,500 · Sin respaldo de actividad: $1,394,350 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 90/100 |
| Rendimiento anómalo | 0/100 |
| Diferencia frente a pares | 48/100 |
| Anomaly detection (IF + LOF) | 100/100 |
| Relaciones médico–paciente (grafo) | 8/100 |
| **Risk Score (2026-04)** | **77/100** |

> Riesgo requiere auditoría — 77/100. Caso escalado a nivel ≥ 3 por regla crítica (R12). Reglas activadas: R06 mismo paciente contabilizado múltiples veces, R11 consultas con duración físicamente improbable, R12 atenciones sin registro clínico, R13 registro clínico creado retrospectivamente. 4 pacientes (3% de su cartera) con frecuencia de visitas implausible en el mes. Combinación atípica de variables según Isolation Forest/LOF (duplicate_patient_days (+15.0), cost_per_patient_z (-2.9), mean_duration_min_z (-1.9)).

### 9. MED0050 — 44/100 · Nivel 2 (Posible error administrativo)

Peer group: Medicina general | telemedicina · Peor período: 2026-08 · Pagado total: $16,186,800 · Sin respaldo de actividad: $2,597,350 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 21/100 |
| Rendimiento anómalo | 95/100 |
| Diferencia frente a pares | 43/100 |
| Anomaly detection (IF + LOF) | 100/100 |
| Relaciones médico–paciente (grafo) | 0/100 |
| **Risk Score (2026-08)** | **44/100** |

> Riesgo posible error administrativo — 44/100. El 41% de las horas pagadas no presenta actividad clínica registrada (32.0 h; $918,400 sin respaldo). El rendimiento cayó 60% respecto de su propio histórico (3.3 → 1.3 pac/h), con señal CUSUM de cambio sostenido. Reglas activadas: R01 horas pagadas sin actividad clínica, R02 rendimiento incompatible con lo esperado, R10 actividad concentrada artificialmente en el turno. Combinación atípica de variables según Isolation Forest/LOF (cost_per_patient_z (+9.0), idle_hours_ratio_z (+6.5), utilization_z (-6.5)).

### 10. MED0053 — 20/100 · Nivel 1 (Anomalía operacional)

Peer group: Medicina interna | presencial · Peor período: 2026-04 · Pagado total: $14,824,800 · Sin respaldo de actividad: $1,409,400 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 0/100 |
| Rendimiento anómalo | 0/100 |
| Diferencia frente a pares | 72/100 |
| Anomaly detection (IF + LOF) | 73/100 |
| Relaciones médico–paciente (grafo) | 12/100 |
| **Risk Score (2026-04)** | **24/100** |

> Riesgo anomalía operacional — 24/100. Médico en percentil 92 de costo por paciente dentro de su peer group (Medicina interna | presencial, n=13). 1 atenciones a 1 pacientes coinciden en el tiempo con atenciones de otro médico al mismo paciente (físicamente incompatible). 1 pacientes (1% de su cartera) con frecuencia de visitas implausible en el mes. Combinación atípica de variables según Isolation Forest/LOF (cost_per_patient_z (+3.3), mean_duration_min_z (+1.4), performance_ratio (-1.2)).

### 11. MED0044 — 18/100 · Nivel 0 (Normal)

Peer group: Medicina general | telemedicina · Peor período: 2026-03 · Pagado total: $23,954,000 · Sin respaldo de actividad: $1,947,000 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 0/100 |
| Rendimiento anómalo | 0/100 |
| Diferencia frente a pares | 42/100 |
| Anomaly detection (IF + LOF) | 100/100 |
| Relaciones médico–paciente (grafo) | 3/100 |
| **Risk Score (2026-03)** | **22/100** |

> Riesgo anomalía operacional — 22/100. 3 pacientes (1% de su cartera) con frecuencia de visitas implausible en el mes. Combinación atípica de variables según Isolation Forest/LOF (no_show_ratio_z (+37.8), utilization_z (-2.0), idle_hours_ratio_z (+2.0)).

### 12. MED0009 — 17/100 · Nivel 0 (Normal)

Peer group: Medicina general | presencial · Peor período: 2026-08 · Pagado total: $11,231,200 · Sin respaldo de actividad: $1,334,400 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 0/100 |
| Rendimiento anómalo | 0/100 |
| Diferencia frente a pares | 82/100 |
| Anomaly detection (IF + LOF) | 18/100 |
| Relaciones médico–paciente (grafo) | 0/100 |
| **Risk Score (2026-08)** | **17/100** |

> Riesgo normal — 17/100. Médico en percentil 90 de costo por paciente dentro de su peer group (Medicina general | presencial, n=21).

### 13. MED0038 — 17/100 · Nivel 0 (Normal)

Peer group: Pediatría | presencial · Peor período: 2026-07 · Pagado total: $14,406,000 · Sin respaldo de actividad: $1,308,300 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 0/100 |
| Rendimiento anómalo | 1/100 |
| Diferencia frente a pares | 27/100 |
| Anomaly detection (IF + LOF) | 100/100 |
| Relaciones médico–paciente (grafo) | 0/100 |
| **Risk Score (2026-07)** | **19/100** |

> Riesgo normal — 19/100. Combinación atípica de variables según Isolation Forest/LOF (mean_duration_min_z (+4.2), no_show_ratio_z (-3.3), utilization_z (-1.8)).

### 14. MED0020 — 17/100 · Nivel 0 (Normal)

Peer group: Pediatría | telemedicina · Peor período: 2026-05 · Pagado total: $18,585,000 · Sin respaldo de actividad: $1,312,750 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 0/100 |
| Rendimiento anómalo | 1/100 |
| Diferencia frente a pares | 20/100 |
| Anomaly detection (IF + LOF) | 100/100 |
| Relaciones médico–paciente (grafo) | 3/100 |
| **Risk Score (2026-05)** | **18/100** |

> Riesgo normal — 18/100. 2 pacientes (1% de su cartera) con frecuencia de visitas implausible en el mes. Combinación atípica de variables según Isolation Forest/LOF (patients_per_hour_z (+11.5), utilization_z (+8.1), idle_hours_ratio_z (-8.1)).

### 15. MED0027 — 14/100 · Nivel 0 (Normal)

Peer group: Pediatría | telemedicina · Peor período: 2026-06 · Pagado total: $11,404,800 · Sin respaldo de actividad: $1,321,650 · Sobre contrato/duplicado: $0

| Dimensión | Score |
|---|---:|
| Inconsistencia contractual | 0/100 |
| Horas sin actividad / integridad del registro | 9/100 |
| Rendimiento anómalo | 10/100 |
| Diferencia frente a pares | 37/100 |
| Anomaly detection (IF + LOF) | 48/100 |
| Relaciones médico–paciente (grafo) | 0/100 |
| **Risk Score (2026-06)** | **17/100** |

> Riesgo normal — 17/100. Reglas activadas: R10 actividad concentrada artificialmente en el turno.

## Validación contra escenarios inyectados (solo data sintética)

- Precision@k (k=9): 1.00
- Médicos inyectados en nivel ≥ 3: 89%
- Médicos normales en nivel ≥ 3 (falsos positivos): 0.0%
- Médicos normales en nivel ≥ 2 / ≥ 1: 0.0% / 2.0%
- Score medio inyectados vs normales: 75.9 vs 8.1
- Ranking por escenario: ghost_records → [8]; hours_overbilling → [5]; network_billing → [2, 4]; off_schedule → [3]; phantom_hours → [6, 7]; productivity_collapse → [1, 9]
