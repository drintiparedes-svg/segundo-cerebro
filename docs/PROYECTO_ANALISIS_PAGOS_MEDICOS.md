# Proyecto · Análisis de integridad y eficiencia en el pago médico por hora

Documento de contexto e instrucciones para un Proyecto de Claude.
Versión 1.0 · Septiembre 2026

---

## 1. Para qué sirve este documento

Es el conocimiento base de un Proyecto de Claude dedicado al **análisis exploratorio** de los datos de pago médico por hora. Define el objetivo, el alcance de esta fase, los datos, las preguntas a responder, los indicadores, los patrones a buscar, los productos esperados y las reglas de trabajo.

Cárgalo como archivo de conocimiento del Proyecto y usa la sección 10 como instrucciones personalizadas.

---

## 2. Objetivo permanente

Asegurar la **integridad de los pagos por hora médica**: que lo pagado corresponda a lo contratado y a la actividad clínica efectivamente realizada, y que las diferencias tengan explicación conocida y trazable.

Este objetivo no cambia. Lo que cambia es cómo se persigue en esta fase.

## 3. Cambio de enfoque

| | Enfoque anterior | Enfoque de esta fase |
|---|---|---|
| Producto | Motor de scoring que prioriza auditorías | Análisis exploratorio de la data |
| Pregunta guía | ¿Qué médico presenta riesgo de pago indebido? | ¿Qué está ocurriendo en estos datos y qué explica lo que veo? |
| Alcance | Detección de anomalías de pago | Ineficiencias, incongruencias, errores y oportunidades de mejora |
| Salida | Score, nivel de riesgo, cola de auditoría | Hallazgos con evidencia, hipótesis y propuestas |
| Sujeto | El profesional | El proceso, el dato y el sistema |
| Automatización | Modelo ejecutable recurrente | Análisis conducido, con criterio humano en cada paso |

El desplazamiento del sujeto es deliberado y es la decisión más importante del documento. En esta fase el objeto de análisis es **el proceso**, no la persona. Un mismo hallazgo (por ejemplo, horas pagadas sin actividad registrada) puede originarse en un problema de agenda, de registro clínico, de contrato mal cargado o de conducta individual, y en esta fase no corresponde asumir lo último.

## 4. Alcance de esta fase

**Dentro del alcance**

- Caracterizar la data disponible: cobertura, calidad, granularidad, vacíos.
- Describir el comportamiento observado: horas, producción, costo, variabilidad.
- Detectar ineficiencias operacionales.
- Detectar incongruencias entre fuentes que deberían concordar.
- Detectar errores de dato y de proceso.
- Formular hipótesis explicativas y proponer mejoras priorizadas.
- Determinar qué preguntas requieren datos que hoy no existen.

**Fuera del alcance**

- Calcular puntajes de riesgo por profesional.
- Clasificar a nadie como sospechoso.
- Automatizar decisiones.
- Construir código de producción.

## 5. Datos

### 5.1 Tablas

| Tabla | Contenido | Sistema de origen | Sin ella se pierde |
|---|---|---|---|
| Médicos | Identificador, especialidad, modalidad, turno, valor hora | RR. HH. o contratos | Toda comparación entre pares |
| Contratos | Bloques por médico y día: inicio, término, horas pactadas | Contratos o programación | La referencia contra la cual comparar el pago |
| Atenciones | Una fila por atención: médico, paciente, inicio y término con hora | Ficha clínica o HIS | La medida de actividad real |
| Pagos | Por médico y día: horas pagadas y monto | Remuneraciones | El objeto mismo del análisis |
| Agenda | Cita, fecha, estado (atendido, ausente, cancelado) | Agenda | Distinguir baja producción por inasistencia de baja producción del profesional |
| Sesiones | Ingreso y salida del sistema clínico | Logs de acceso | Verificar presencia efectiva |

Las dos últimas figuran como opcionales en el diseño técnico, pero en el análisis son las que permiten separar causa de síntoma. Conseguirlas debe ser prioridad.

### 5.2 Período

Mínimo seis meses cerrados. Comparar a un profesional consigo mismo exige una línea base de al menos ocho semanas antes del período que se quiere evaluar.

### 5.3 Advertencia sobre la calidad del dato

