# Payment Integrity Engine — pago médico por hora

Modelo híbrido de **Payment Integrity y detección de anomalías en pagos médicos por hora**.
Identifica *riesgo de pago indebido* (no culpabilidad) cruzando contrato, horas pagadas,
actividad clínica efectiva y comportamiento esperado del profesional, y entrega al auditor
un score explicable con la evidencia que lo sustenta.

> Estado: **MVP validado sobre data proxy sintética.** El repositorio no contenía data, por lo
> que se construyó un generador que replica el modelo de datos del diseño (contrato, agenda,
> atenciones, sesiones, pagos) con cinco escenarios de riesgo inyectados. El pipeline está
> listo para recibir data real con el contrato de tablas descrito abajo.

## Uso rápido

```bash
pip install -r requirements.txt
python -m payment_integrity                      # corre sobre data sintética → ./output
python -m payment_integrity --synthetic-out data/synthetic   # además exporta la data proxy en CSV
python -m payment_integrity --input data/real    # corre sobre CSV reales (ver "Conectar data real")
python -m pytest -q tests
```

Desde Python:

```python
from payment_integrity import run_pipeline
res = run_pipeline()                 # o run_pipeline(data={"doctors": df, "contracts": df, ...})
res.doctor_scores.head(10)           # ranking consolidado por médico
res.scored_periods                   # médico × mes con dimensiones, reglas y explicación
res.alerts                           # tabla larga de alertas por regla
```

## Arquitectura (cinco capas)

```
Contrato · Horas · Pagos · Agenda · Atenciones · Registro clínico · Sesiones
        │
        ▼  features.py — ≈30 variables derivadas (médico×día → médico×mes)
        │
   CAPA 1  Conciliación contractual     layers/reconciliation.py   contrato ↔ pagado ↔ actividad (CLP en riesgo)
   CAPA 2  Rules Engine                 layers/rules.py            13 reglas explícitas, intensidad 0-1, reglas críticas
   CAPA 3  Provider Profiling           layers/peer.py             z-score robusto (MAD) y percentiles vs pares equivalentes
   CAPA 4  Anomaly Detection            layers/anomaly.py          Isolation Forest + LOF sobre z-scores intra-peer
   CAPA E  Change Detection             layers/change.py           EWMA + CUSUM del médico contra su propio histórico
   CAPA 5  Risk Scoring + explicación   scoring.py                 score compuesto, niveles 0-4, narrativa accionable
```

### Fórmula del Risk Score

```
RiskScore = 0.20·ContractRisk + 0.25·ActivityRisk + 0.20·ProductivityRisk + 0.20·PeerRisk + 0.15·AnomalyRisk
```

| Dimensión | Fuente |
|---|---|
| ContractRisk | Capa 1 (monto sobre contrato o duplicado / pago total) y reglas R07, R08 |
| ActivityRisk | Reglas R01, R03–R06, R09–R13 (horas sin actividad, integridad del registro) |
| ProductivityRisk | Regla R02 y Change Detection (caída sostenida vs histórico propio) |
| PeerRisk | Desviación robusta en la dirección de riesgo frente al peer group |
| AnomalyRisk | Isolation Forest (0.6) + LOF (0.4), normalizados por mediana + k·MAD |

**Escalamiento por reglas críticas.** Si una regla marcada como crítica (R01, R03, R04, R05, R07,
R08, R09, R12) alcanza intensidad ≥ 0,5, el score se eleva al menos al piso de nivel 3
(60) y sobre el piso conserva el orden del puntaje ponderado. Evita que un caso con
evidencia directa de pago indebido se diluya en el promedio.

**Consolidación por médico.** `max(0,75·peor mes + 0,25·promedio, último mes)`: la persistencia
pesa (un mes aislado no condena) y la recencia manda (un cambio reciente no se diluye).

### Escala de niveles (gobernanza)

| Nivel | Score | Etiqueta | Uso |
|---|---|---|---|
| 0 | 0–20 | Normal | Sin acción |
| 1 | 20–40 | Anomalía operacional | Monitoreo |
| 2 | 40–60 | Posible error administrativo | Revisión administrativa |
| 3 | 60–75 | Posible pago indebido | Revisión de pagos |
| 4 | 75–100 | Requiere auditoría | Auditoría formal |

