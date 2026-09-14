# 16 · Conectores: fuentes que se conectan y desconectan sin tocar código

Toda fuente de información es una **instancia** de un tipo de conector,
registrada en `.brain/connectors.json` con su configuración, su estado de
sincronización y su último resultado. El contrato es el mismo para todas:

| Método | Qué hace |
|---|---|
| `test()` | ¿llego a la fuente? (carpeta existe, cuenta responde, archivo está) |
| `sync(store)` | trae lo nuevo, idempotente; devuelve los documentos añadidos |
| `disconnect(store, purge)` | quita la instancia; con `purge`, borra de la memoria lo que aportó |

Cada documento guarda `connector_id` (la instancia que lo trajo), así
desconectar puede borrar **exactamente lo suyo**: sus documentos, los
knowledge objects y relaciones derivados. Las entidades del grafo se
conservan (pueden venir de otros documentos) y lo capturado a mano
(`sb add`, captura de correo) nunca pertenece a un conector.

## Tipos incorporados

| Tipo | Privacidad | Cómo se conecta |
|---|---|---|
| `localfs` Carpeta local | local | `sb connect add localfs --path <carpeta>` o el asesor (`sb sources suggest`) |
| `gdrive` Google Drive | read-cloud | `sb google connect <alias>` → aparece sola |
| `gcalendar` Google Calendar | read-cloud | ídem |
| `gmail` Gmail (triaje) | read-cloud | ídem; nunca persiste correos |
| `zotero` Zotero / BibTeX | local | `sb connect add zotero --path biblioteca.bib` |
| `chats` WhatsApp / Slack | local | `sb connect add chats --path export.txt --alias "Equipo"` |

`privacy` dice qué sale del equipo: **local** nada; **read-cloud** consultas
de solo lectura a tu cuenta; **write-cloud** (reservado para la fase de
autonomía) escritura reversible en tus propias cuentas.

## Uso

```bash
sb connect types                       # tipos disponibles
sb connect                             # instancias, estado, docs aportados
sb connect add localfs --path ~/Documentos/Proyectos
sb connect test localfs:Proyectos
sb connect sync                        # todas (o: sb connect sync <id>)
sb connect remove localfs:Proyectos            # desconecta; los datos quedan
sb connect remove localfs:Proyectos --purge    # …y borra lo que aportó
sb connect remove gdrive:falp --purge --forget # Google: además olvida la autorización
```

`sb refresh` sincroniza todas las instancias habilitadas en su paso
`connectors` (reemplaza los antiguos pasos `sources` y `google`); el triaje
de correo sigue en el paso `mail`, solo para las cuentas Gmail habilitadas.

En la UI, pestaña **Conectores**: tarjeta por instancia (privacidad,
documentos aportados, última sincronización, error si lo hubo) con
**Probar / Sync / ✕ Desconectar** (pregunta si borrar también sus datos) y un
formulario para conectar carpetas, bibliotecas Zotero o exports de chat.
Las cuentas Google desconectadas quedan deshabilitadas con **↺** para
reconectar sin volver a autorizar.

## Compatibilidad

- `sb sources …` y `sb desktop` siguen funcionando: son una vista sobre las
  instancias `localfs`. El antiguo `sources.json` se migra solo la primera
  vez (queda `sources.json.migrated`).
- Bases anteriores al SDK: al abrirlas, `connector_id` se rellena desde los
  metadatos de cada documento.

## Extender con un plugin

```python
from segundo_cerebro.connectors.base import Connector, ConnectorSpec, SyncResult

class NotionConnector(Connector):
    spec = ConnectorSpec(id="notion", name="Notion", kind="api", privacy="read-cloud",
                         config_schema={"token": {"required": True, "help": "integration token"}})
    def test(self): ...
    def sync(self, store): ...; return SyncResult(added=docs)
```

Publícalo con el entry point `segundo_cerebro.connectors = notion = mi_paquete:NotionConnector`
y aparecerá en `sb connect types`. Las reglas no cambian: solo lectura por
defecto, todo en `.brain/`, y el botón de emergencia (`sb ai off`) manda.
