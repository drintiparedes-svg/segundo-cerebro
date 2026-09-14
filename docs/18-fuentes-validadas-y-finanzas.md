# 18 · Fuentes validadas y lente financiera

## Fuentes técnicas validadas

Cuatro conectores nuevos, todos de solo lectura y con **procedencia** en
cada documento (`validated: true`, identificador oficial, `retrieved_at`).
Solo viajan los términos de búsqueda que tú eliges.

| Conector | Fuente oficial | Qué entra | Id |
|---|---|---|---|
| `pubmed` | NCBI E-utilities | papers | PMID, DOI |
| `europepmc` | Europe PMC REST | papers open access | DOI, PMID |
| `clinicaltrials` | ClinicalTrials.gov API v2 | ensayos con estado y fase | NCT |
| `guidelines` | RSS/Atom (WHO, MINSAL, sociedades) | guías y alertas | URL |

```bash
sb literature watch "HPV self-sampling packaging" --source pubmed
sb literature watch "cervical cancer screening self-collection" --source clinicaltrials
sb connect add guidelines --config url=https://www.who.int/rss-feeds/news-english.xml --config name=WHO
sb connect                      # las búsquedas guardadas son instancias; sb refresh las sincroniza
```

En la vista de un documento, chip **✔ fuente validada** con su PMID/DOI/NCT
y la fecha de consulta. `sb literature verify` sigue validando las citas de
tus manuscritos contra Crossref.

## Radar de financiamiento

Dos entradas y una regla. Entradas: `brain/self/funding.md` (convocatorias
que sigues a mano: nombre, **URL oficial**, cierre, monto, palabras clave,
proyecto) y páginas oficiales conectadas (`sb connect add funding --config
url=… --config name=ANID`) con barrido heurístico de títulos con fecha.

**Regla:** solo entra a la memoria lo verificable como **abierta** — URL
alcanzable y cierre futuro. Sin fecha confirmada → «sin verificar»; nunca
se asume. Cada abierta es un knowledge object `opportunity` con `valid_to`
= cierre, ligado al proyecto que calce por palabras clave.

```bash
sb funding                 # verifica en la fuente y actualiza la memoria
sb funding --offline       # sin red: solo por fecha
```

Aparecen en `sb today` («Financiamiento: cierra en 30 días»), en la lente
financiera del proyecto y como alerta cuando cierran en ≤ 14 días. El
informe queda en `.brain/reports/radar-financiamiento-*.md`.

## Indicadores económicos

`sb indicators` trae UF, dólar, euro, IPC, UTM y TPM desde mindicador.cl
(republica al Banco Central) con caché de 24 h en
`.brain/state/indicators.json`; la lente financiera convierte presupuestos
a USD y UF con ese caché (nunca llama en caliente desde la UI).

## Lente financiera por proyecto

```bash
sb project finance tesis --budget PlanTrabajo_VPH_3meses.xlsx   # importa la hoja «Presupuesto»
sb project finance tesis --actuals gasto.csv                    # ejecución real (fecha, ítem, fase, monto)
sb project finance tesis --save                                 # informe en .brain/reports/
```

El importador entiende `Fase · Ítem · Detalle · Costo unit. · Cantidad ·
Total` y las filas de subtotal / contingencia / total. Lo demás sale de
`brain/self/projects.md`:

```yaml
currency: CLP
units:
  - { name: "kit de autotoma entregado", volume: 500 }
  - { name: "mujer tamizada", volume: 400, price: 15000, fixed_cost: 300000, variable_cost: 9000 }
benefits:
  - { name: "Tamizajes ganados", value_clp: 4800000, per: year, basis: "400 × $12.000 evitados" }
```

Qué calcula:
- **Ejecución**: total, por fase, % ejecutado, restante; en USD y UF.
- **Unidades económicas**: costo por unidad (plan y real), desvío, punto
  de equilibrio y margen si hay precio.
- **Impacto**: beneficio − costo, ROI, payback y sensibilidad ±20 % en
  volumen y costo.
- **Alertas L1** (solo sugieren): fase ≥ 90 % ejecutada, desvío unitario
  ≥ 15 %, convocatoria que cierra en ≤ 14 días.

En la UI: pestaña **Hoy → Finanzas** (tarjeta por proyecto). Plantilla
nueva para `sb draft caso-financiero --topic "…"`.

Todo es cálculo local sobre tus planillas; los supuestos son tuyos y
quedan escritos en `basis`.
