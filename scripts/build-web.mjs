// Genera el sitio estático que se publica en Vercel.
//
// IMPORTANTE: el sitio publicado es SOLO la vitrina en modo demo. No
// incluye la memoria personal: esa vive únicamente en la máquina del
// usuario (.brain/) y se consulta con `sb serve` en local.

import { mkdir, readFile, writeFile } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const root = join(dirname(fileURLToPath(import.meta.url)), "..");
const source = join(root, "src", "segundo_cerebro", "ui", "index.html");
const outDir = join(root, "web");

const body = await readFile(source, "utf8");
const page = `<!doctype html>\n<html lang="es">\n${body}\n</html>\n`;

await mkdir(outDir, { recursive: true });
await writeFile(join(outDir, "index.html"), page, "utf8");
await writeFile(
  join(outDir, "robots.txt"),
  "User-agent: *\nDisallow:\n",
  "utf8",
);

console.log("web/index.html generado (modo demo, sin memoria personal)");