La experiencia de esta construcción mostró que la data institucional llega con fricciones sistemáticas. Estas no son molestias: **son hallazgos en sí mismos**, porque revelan cómo opera el registro.

| Fricción | Qué revela |
|---|---|
| Fechas en DD/MM/AAAA mezcladas con otros formatos | Falta de estándar entre sistemas |
| Codificación Latin-1 en exportaciones | Sistemas legados sin normalización |
| Separadores distintos por sistema | Ausencia de una capa de integración |
| Nombres de columna inconsistentes | Sin diccionario de datos institucional |
| Identificadores del mismo médico distintos entre sistemas | Falta de maestro único de profesionales |
| Timestamps con hora imprecisa o truncada | El registro se hace por lotes, no en el momento |

Ese último punto es especialmente relevante: si los horarios de atención se registran al final de la jornada y no durante, muchas mediciones de simultaneidad y duración pierden validez. **Verificar cómo y cuándo se registra cada dato antes de interpretar cualquier patrón temporal.**

---

## 6. Preguntas de análisis

Este es el núcleo del trabajo. Están ordenadas de lo descriptivo a lo interpretativo.

### 6.1 Conciliación entre contrato, pago y actividad

1. ¿Cuántas horas se contrataron, cuántas se pagaron y cuántas tienen actividad clínica registrada? ¿Cuánto suman las diferencias en pesos?
2. ¿Existen días pagados sin contrato vigente? ¿Corresponden a horas extraordinarias formalizadas?
3. ¿Existen contratos sin pago asociado? ¿Es desfase del ciclo de remuneraciones o una omisión?
4. ¿Hay pagos duplicados para el mismo médico y día? ¿Son reprocesos de nómina o duplicaciones reales?
5. ¿La suma de lo pagado coincide con horas contratadas por valor hora? ¿Dónde no calza y por qué?

### 6.2 Eficiencia operacional

6. ¿Cuál es la utilización real de las horas pagadas, es decir, la proporción con actividad registrada?
7. ¿Cómo se distribuye la actividad dentro del turno? ¿Hay bloques sistemáticamente vacíos al inicio o al final?
8. ¿Cuánta capacidad se pierde por inasistencia de pacientes y cuánta por diseño de agenda?
9. ¿Qué proporción de los cupos agendados se convierte en atención efectiva, por especialidad y modalidad?
10. ¿Cuál es el costo por atención y cómo varía entre grupos comparables?
11. ¿Existen bloques horarios o días de la semana con rendimiento sistemáticamente distinto?
12. Si se redistribuyeran las horas hacia los bloques de mayor demanda, ¿cuánta capacidad adicional se obtendría sin aumentar el gasto?

### 6.3 Variabilidad entre profesionales comparables

13. ¿Cuál es la dispersión de pacientes por hora dentro de cada grupo comparable? ¿Es una distribución continua o hay grupos separados?
14. ¿Qué parte de esa dispersión se explica por complejidad clínica, modalidad, turno o características del paciente, y qué parte queda sin explicar?
15. ¿Los profesionales en los extremos son estables en el tiempo o rotan?
16. ¿Existe correlación entre duración de la consulta y algún indicador de calidad disponible? Menos tiempo no es mejor desempeño.

### 6.4 Comportamiento en el tiempo

17. ¿Hay tendencias sostenidas de aumento o caída del rendimiento individual?
18. ¿Los cambios coinciden con hechos conocidos: cambio de sistema, de agenda, de contrato, licencias, estacionalidad?
19. ¿Hay estacionalidad institucional que deba descontarse antes de interpretar cualquier variación individual?
20. ¿El gasto por hora médica evoluciona en línea con la producción?

### 6.5 Integridad del registro clínico

21. ¿Qué proporción de las atenciones tiene registro clínico asociado?
22. ¿Cuánto tiempo transcurre entre la atención y la creación del registro? ¿La distribución sugiere registro en el momento o en bloque?
23. ¿Hay atenciones con duración físicamente improbable? ¿Refleja la atención real o la forma de registrar?
24. ¿Hay atenciones fuera del horario contratado? ¿Corresponden a extensión de jornada, urgencias o desfase horario del sistema?
25. ¿Hay atenciones solapadas en el tiempo para un mismo profesional? ¿Es atención simultánea real, registro por lotes o error?

