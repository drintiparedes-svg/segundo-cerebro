# Payment Integrity Engine — Manual de uso y reglas de indicadores y métricas

Versión 1.0 · Septiembre 2026 · Modelo de Payment Integrity y detección de anomalías en pagos médicos por hora

---

## 1. Propósito y principio rector

El sistema identifica **riesgo de pago indebido** en esquemas de remuneración médica por hora, cruzando contrato, horas pagadas, actividad clínica efectivamente registrada, comportamiento esperado del profesional y relaciones médico–paciente. Su producto es una **priorización de auditoría explicable**, no una imputación.

Principios no negociables:

1. El score mide riesgo de pago indebido; el fraude solo se confirma tras investigación humana.
2. Todo caso de nivel 3 o 4 requiere revisión de un auditor antes de cualquier acción administrativa o laboral.
3. Cada alerta viene acompañada de la evidencia cuantificada que la sustenta (horas, montos, percentiles, coincidencias).
4. Los parámetros del modelo son explícitos, están en un solo archivo de configuración y deben recalibrarse con data real.

## 2. Arquitectura en una página

| Capa | Módulo | Qué hace | Salida |
|---|---|---|---|
| Calidad de datos | `quality.py` | Valida el contrato de datos, fechas, claves, integridad referencial y cobertura | Tabla de checks con severidad |
| Features | `features.py` | Deriva unas 30 variables por médico-día y médico-mes | `period_features` |
| 1 · Conciliación contractual | `layers/reconciliation.py` | Cruza contrato, pago y actividad; cuantifica pesos sin respaldo | `reconciliation`, ContractRisk |
| 2 · Reglas de negocio | `layers/rules.py` | 13 reglas explícitas con umbral, saturación e intensidad 0-1 | `alerts`, ActivityRisk, ProductivityRisk |
| 3 · Perfil de pares | `layers/peer.py` | Z-score robusto (MAD) y percentiles dentro del peer group | PeerRisk |
| 4 · Anomalías | `layers/anomaly.py` | Isolation Forest y LOF sobre z-scores intra-grupo | AnomalyRisk |
| E · Cambio de comportamiento | `layers/change.py` | EWMA y CUSUM del médico contra su propio histórico | Refuerza ProductivityRisk |
| F · Grafo | `layers/graph.py` | Relaciones médico–paciente–tiempo: compartidos, simultáneos, concentración, comunidades | GraphRisk, G01 |
| 5 · Scoring | `scoring.py` | Score compuesto 0-100, escalamiento crítico, niveles 0-4, narrativa | `scored_periods`, `doctor_scores` |
| D · Supervisada | `layers/supervised.py` | Gradient boosting con auditorías cerradas | `supervised_prob` |
| Gestión de casos | `casework.py` | Decisiones del auditor, historial y corridas en SQLite | Etiquetas para la capa D |
| Reportería | `reporting.py` | Informe HTML, Markdown, Excel, CSV | Paquete de hallazgos |

## 3. Instalación y ejecución

### 3.1 Local

```bash
git clone <repositorio>
cd segundo-cerebro
pip install -r requirements.txt
streamlit run app/dashboard.py          # tablero en http://localhost:8501
python -m payment_integrity             # corrida por línea de comando sobre data sintética
python -m pytest -q tests               # suite de pruebas
```

### 3.2 Línea de comando

| Comando | Efecto |
|---|---|
| `python -m payment_integrity --input data/real --output output/real` | Corre el modelo sobre CSV reales |
| `python -m payment_integrity --labels auditorias.csv` | Importa auditorías cerradas y entrena la capa supervisada |
| `python -m payment_integrity --synthetic-out data/synthetic` | Exporta la data sintética para pruebas |
| `python -m payment_integrity --no-db` | No registra la corrida en la base de casos |

### 3.3 Despliegue

