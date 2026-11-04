// Builds dist/: index.html + app.js + app.css + data/. Run after `next build` in apps/web (its CSS is reused,
// so the demo looks exactly like the app) and after the engine has written apps/web/data.
import { build } from "esbuild";
import { cpSync, mkdirSync, readFileSync, readdirSync, rmSync, writeFileSync, existsSync } from "node:fs";
import { dirname, join, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const web = resolve(here, "../apps/web");
const dist = join(here, "dist");
rmSync(dist, { recursive: true, force: true });
mkdirSync(join(dist, "data/research"), { recursive: true });

await build({
  entryPoints: [join(here, "src/main.tsx")],
  bundle: true, minify: true, format: "iife", target: "es2020", outfile: join(dist, "app.js"), jsx: "automatic",
  alias: { "next/link": join(here, "src/shims/link.tsx"), "next/navigation": join(here, "src/shims/navigation.ts"), "@": web },
  nodePaths: [join(web, "node_modules")],
  define: { "process.env.NODE_ENV": '"production"' },
  loader: { ".css": "empty" }, // CSS comes from the Next build below
  logLevel: "warning",
});

// CSS from the Next build, with the font files inlined (the hosted page loads nothing from elsewhere).
const cssDir = join(web, ".next/static/css");
if (!existsSync(cssDir)) throw new Error("run `npx next build` in apps/web first");
let css = readdirSync(cssDir).filter((f) => f.endsWith(".css")).map((f) => readFileSync(join(cssDir, f), "utf8")).join("\n");
// Keep only the Latin subsets of the fonts (rupee sign and Indian names are in latin / latin-ext).
css = css.replace(/@font-face\{[^}]*\}/g, (rule) => {
  const ur = rule.match(/unicode-range:([^;}]*)/);
  if (ur && !/U\+0000-00FF|U\+0100-02BA|U\+20B9|U\+0100-024F/i.test(ur[1])) return "";
  return rule.replace(/url\((\/_next\/static\/media\/[^)]+)\)/g, (_, p) => {
    const f = join(web, ".next", p.replace("/_next/", ""));
    return `url(data:font/woff2;base64,${readFileSync(f).toString("base64")})`;
  });
});
writeFileSync(join(dist, "app.css"), css);

// Data: exactly what the engine wrote for the web app.
cpSync(join(web, "data/feed.json"), join(dist, "data/feed.json"));
for (const f of readdirSync(join(web, "data/research"))) if (f.endsWith(".json") && f !== "securities.json") cpSync(join(web, "data/research", f), join(dist, "data/research", f));
// Search list: symbol and name only, EQ series plus the demo companies (the full list with ISINs stays in the app).
const sec = JSON.parse(readFileSync(join(web, "data/research/securities.json"), "utf8")).rows.filter((r) => r.series === "EQ" || r.fixture);
writeFileSync(join(dist, "data/research/securities.csv"), "symbol,name,fixture\n" + sec.map((r) => `${r.symbol},${r.name.replaceAll(",", " ")},${r.fixture ? 1 : 0}`).join("\n") + "\n");

writeFileSync(join(dist, "index.html"), `<!DOCTYPE html>
<html lang="en-IN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="theme-color" content="#0d1218">
<title>FINN: static demo</title>
<link rel="stylesheet" href="app.css">
</head>
<body>
<div id="root"></div>
<noscript>FINN needs JavaScript.</noscript>
<script src="app.js"></script>
</body>
</html>
`);
const size = (p) => (readFileSync(p).length / 1024).toFixed(0) + " KB";
console.log("dist/app.js", size(join(dist, "app.js")), "| app.css", size(join(dist, "app.css")), "| files", readdirSync(join(dist, "data/research")).length + 1, "data files");