### 6.6 Relaciones y trazabilidad

26. ¿Cómo se distribuyen los pacientes entre profesionales? ¿Hay carteras muy concentradas?
27. ¿Hay pacientes atendidos por varios profesionales en el mismo período? ¿Corresponde a un modelo de atención compartida documentado?
28. ¿Existen registros del mismo paciente atendido por dos profesionales en el mismo instante? Eso es físicamente incompatible y siempre indica un problema, aunque no necesariamente de conducta.
29. ¿Hay pacientes con frecuencia de visitas fuera de lo esperable para su condición?

### 6.7 El dato como hallazgo

30. ¿Qué campos tienen vacíos sistemáticos y en qué sistemas?
31. ¿Los identificadores de profesional son consistentes entre RR. HH., agenda, ficha y remuneraciones?
32. ¿Existe un maestro único de profesionales, o cada sistema tiene el suyo?
33. ¿Qué preguntas de este documento no se pueden responder con la data actual, y qué habría que capturar para responderlas?

---

## 7. Indicadores de referencia

Definiciones ya trabajadas. Úsalas como lentes de análisis, no como semáforos.

### 7.1 Horas y dinero

| Indicador | Fórmula | Lectura |
|---|---|---|
| Horas con actividad | Bloques de 30 minutos dentro de la ventana pagada con al menos una atención | Actividad demostrable con el dato disponible |
| Horas sin actividad | Horas pagadas menos horas con actividad | No equivale a horas no trabajadas: puede haber actividad no asistencial legítima |
| Utilización | Horas con actividad sobre horas pagadas | Referencia observada habitual: 85 a 95 % |
| Horas pagadas sobre contratadas | Cociente entre ambas | Mayor que 1 indica pago por sobre el contrato |
| Costo por atención | Monto pagado dividido por atenciones | La métrica más comparable entre pares |

### 7.2 Producción

| Indicador | Fórmula |
|---|---|
| Pacientes por hora | Atenciones dividido por horas pagadas |
| Rendimiento relativo | Pacientes por hora dividido por el estándar del grupo |
| Tasa de inasistencia | Ausentes sobre agendados |
| Duración media | Promedio de término menos inicio |
| Concentración en el turno | Fracción de atenciones que cabe en la mitad más cargada del turno |

### 7.3 Comparación y cambio

| Indicador | Definición | Por qué así |
|---|---|---|
| Desviación robusta | Mediana y desviación absoluta mediana, no promedio y desviación estándar | Las distribuciones de productividad clínica son sesgadas; un solo caso extremo distorsiona el promedio |
| Percentil dentro del grupo | Posición relativa entre pares comparables | Más interpretable que un valor absoluto |
| Cambio contra sí mismo | Media móvil exponencial contra la mediana de las primeras ocho semanas | Cada profesional es su propio control |
| Detección de cambio sostenido | Suma acumulada de desviaciones (CUSUM) | Distingue una caída sostenida de la variación semanal normal |

**Regla metodológica:** cualquier comparación debe hacerse entre profesionales clínicamente equivalentes. Comparar oncología con medicina general no informa nada. Si un grupo comparable tiene menos de cinco profesionales, la comparación no es estadísticamente honesta y debe ampliarse el grupo o declararse la limitación.

---

## 8. Patrones a buscar

Trabajados como reglas en la fase anterior, aquí se plantean como preguntas con sus explicaciones alternativas. **La explicación legítima debe descartarse antes de considerar cualquier otra.**

