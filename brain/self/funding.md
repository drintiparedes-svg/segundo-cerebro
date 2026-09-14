---
# Convocatorias que sigues a mano. EDÍTALO: nombre, URL OFICIAL, cierre,
# monto, palabras clave y (opcional) proyecto. `sb funding` verifica que
# la URL responda y que el cierre sea futuro; solo entonces cuenta como
# ABIERTA y entra a tu memoria como oportunidad (con vencimiento).
#
#   sb funding            # radar: manual + páginas oficiales conectadas
#   sb funding --offline  # sin red: solo por fecha
calls:
  - name: "ANID · Fondecyt de Iniciación (referencia)"
    url: "https://anid.cl/concursos/"
    funder: ANID
    deadline: 2027-03-31
    amount: "hasta $30 MM/año"
    keywords: [investigación, salud, iniciación]
    project: tesis
---

# Radar de financiamiento

Fuentes oficiales para el barrido automático se agregan como conectores:

```bash
sb connect add funding --config url=https://anid.cl/concursos/ --config name=ANID
sb connect add funding --config url=https://www.corfo.cl/sites/cpp/convocatorias --config name=CORFO
```

Regla: lo que no se puede verificar en la fuente oficial (URL viva y cierre
futuro) se informa como «sin verificar», nunca como oportunidad.