| Modalidad | Uso | Cómo |
|---|---|---|
| Contenedor (Render, Railway, Cloud Run, servidor propio) | Tablero interactivo completo: carga de archivos, modelo, gestión de casos | `docker build -t payment-integrity . && docker run -p 8501:8501 payment-integrity` |
| Streamlit Community Cloud | Tablero interactivo completo desde el repositorio GitHub | Importar el repo, archivo principal `app/dashboard.py` |
| Vercel | **Solo la vista estática de demostración** (`web/`): resultados precalculados, gráficos e informe. Vercel no ejecuta servidores persistentes como Streamlit | Importar el repo en Vercel; `vercel.json` publica la carpeta `web` |

Regenerar la vista estática tras cambiar el modelo: `python scripts/export_static_data.py web`.

Para producción con datos reales, la recomendación es contenedor en infraestructura institucional: los datos de pago y actividad clínica no deben salir del perímetro de la organización.

## 4. Flujo de uso del tablero

### Sección 1 · Carga de datos

1. Arrastrar los archivos al cargador, en el formato en que los entrega el sistema de origen (ver sección 4 bis).
2. Pulsar **Leer y validar archivos**. El sistema identifica las tablas, traduce las columnas, ejecuta el control de calidad y muestra el informe de ingesta.
3. Revisar la tabla de calidad. Los checks de severidad ERROR bloquean la ejecución; las ADVERTENCIAS degradan la confianza de alguna capa; INFO es contexto.
4. Ajustar, si corresponde, los parámetros en la barra lateral (umbrales R01, R02, R12, mínimo de pares y pesos).
5. Pulsar **Ejecutar modelo**. La corrida queda registrada en la base de casos con su configuración.

El botón **Usar data de demostración** genera 60 médicos y 26 semanas con seis escenarios de riesgo inyectados. Sirve para conocer el sistema y validar la instalación.

### Sección 2 · Resumen ejecutivo

KPIs del período, distribución por nivel, histograma de scores, top N de médicos priorizados, evolución mensual y ranking consolidado. Cada gráfico tiene su tabla equivalente.

### Sección 3 · Métricas

Filtros por peer group, período y nivel mínimo. Cinco pestañas: productividad y costo, perfil de pares, reglas, anomalías y conciliación, y grafo de relaciones.

### Sección 4 · Ficha por médico

Score consolidado, nivel, explicación accionable, seis dimensiones, comparación con pares, serie semanal con línea base, EWMA y alarmas CUSUM, horas pagadas versus con actividad, señales de grafo y vecindario, trayectoria mensual y alertas por regla. Es la vista que usa el auditor para preparar la revisión.

### Sección 5 · Reportería

Informe filtrable por nivel mínimo, top N y peer group. Exportaciones: HTML imprimible, Markdown, Excel de cinco hojas, CSV de hallazgos y paquete ZIP con todas las tablas y la configuración usada.

### Sección 6 · Gestión de casos

Cola de casos por nivel, registro de decisiones (estado, resultado, auditor, comentario), historial completo, carga masiva de auditorías cerradas y entrenamiento de la capa supervisada.

## 4 bis. Formatos de archivo aceptados

No es necesario preparar los archivos ni renombrar columnas: el sistema los acepta como los entrega la fuente.

| Aspecto | Qué acepta |
|---|---|
| Formatos | CSV, TSV, TXT, Excel (.xlsx, .xlsm, .xls, una o varias hojas), JSON, NDJSON, Parquet, ZIP |
| Separador | Coma, punto y coma, tabulador o barra vertical, detectado automáticamente |
| Codificación | UTF-8, UTF-8 con BOM, Latin-1, CP1252 |
| Nombres de columna | En español o inglés, con o sin acentos, mayúsculas o guiones |
| Fechas | ISO-8601 y DD/MM/AAAA |
| Montos | `$1.234.567,89` (local) y `1,234,567.89` (anglosajón) |
| Estados de agenda | `atendido`, `ATENDIDA`, `Realizada`, `No Asiste`, `Anulada` y equivalentes |
| Organización | Un archivo por tabla, un único Excel con una hoja por tabla, o un ZIP con todo |

Cada tabla se identifica por el nombre del archivo o de la hoja y, si eso no basta, por las columnas
presentes. Un alias ambiguo se resuelve según la tabla: `Hora Inicio` es inicio de turno en contratos,
comienzo de la atención en atenciones e inicio de sesión en los logs de acceso.