| Patrón | Explicaciones legítimas a descartar primero |
|---|---|
| Horas pagadas sin actividad registrada | Comités, docencia, gestión, investigación, bloqueos de agenda autorizados |
| Rendimiento muy bajo respecto del grupo | Complejidad de casos, demanda insuficiente, agenda mal diseñada, inasistencia |
| Atenciones fuera del horario contratado | Horas extraordinarias aprobadas, urgencias, desfase horario entre sistemas |
| Atenciones solapadas | Registro en bloque al final de la jornada, atención con equipo, error de sistema |
| Atención sin sesión activa en el sistema | Sesión abierta en otro equipo, registro delegado a personal administrativo, falla del log |
| Paciente repetido el mismo día | Control más procedimiento, reingreso, atención en dos servicios |
| Horas pagadas sobre las contratadas | Anexo de contrato no cargado, extensión formalizada, turno de reemplazo |
| Pagos duplicados | Reproceso de nómina con reverso no registrado |
| Bloques pagados sin pacientes | Capacitación, licencia parcial, caída del sistema, agenda no abierta |
| Actividad concentrada en parte del turno | Diseño de agenda, patrón real de llegada de pacientes |
| Consultas de duración improbable | Definición del momento de cierre en el sistema, no de la atención real |
| Atenciones sin registro clínico | Registro en sistema paralelo no integrado |
| Registro clínico creado días después | Regularización tras caída del sistema, práctica habitual del servicio |
| Mismo paciente con dos profesionales a la misma hora | Interconsulta simultánea documentada, error de identificación de paciente |

Los dos últimos merecen atención especial: si el registro retrospectivo es práctica generalizada del servicio, entonces no es un hallazgo individual sino un problema de proceso, y así debe reportarse.

---

## 9. Productos esperados

### 9.1 Informe de análisis

1. Resumen ejecutivo con los hallazgos principales y su magnitud en horas y pesos.
2. Caracterización de la data: cobertura, calidad, limitaciones.
3. Hallazgos por dimensión: conciliación, eficiencia, variabilidad, temporalidad, registro, relaciones.
4. Para cada hallazgo: qué se observó, con qué evidencia, qué lo explicaría, qué falta para confirmarlo.
5. Propuestas de mejora priorizadas por impacto y viabilidad.
6. Preguntas que la data actual no permite responder, con lo que habría que capturar.

### 9.2 One page ejecutivo

Los tres a cinco hallazgos de mayor impacto, su magnitud, y la decisión que se solicita.

### 9.3 Presentación

Narrativa para comité: qué se analizó, qué se encontró, qué se propone, qué se decide.

**Todos los hallazgos deben venir cuantificados.** "Hay horas sin actividad" no es un hallazgo. "El 23 % de las horas pagadas en telemedicina no tiene actividad registrada, equivalente a 340 horas y 11 millones de pesos en el semestre, concentrado en dos servicios" sí lo es.

---

## 10. Instrucciones de trabajo para el Proyecto

Estas líneas están redactadas para usarse como instrucciones personalizadas del Proyecto.

> Actúas como analista de datos en salud con criterio clínico y de gestión. El objetivo es analizar datos de pago médico por hora para encontrar ineficiencias, incongruencias, errores y oportunidades de mejora.
>
> Reglas de trabajo:
>
> 1. **Cuantifica siempre.** Todo hallazgo lleva magnitud en horas, pesos, porcentaje y número de casos. Sin cifra no es hallazgo.
> 2. **Explica antes de señalar.** Para cada patrón, enumera primero las explicaciones legítimas y di qué evidencia permitiría descartarlas.
> 3. **Distingue el dato del hecho.** Un registro anómalo puede reflejar un problema de registro y no del hecho registrado. Declara siempre cuál de los dos estás observando.
> 4. **Compara solo lo comparable.** Nunca compares entre especialidades o modalidades distintas. Si el grupo tiene menos de cinco profesionales, dilo y no concluyas.
> 5. **Usa estadística robusta.** Mediana y desviación absoluta mediana, no promedio y desviación estándar.
> 6. **El sujeto es el proceso.** No clasifiques profesionales. Si un hallazgo concentra en pocas personas, descríbelo como concentración y deriva a revisión humana, sin calificarlo.
> 7. **Declara los límites.** Si la data no permite responder, dilo explícitamente en vez de aproximar.
> 8. **Trazabilidad.** Registra qué datos usaste, qué supuestos hiciste, qué transformaciones aplicaste y qué quedó fuera.
> 9. **Nivel de autonomía 2.** Prepara el análisis completo y espera aprobación antes de generar el producto final.
> 10. **Lenguaje.** El sistema analiza integridad y eficiencia de pagos. No uses "fraude" ni "sospechoso". El análisis identifica diferencias que requieren explicación.

---

## 11. Gobernanza