El fraude solo se confirma tras investigación; el modelo prioriza auditorías.

## Reglas de negocio (Capa 2)

| Código | Regla | Variable | Umbral | Saturación | Crítica |
|---|---|---|---|---|---|
| R01 | Horas pagadas sin actividad clínica | `idle_hours_ratio` | > 35 % | 60 % | ✔ |
| R02 | Rendimiento incompatible con lo esperado | `performance_ratio` | < 0,50 | 0,25 | |
| R03 | Atenciones fuera del horario contratado | `off_schedule_encounters` | > 2 | 12 | ✔ |
| R04 | Consultas simultáneas (solapadas) | `overlapping_encounters` | > 0 | 6 | ✔ |
| R05 | Atención sin sesión activa del médico | `encounters_without_login` | > 1 | 8 | ✔ |
| R06 | Mismo paciente contabilizado múltiples veces | `duplicate_patient_days` | > 1 | 6 | |
| R07 | Horas pagadas superiores a contratadas | `overpaid_days_ratio` | > 5 % | 30 % | ✔ |
| R08 | Pagos duplicados | `duplicate_payments` | > 0 | 3 | ✔ |
| R09 | Bloques pagados íntegros sin pacientes | `empty_paid_blocks_ratio` | > 5 % | 25 % | ✔ |
| R10 | Actividad concentrada artificialmente en el turno | `edge_concentration` | > 70 % | 95 % | |
| R11 | Consultas con duración físicamente improbable (< 4 min) | `improbable_duration_ratio` | > 10 % | 30 % | |
| R12 | Atenciones sin registro clínico | `missing_record_ratio` | > 10 % | 30 % | ✔ |
| R13 | Registro clínico creado retrospectivamente (> 48 h) | `retro_record_ratio` | > 10 % | 30 % | |

Intensidad = 0 en el umbral, 1 en la saturación. Todos los umbrales viven en
`payment_integrity/config.py` (`RuleThresholds`) y deben recalibrarse con data real.
R02 no es crítica deliberadamente: el bajo rendimiento por sí solo admite explicaciones
legítimas (bloqueos de agenda, complejidad, demanda, tareas administrativas).

## Modelo de datos (contrato de entrada)

Un `dict` de DataFrames (o una carpeta con `tabla.csv`). Fechas en ISO-8601.

| Tabla | Obligatoria | Columnas requeridas | Opcionales |
|---|---|---|---|
| `doctors` | ✔ | `doctor_id`, `peer_group`, `expected_rate` (pac/h), `hourly_rate` | `specialty`, `modality`, `shift` |
| `contracts` | ✔ | `doctor_id`, `date`, `contract_start`, `contract_end`, `contracted_hours` | |
| `encounters` | ✔ | `encounter_id`, `doctor_id`, `patient_id`, `date`, `start_ts`, `end_ts` | `has_clinical_record`, `record_created_ts`, `service_type` |
| `payments` | ✔ | `payment_id`, `doctor_id`, `date`, `paid_hours`, `amount` | `hourly_rate` |
| `schedule` | | `doctor_id`, `date`, `status` (`atendido`/`ausente`/`cancelado`) | `slot_start`, `patient_id` |
| `sessions` | | `doctor_id`, `date`, `login_ts`, `logout_ts` | |

Si falta una tabla opcional o una columna opcional, las variables dependientes quedan en NaN y
las reglas asociadas se omiten (R05 sin `sessions`; R12/R13 sin registro clínico; `no_show_ratio`
sin `schedule`). El resto del modelo sigue operando.

`peer_group` define contra quién se compara cada médico (p. ej. `Medicina general | telemedicina`).
Con menos de 5 pares el `peer_risk` se atenúa a la mitad y se marca `peer_reliable = False`.

## Diccionario de variables derivadas (médico × mes)