Si faltan columnas que pueden deducirse, se derivan y se deja constancia: `peer_group` desde especialidad
y modalidad, `hourly_rate` desde monto dividido por horas pagadas, y `expected_rate` desde la mediana
observada del peer group. Esta última es un proxy inicial que debe validarse con el área clínica.

El **informe de ingesta** que aparece tras la carga registra el formato detectado, la codificación, el
separador, cada columna traducida, las columnas no reconocidas y los valores que no se pudieron
interpretar. Revíselo antes de dar por buena la carga: una columna mal mapeada invalida el análisis.

## 5. Contrato de datos

| Tabla | Obligatoria | Columnas requeridas | Opcionales | Fuente habitual |
|---|---|---|---|---|
| `doctors` | Sí | `doctor_id`, `peer_group`, `expected_rate`, `hourly_rate` | `specialty`, `modality`, `shift` | RR. HH., contratos |
| `contracts` | Sí | `doctor_id`, `date`, `contract_start`, `contract_end`, `contracted_hours` | | Contratos, turnos |
| `encounters` | Sí | `encounter_id`, `doctor_id`, `patient_id`, `date`, `start_ts`, `end_ts` | `has_clinical_record`, `record_created_ts`, `service_type` | Ficha clínica, HIS |
| `payments` | Sí | `payment_id`, `doctor_id`, `date`, `paid_hours`, `amount` | `hourly_rate` | Remuneraciones |
| `schedule` | No | `doctor_id`, `date`, `status` | `slot_start`, `patient_id` | Agenda |
| `sessions` | No | `doctor_id`, `date`, `login_ts`, `logout_ts` | | Logs del sistema clínico |

Convenciones:

- Fechas y timestamps en ISO-8601 (`AAAA-MM-DD` y `AAAA-MM-DD HH:MM:SS`).
- `status` de agenda con valores `atendido`, `ausente`, `cancelado`.
- `has_clinical_record` booleano. Si falta, las reglas R12 y R13 se omiten.
- Un registro de `payments` por médico y día. Dos registros el mismo día se interpretan como pago duplicado (R08).
- `peer_group` define contra quién se compara cada médico. Punto de partida: especialidad × modalidad × turno. Con menos de cinco pares la comparación se atenúa a la mitad.
- `expected_rate` es el rendimiento esperado en pacientes por hora, definido con el área clínica. Si no existe, usar la mediana observada del peer group como proxy inicial.

## 6. Control de calidad de datos

| Check | Severidad | Efecto |
|---|---|---|
| Tabla o columna obligatoria ausente | ERROR | Bloquea la ejecución |
| Fechas no interpretables | ERROR | Bloquea |
| `doctor_id` inexistente en `doctors` | ERROR | Bloquea: el médico no tendría peer group ni rendimiento esperado |
| Fin de atención anterior al inicio; horas pagadas negativas; `expected_rate` ausente o ≤ 0 | ERROR | Bloquea |
| Claves duplicadas en `doctors`, `encounters`, `contracts` | ERROR | Bloquea |
| Claves duplicadas en `payments` | ADVERTENCIA | Puede ser un pago duplicado real (R08) |
| Nulos en columnas clave, horas pagadas > 16 al día, atenciones > 4 horas | ADVERTENCIA | Revisar la fuente; el modelo corre |
| Días pagados sin contrato; atenciones en días sin contrato | ADVERTENCIA | Alimentan ContractRisk y R03 |
| Peer groups con menos de 5 médicos | ADVERTENCIA | PeerRisk atenuado |
| Tablas opcionales ausentes | INFO | Reglas dependientes omitidas |

## 7. Diccionario de indicadores y métricas

Todas las métricas se calculan por **médico y mes** salvo indicación. "Hora con actividad" es un bloque de 30 minutos, dentro de la ventana pagada, con al menos una atención registrada.

### 7.1 Horas y pagos