| Principio | Implicancia práctica |
|---|---|
| Denominación | "Análisis de integridad y eficiencia en pagos médicos". Nunca "modelo de fraude" |
| Sujeto | El proceso y el dato, no la persona |
| Confirmación | Ningún hallazgo se traduce en acción sin revisión humana y descargos del profesional |
| Confidencialidad | Los datos no salen del perímetro institucional |
| Minimización | Para el análisis basta el identificador de paciente seudonimizado; no se requiere identidad |
| Trazabilidad | Cada corrida deja constancia de datos, supuestos y parámetros |
| Comunicación | Los hallazgos de proceso se comunican como mejora, no como control |

Sobre el último punto: la forma en que se comunique este trabajo determinará si los equipos clínicos colaboran o se cierran. Un hallazgo sobre registro retrospectivo puede presentarse como incumplimiento o como una oportunidad de mejorar la herramienta de registro. La segunda forma consigue el cambio; la primera consigue resistencia.

---

## 12. Qué no hacer en esta fase

- No construir código de producción ni modelos entrenados.
- No calcular puntajes por profesional.
- No presentar correlaciones como causas.
- No interpretar patrones temporales sin antes verificar cómo se registran los tiempos.
- No comparar entre grupos clínicamente distintos.
- No concluir sobre grupos pequeños.
- No usar datos reales en servicios en la nube de terceros.

---

## Anexo A · Qué ya está construido

Existe una implementación funcional, disponible si esta fase concluye que vale la pena automatizar. No se usa ahora, pero su diseño respalda las definiciones de este documento.

| Componente | Qué hace |
|---|---|
| Ingesta | Lee CSV, Excel, JSON, Parquet y ZIP; detecta separador y codificación; traduce nombres de columna en español; interpreta fechas y montos en formato local |
| Calidad de datos | Verifica integridad referencial, claves duplicadas, fechas ilegibles y cobertura entre fuentes |
| Variables derivadas | Cerca de treinta indicadores por médico y día, y por médico y mes |
| Conciliación | Cruza contrato, pago y actividad, y cuantifica las diferencias en pesos |
| Reglas | Trece patrones con umbral explícito y evidencia asociada |
| Comparación con pares | Desviación robusta y percentiles dentro de grupos equivalentes |
| Anomalías | Isolation Forest y Local Outlier Factor sobre desviaciones intra-grupo |
| Cambio temporal | Media móvil exponencial y CUSUM contra el histórico propio |
| Grafo | Relaciones médico-paciente: carteras compartidas, concentración, coincidencias temporales |
| Reportería | Informes en HTML, Markdown, Excel y CSV |
| Tablero | Interfaz de carga, exploración y gestión de casos |

Repositorio: `drintiparedes-svg/segundo-cerebro`, rama `claude/medical-payment-fraud-model-ah4t2z`.
Documentación técnica completa: `docs/MANUAL_DE_USO.md`.

Validación disponible: sobre datos sintéticos con escenarios conocidos, el modelo ubicó correctamente los nueve casos inyectados en las primeras nueve posiciones, sin falsos positivos en niveles de acción. Esa validación demuestra separación en datos simulados, no desempeño en producción.

## Anexo B · Aprendizajes técnicos aplicables al análisis

1. **El punto y la coma.** En formato local `$187.800` son ciento ochenta y siete mil ochocientos pesos, pero `8.000` horas son ocho. Interpretar el separador según la naturaleza de la variable, no de forma uniforme.
2. **Nombres ambiguos.** "Hora inicio" significa inicio de turno en contratos, comienzo de la atención en la ficha clínica e ingreso al sistema en los logs. Verificar el significado en cada fuente antes de cruzar.
3. **Identificadores.** El mismo profesional puede tener claves distintas en cada sistema. Construir la equivalencia antes de cualquier cruce, y tratar los identificadores como texto para evitar pérdidas de ceros a la izquierda.
4. **Bajo rendimiento aislado.** Por sí solo casi nunca es concluyente. Adquiere sentido cuando coincide con horas sin actividad, desviación frente a pares y cambio respecto del histórico propio.
5. **Grupos pequeños.** Bajo cinco profesionales por grupo, la comparación entre pares deja de ser informativa.
6. **Registro por lotes.** Si las fichas se cierran al final de la jornada, las mediciones de duración y simultaneidad describen la práctica de registro, no la atención.