| Variable | Definición |
|---|---|
| `contracted_hours` / `paid_hours` / `total_paid` | Horas contratadas, pagadas (incluye duplicados) y monto CLP |
| `active_hours` | Horas con actividad clínica: bloques de 30 min con ≥ 1 atención dentro de la ventana pagada |
| `idle_hours`, `idle_hours_ratio` | Horas pagadas sin actividad y su fracción (R1 del diseño) |
| `utilization` | `active_hours / paid_hours` |
| `patients_attended`, `patients_per_hour` | Atenciones efectivas y rendimiento observado |
| `performance_ratio` | Rendimiento observado / esperado |
| `cost_per_patient` | Pago total / pacientes atendidos |
| `no_show_ratio` | Ausentes / agendados |
| `mean_duration_min` | Duración media de la consulta |
| `off_schedule_encounters` | Atenciones con inicio fuera de `[contract_start, contract_end)` |
| `overlapping_encounters` | Atenciones que comienzan > 1 min antes del fin de la anterior |
| `encounters_without_login` | Atenciones fuera de la ventana login–logout |
| `duplicate_patient_days` | Días con el mismo paciente contabilizado 2+ veces |
| `overpaid_days_ratio`, `overpaid_hours` | Días y horas con pago sobre lo contratado |
| `duplicate_payments` | Registros de pago adicionales para el mismo médico-día |
| `empty_paid_blocks_ratio` | Bloques pagados sin ninguna atención |
| `edge_concentration` | Fracción de atenciones que cabe en la mitad contigua más cargada del turno |
| `improbable_duration_ratio` | Fracción de consultas < 4 min |
| `missing_record_ratio`, `retro_record_ratio` | Sin registro clínico / registro creado > 48 h después |
| `*_z`, `*_pct` | z-score robusto (MAD) y percentil dentro del peer group y mes |
| `baseline_pph`, `ewma_pph`, `rel_change`, `cusum_alarm` | Change detection contra el histórico propio |

El diccionario completo se exporta en `output/feature_dictionary.json`.

## Salidas (`output/`)

| Archivo | Contenido |
|---|---|
| `doctor_scores.csv` | Ranking consolidado por médico: score, nivel, peor período, montos en riesgo, explicación |
| `scored_periods.csv` | Médico × mes con las 5 dimensiones, 13 reglas (flag + intensidad), z-scores, anomalía, cambio y narrativa |
| `alerts.csv` | Tabla larga: una fila por regla activada (valor observado, umbral, intensidad, detalle) |
| `reconciliation.csv` | Capa 1: horas y CLP conciliados, sin respaldo de actividad, sobre contrato y duplicados |
| `peer_profiles.csv` | Capa 3: z-scores, percentiles y riesgo por métrica dentro del peer group |
| `anomalies.csv` | Capa 4: scores IF/LOF y las 3 variables más desviadas por observación |
| `change_weekly.csv` | Capa E: serie semanal, EWMA, CUSUM y alarma por médico |
| `day_features.csv`, `period_features.csv` | Variables derivadas a ambas granularidades |
| `audit_report.md` | Reporte de priorización con narrativa por médico |
| `config_used.json`, `validation.json` | Trazabilidad: parámetros usados y métricas de validación |

Ejemplo de explicación entregada al auditor:

> Riesgo requiere auditoría — 86/100. Médico en percentil 99 de costo por paciente dentro de su
> peer group (Medicina interna | telemedicina, n=8). El 50 % de las horas pagadas no presenta
> actividad clínica registrada (45,0 h; $1.773.000 sin respaldo). El rendimiento cayó 59 %
> respecto de su propio histórico (2,3 → 0,9 pac/h), con señal CUSUM de cambio sostenido. Caso
> escalado a nivel ≥ 3 por regla crítica (R01). Reglas activadas: R01, R02, R10.

## Validación sobre data proxy

Data sintética: 60 médicos, 4 especialidades × 2 modalidades, 26 semanas, 9 médicos (15 %)
con escenario inyectado. La columna `doctors.scenario` **solo** se usa para evaluar; nunca
como feature.