| Indicador | Fórmula | Unidad | Lectura |
|---|---|---|---|
| Horas contratadas | Σ `contracted_hours` de los bloques del mes | h | Base contractual |
| Horas pagadas | Σ `paid_hours` (incluye duplicados) | h | Lo efectivamente remunerado |
| Horas con actividad | Bloques de 30 min con ≥ 1 atención × 0,5, tope en horas pagadas | h | Actividad clínica demostrable |
| Horas ociosas (`idle_hours`) | Horas pagadas − horas con actividad | h | Horas pagadas sin respaldo de actividad |
| Ratio de horas ociosas (`idle_hours_ratio`) | Horas ociosas / horas pagadas | % | Regla R01. Referencia esperada 5–15 % |
| Utilización | Horas con actividad / horas pagadas | % | Complemento del anterior |
| Horas pagadas / contratadas | Horas pagadas / horas contratadas | ratio | > 1 indica pago sobre contrato |
| Monto sin respaldo (`idle_amount`) | Horas ociosas × valor hora | CLP | Monto a revisar, no pérdida confirmada |
| Monto sobre contrato o duplicado (`amount_at_risk`) | (Horas pagadas − contratadas)⁺ × valor hora + pagos duplicados | CLP | Evidencia directa de la conciliación |

### 7.2 Producción y costo

| Indicador | Fórmula | Unidad | Lectura |
|---|---|---|---|
| Pacientes atendidos | N° de atenciones registradas | n | |
| Pacientes por hora | Pacientes atendidos / horas pagadas | pac/h | Rendimiento observado |
| Rendimiento vs esperado (`performance_ratio`) | Pacientes por hora / `expected_rate` | ratio | Regla R02. Referencia 0,7–1,1 |
| Costo por paciente | Monto pagado / pacientes atendidos | CLP | Métrica clave de comparación con pares |
| No-show | Ausentes / agendados | % | Contexto para rendimiento bajo legítimo |
| Duración media | Media de (fin − inicio) de las atenciones | min | Base para R11 |

### 7.3 Integridad del registro

| Indicador | Definición | Regla |
|---|---|---|
| Atenciones fuera de horario | Inicio fuera de `[contract_start, contract_end)` o en día sin contrato | R03 |
| Atenciones solapadas | Inicio más de 1 minuto antes del fin de la atención anterior del mismo médico | R04 |
| Atenciones sin sesión activa | Inicio fuera de la ventana login–logout del día | R05 |
| Días con paciente repetido | Días con el mismo paciente contabilizado 2 o más veces por el mismo médico | R06 |
| Días con pago sobre contrato | Días con horas pagadas > contratadas | R07 |
| Pagos duplicados | Registros adicionales de pago para el mismo médico y día | R08 |
| Bloques pagados sin pacientes | Días con horas pagadas y cero atenciones | R09 |
| Concentración en el turno (`edge_concentration`) | Fracción de atenciones que cabe en la mitad contigua más cargada del turno | R10 |
| Duración improbable | Fracción de atenciones con duración < 4 minutos | R11 |
| Sin registro clínico | Fracción de atenciones con `has_clinical_record` falso | R12 |
| Registro retrospectivo | Fracción con registro creado más de 48 horas después del término | R13 |

### 7.4 Comparación con pares

| Indicador | Fórmula | Lectura |
|---|---|---|
| Z robusto | 0,6745 × (x − mediana del grupo) / MAD del grupo; si MAD = 0, IQR / 1,349 | Desviación resistente a distribuciones sesgadas |
| Percentil en el grupo | Rango percentil dentro del peer group y mes | Se muestra en la narrativa |
| Dirección de riesgo | Bajo: pacientes por hora, utilización, duración media. Alto: costo por paciente, ratio ociosas, no-show | Solo la desviación en la dirección de riesgo suma |
| Saturación | \|z\| = 3,5 satura el riesgo de la métrica | Percentil ≈ 99,9 |

### 7.5 Cambio de comportamiento

| Indicador | Definición |
|---|---|
| Línea base propia | Mediana de pacientes por hora en las primeras 8 semanas del médico |
| EWMA | Media móvil exponencial con α = 0,3 de la serie semanal |
| Cambio relativo (`rel_change`) | (EWMA − línea base) / línea base, promedio de las semanas del mes |
| Alarma CUSUM | CUSUM unilateral de caídas con deriva 0,5 y umbral 4 desviaciones robustas |
| Riesgo de cambio | Caída relativa / 0,60, saturado en 1; se pondera por 1 si hay alarma CUSUM y por 0,5 si no; cero durante la línea base |

