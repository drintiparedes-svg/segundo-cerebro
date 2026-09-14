# 19 · App de escritorio

El mismo sistema, abierto con un clic y sin terminal. Todo sigue en tu
equipo: la app es una ventana nativa sobre el servidor local.

## Cómo funciona

```bash
pip install -e ".[app]"      # pywebview
sb app                       # o: python -m segundo_cerebro.app
sb app --browser             # sin ventana nativa: abre tu navegador
```

- Elige un **puerto libre** y genera un **token de sesión**: solo esa
  ventana puede hablar con la API (`X-SB-Token`); otra pestaña o proceso
  recibe `401`. `sb serve` (sin token) se mantiene para uso local clásico.
- Lanza `sb refresh` en segundo plano al abrir, salvo en modo manual
  supervisado (`refresh.auto = false`, p. ej. tras `sb ai off`).
- La memoria vive en `~/SegundoCerebro/.brain` cuando corres el
  ejecutable; con el repo clonado, en `./.brain` como siempre.

## Primeros pasos y doctor

Al abrir, la pestaña **Hoy** muestra la lista **Primeros pasos** hasta que
esté completa: conectar carpetas, primera sincronización, cuentas Google,
personas clave, política de Claude y tarea programada (con botón
**Programar** → `POST /api/schedule/install`).

```bash
sb doctor          # dependencias, cerebro, conectores, Google, tarea, IA, última sync
sb doctor --json   # para automatizar (exit 1 si hay fallas)
sb update-check    # consulta GitHub Releases solo cuando tú lo pides; sin telemetría
sb --version
```

## Empaquetar

```bash
pip install -e ".[app,files,google,build]"
python packaging/build_app.py --dry-run   # muestra el comando de PyInstaller
python packaging/build_app.py             # dist/Segundo Cerebro/ (.exe) o .app
```

`.github/workflows/release.yml` construye Windows (`.zip`) y macOS (`.dmg`)
al etiquetar `vX.Y.Z` y publica la release. Los binarios **no están
firmados** todavía: en Windows, SmartScreen → «Más información → Ejecutar
de todas formas»; en macOS, clic derecho → Abrir la primera vez (o
`xattr -d com.apple.quarantine "Segundo Cerebro.app"`). La firma
(certificado / notarización) queda para cuando el producto salga de uso
personal.

## Qué NO se empaqueta

Tu memoria (`.brain/`), tus tokens de Google y tus claves nunca van dentro
del instalador: se crean en tu equipo la primera vez que abres la app.