| Escenario inyectado | Qué simula | Capas que lo capturan |
|---|---|---|
| `phantom_hours` | Turno pagado íntegro con actividad en el primer 40 % | R01, R10, peer, anomalía |
| `productivity_collapse` | Historial normal, caída 65 % en las últimas 8 semanas | R02, CUSUM/EWMA, peer |
| `hours_overbilling` | Horas pagadas > contratadas en 40 % de los días + pagos duplicados | Capa 1, R07, R08 |
| `ghost_records` | 28 % sin registro clínico, 22 % consultas de 1–3 min, paciente repetido | R06, R11, R12, R13, anomalía |
| `off_schedule` | Atenciones fuera de horario, solapadas y sin sesión activa | R03, R04, R05, anomalía |

Resultado con la configuración por defecto (`output/validation.json`):

| Métrica | Valor |
|---|---|
| Precision@9 / Recall@9 (ranking por médico) | 1,00 / 1,00 |
| Inyectados en nivel ≥ 3 | 8 de 9 |
| Normales en nivel ≥ 3 / ≥ 2 / ≥ 1 | 0 % / 0 % / 5,9 % |
| Score medio inyectados vs normales | 77,3 vs 9,2 |

El caso inyectado que queda en nivel 2 es una caída de rendimiento sin quiebre contractual
(el médico sigue distribuyendo sus pocas atenciones a lo largo del turno). Es el comportamiento
esperado: el diseño establece que el bajo rendimiento por sí solo no es evidencia de pago
indebido, pero el reporte lo entrega con la caída cuantificada y la alarma CUSUM para revisión.

## Conectar data real

1. Construir las tablas del contrato de entrada desde los sistemas fuente (RR. HH./contratos,
   remuneraciones, agenda, ficha clínica, logs de acceso) y dejarlas como `data/real/<tabla>.csv`.
2. Definir `peer_group` con criterio clínico (especialidad × modalidad × turno es el punto de partida).
3. Definir `expected_rate` por peer group con el área clínica; si no existe, usar la mediana
   observada del grupo como proxy inicial.
4. Correr `python -m payment_integrity --input data/real --output output/real`.
5. Calibrar umbrales en `config.py` mirando `period_features.csv`: los umbrales deben dejar a la
   mayoría de los médicos en nivel 0–1. Registrar cada cambio en `config_used.json`.
6. Revisar los casos nivel 3–4 con auditoría y registrar el resultado
   (`NORMAL`, `ERROR_ADMINISTRATIVO`, `PAGO_INDEBIDO_CONFIRMADO`, `ABUSO`, `FRAUDE_CONFIRMADO`).
   Con esa base histórica se habilita la capa supervisada (XGBoost/LightGBM) y la calibración de pesos.

## Supuestos y límites

- **Proxy de "hora con actividad"**: bloques de 30 min con al menos una atención. Con data real puede
  refinarse con eventos del sistema (apertura de ficha, prescripciones, firma).
- **Sin etiquetas**: los pesos del score y los umbrales son juicio experto inicial, no aprendidos.
  La validación demuestra separación sobre escenarios sintéticos, no rendimiento en producción.
- **Ventana de agregación mensual**: elegida por coherencia con el ciclo de pago. Las reglas
  R04/R05/R08 operan sobre conteos por mes; con muy pocos días trabajados aumenta la varianza.
- **Peer groups pequeños**: bajo 5 pares la comparación se atenúa; en producción conviene
  ampliar el grupo (p. ej. sin distinguir turno) antes que comparar contra 3 colegas.
- **No es un modelo de fraude**: identifica riesgo de pago indebido y prioriza auditorías. Todo
  caso nivel 3–4 requiere revisión humana antes de cualquier acción laboral o administrativa.
- **Graph analytics y modelo supervisado** (capas D y F del diseño) quedan fuera del MVP a la
  espera de prestaciones individuales y de una base de auditorías cerradas.

## Estructura del repositorio

```
payment_integrity/
  config.py            umbrales, pesos, parámetros (única fuente de verdad)
  synthetic.py         generador de data proxy con escenarios inyectados
  features.py          variables derivadas médico×día y médico×mes; validación del contrato de entrada
  layers/
    reconciliation.py  capa 1
    rules.py           capa 2
    peer.py            capa 3
    anomaly.py         capa 4
    change.py          capa E
  scoring.py           capa 5 + narrativa + consolidación por médico
  pipeline.py          orquestación, validación, exportación, reporte
  __main__.py          CLI
tests/test_pipeline.py
requirements.txt
```