### 7.6 Relaciones médico–paciente (grafo)

| Indicador | Definición | Señal |
|---|---|---|
| Pacientes compartidos | Fracción de la cartera del mes que también atendió otro médico | Riesgo desde máx(2 × mediana del grupo, 25 %) hasta saturar en +50 puntos |
| Atenciones simultáneas | Atenciones del médico que coinciden en el tiempo con una atención de otro médico al mismo paciente | Satura en 6; 3 o más escalan el caso (G01) |
| Concentración de cartera | Atenciones por paciente en múltiplos de la mediana del grupo; HHI y participación del top 5 | Riesgo desde 2× y saturación en 4× |
| Visitas implausibles | Fracción de la cartera con 4 o más atenciones en el mes | Satura en 25 % |
| Vínculo más fuerte | Médico con más pacientes en común y su índice de Jaccard | Se cita en la narrativa |
| Comunidad | Grupo detectado por modularidad sobre aristas con 3 o más pacientes en común | Tamaño de la comunidad |

## 8. Reglas de negocio

La intensidad de cada regla vale 0 en el umbral y 1 en el punto de saturación, lineal entre ambos. Las reglas **críticas** escalan el caso por sí solas cuando su intensidad alcanza 0,5.

| Código | Regla | Variable | Umbral | Saturación | Dimensión | Crítica | Qué revisar en auditoría | Causas legítimas a descartar |
|---|---|---|---|---|---|---|---|---|
| R01 | Horas pagadas sin actividad clínica | `idle_hours_ratio` | > 35 % | 60 % | Actividad | Sí | Distribución horaria de atenciones, tareas no asistenciales pactadas | Comités, docencia, gestión, bloqueos de agenda autorizados |
| R02 | Rendimiento incompatible con lo esperado | `performance_ratio` | < 0,50 | 0,25 | Productividad | No | Complejidad de casos, demanda, no-show | Baja demanda, pacientes complejos, licencias parciales |
| R03 | Atenciones fuera del horario contratado | `off_schedule_encounters` | > 2 | 12 | Actividad | Sí | Horas extraordinarias autorizadas, errores de registro | Extensión de turno aprobada, desfase de reloj del sistema |
| R04 | Consultas simultáneas | `overlapping_encounters` | > 0 | 6 | Actividad | Sí | Timestamps de inicio y fin, registro por lotes | Cierre tardío de fichas en bloque |
| R05 | Atención sin sesión activa | `encounters_without_login` | > 1 | 8 | Actividad | Sí | Logs de acceso, delegación de credenciales | Sesión abierta en otro equipo, falla del log |
| R06 | Mismo paciente contabilizado múltiples veces | `duplicate_patient_days` | > 1 | 6 | Actividad | No | Procedimientos múltiples legítimos el mismo día | Control más procedimiento, reingreso |
| R07 | Horas pagadas superiores a contratadas | `overpaid_days_ratio` | > 5 % de los días | 30 % | Contrato | Sí | Anexos de contrato, horas extraordinarias | Extensión formalizada no cargada en contratos |
| R08 | Pagos duplicados | `duplicate_payments` | > 0 | 3 | Contrato | Sí | Liquidaciones del período | Reproceso de nómina con reverso no registrado |
| R09 | Bloques pagados sin pacientes | `empty_paid_blocks_ratio` | > 5 % de los días | 25 % | Actividad | Sí | Actividad no asistencial del día | Capacitación, licencia parcial, falla de agenda |
| R10 | Actividad concentrada en el turno | `edge_concentration` | > 70 % | 95 % | Actividad | No | Patrón de llegada de pacientes | Demanda concentrada por diseño de agenda |
| R11 | Duración físicamente improbable | `improbable_duration_ratio` | > 10 % | 30 % | Actividad | No | Definición de inicio y fin en el sistema | Registro del cierre inmediato tras la atención real |
| R12 | Atenciones sin registro clínico | `missing_record_ratio` | > 10 % | 30 % | Actividad | Sí | Existencia de evolución, receta o indicación | Registro en sistema paralelo no integrado |
| R13 | Registro clínico retrospectivo | `retro_record_ratio` | > 10 % | 30 % | Actividad | No | Fecha de creación versus fecha de atención | Regularización masiva tras caída del sistema |
| G01 | Mismo paciente, dos médicos, mismo instante | `simultaneous_encounters` | ≥ 3 | — | Grafo | Sí | Ambas fichas, agenda y logs de los dos médicos | Atención conjunta documentada (interconsulta simultánea) |

R02 no es crítica por diseño: el bajo rendimiento por sí solo admite explicaciones legítimas. Lo que lo vuelve relevante es su combinación con horas ociosas, desviación frente a pares o caída sostenida.

## 9. Risk Score y niveles

### 9.1 Dimensiones

| Dimensión | Peso | Cómo se construye |
|---|---|---|
| ContractRisk | 0,18 | Máximo entre reglas R07 y R08 y la intensidad de conciliación (monto sobre contrato o duplicado / pago total, satura en 15 %) |
| ActivityRisk | 0,22 | 0,6 × máxima intensidad ponderada + 0,4 × media de las reglas activas de actividad e integridad |
| ProductivityRisk | 0,18 | Máximo entre R02 y (0,7 × riesgo de cambio + 0,3 × R02) |
| PeerRisk | 0,18 | 0,6 × máximo + 0,4 × media de las desviaciones en dirección de riesgo, atenuado al 50 % con menos de 5 pares |
| AnomalyRisk | 0,14 | 0,6 × Isolation Forest + 0,4 × LOF, cada uno llevado a 0-1 entre mediana + 2 MAD y mediana + 6 MAD |
| GraphRisk | 0,10 | 0,6 × máximo + 0,4 × media de las cuatro señales de grafo |

### 9.2 Fórmula

```
Score ponderado = 0,18·Contract + 0,22·Activity + 0,18·Productivity + 0,18·Peer + 0,14·Anomaly + 0,10·Graph
```

**Escalamiento crítico.** Si alguna regla crítica alcanza intensidad ≥ 0,5, o G01 se activa, el score final es al menos 60 y sobre ese piso conserva el orden del score ponderado: `60 + ponderado × 0,40`.

**Consolidación por médico.** `máx(0,75 × peor mes + 0,25 × promedio de meses, último mes)`. La persistencia pesa y la recencia manda.

### 9.3 Niveles y acciones

| Nivel | Score | Etiqueta | Acción sugerida | Plazo orientativo |
|---|---|---|---|---|
| 0 | 0–20 | Normal | Sin acción | — |
| 1 | 20–40 | Anomalía operacional | Monitoreo en el próximo ciclo de pago | Siguiente corrida |
| 2 | 40–60 | Posible error administrativo | Revisión administrativa de agenda, contrato y registro | 15 días |
| 3 | 60–75 | Posible pago indebido | Revisión de pagos y solicitud de descargos al profesional | 10 días |
| 4 | 75–100 | Requiere auditoría | Auditoría formal con reconstrucción de actividad y cruce de fuentes | Inmediato |

### 9.4 Cómo leer la narrativa

Ejemplo: *"Riesgo requiere auditoría — 86/100. Médico en percentil 99 de costo por paciente dentro de su peer group (n=8). El 50 % de las horas pagadas no presenta actividad clínica registrada (45,0 h; $1.773.000 sin respaldo). El rendimiento cayó 59 % respecto de su propio histórico, con señal CUSUM de cambio sostenido. Caso escalado a nivel ≥ 3 por regla crítica (R01)."*

Cada frase corresponde a una capa: pares, actividad, cambio, escalamiento. El auditor debe verificar en la fuente primaria cada afirmación antes de concluir.

## 10. Calibración con data real

1. Correr el modelo sobre un período cerrado de al menos seis meses.
2. Revisar `period_features` y la pestaña de perfil de pares: la mayoría de los médicos debe quedar en nivel 0 o 1. Si más del 10 % queda en nivel 2 o superior sin evidencia, subir los umbrales de las reglas que más disparan.
3. Ajustar `expected_rate` por peer group con el área clínica.
4. Verificar que los peer groups tengan al menos cinco médicos; de lo contrario, agrupar.
5. Documentar cada cambio de parámetro. La corrida guarda la configuración usada en la base de casos y en `config_used.json`.
6. Auditar los casos de nivel 3 y 4 y registrar el resultado en la sección 6. Con 20 casos cerrados y 5 por clase se habilita la capa supervisada.
7. Revisar trimestralmente los pesos del score con los resultados de auditoría.

## 11. Ciclo de auditoría y gestión de casos

| Estado | Significado |
|---|---|
| PENDIENTE | Priorizado por el modelo, sin revisión |
| EN_REVISION | Asignado a un auditor |
| CERRADO | Con resultado registrado |

| Resultado | Etiqueta para la capa supervisada |
|---|---|
| NORMAL | 0 |
| ERROR_ADMINISTRATIVO | 0 |
| PAGO_INDEBIDO_CONFIRMADO | 1 |
| ABUSO | 1 |
| FRAUDE_CONFIRMADO | 1 |

Todas las decisiones quedan en historial con auditor, fecha, comentario, score y nivel al momento de la decisión y corrida de origen.

## 12. Reportería

| Formato | Contenido | Destinatario |
|---|---|---|
| HTML imprimible | Resumen, distribución por nivel con gráficos, ranking, fichas de hallazgos, relaciones, metodología | Comité, dirección |
| Markdown | Mismo contenido en texto | Repositorio, trazabilidad |
| Excel (5 hojas) | Resumen, hallazgos, alertas, ranking, médico-períodos | Equipo de auditoría, Google Sheets |
| CSV de hallazgos | Una fila por médico priorizado con todas las evidencias | Integración con otros sistemas |
| ZIP | Todas las tablas intermedias, informe y configuración | Archivo de la corrida |

## 13. Gobernanza, límites y buenas prácticas

- Denominación: "Modelo de Payment Integrity y detección de anomalías en pagos médicos". Evitar "modelo de fraude" en comunicaciones con profesionales.
- Los datos de pago y actividad clínica se procesan dentro del perímetro institucional. No usar la demostración pública con datos reales.
- El proxy de "hora con actividad" se basa en atenciones registradas; con eventos del sistema (apertura de ficha, prescripción, firma) puede refinarse.
- La detección de atenciones simultáneas depende de timestamps precisos; con relojes o registros imprecisos, aumentar la tolerancia en la configuración de grafo.
- La capa supervisada con menos de 60 auditorías es orientativa. Nunca sustituye la revisión.
- Los umbrales y pesos por defecto provienen de juicio experto y validación sobre data sintética; su validez en producción depende de la calibración descrita en la sección 10.

## 14. Anexo · Parámetros de configuración por defecto

| Grupo | Parámetro | Valor |
|---|---|---|
| Reglas | Umbrales R01–R13 | Ver sección 8 |
| Pares | Métricas comparadas | pacientes por hora, utilización, costo por paciente, ratio ociosas, duración media, no-show |
| Pares | Saturación z; mínimo de pares | 3,5; 5 |
| Anomalías | Contaminación; árboles; vecinos LOF | 0,06; 400; 15 |
| Anomalías | Normalización | mediana + 2 MAD → 0; mediana + 6 MAD → 1 |
| Cambio | α EWMA; semanas base; umbral y deriva CUSUM; saturación de caída | 0,3; 8; 4 y 0,5; 60 % |
| Grafo | Tolerancia simultaneidad; saturación simultáneas; saturación compartidos | 0 min; 6; +50 puntos |
| Grafo | Visitas implausibles; saturación fracción; compuerta concentración; mínimo comunidad | 4; 25 %; 2×; 3 |
| Scoring | Pesos | 0,18 / 0,22 / 0,18 / 0,18 / 0,14 / 0,10 |
| Scoring | Intensidad crítica; piso; G01 | 0,5; 60; 3 atenciones |
| Supervisada | Mínimo de etiquetas; mínimo por clase | 20; 5 |

Todos los valores viven en `payment_integrity/config.py`.
