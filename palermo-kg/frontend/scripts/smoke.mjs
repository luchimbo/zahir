import { spawn } from "node:child_process";

const rootDir = new URL("../../", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");
const frontendDir = new URL("../", import.meta.url).pathname.replace(/^\/([A-Z]:)/, "$1");
const pythonExe = `${rootDir}.venv/Scripts/python.exe`;
const nextBin = `${frontendDir}node_modules/next/dist/bin/next`;
const apiPort = process.env.API_PORT ?? "8017";
const frontendPort = process.env.FRONTEND_PORT ?? "3017";

function run(command, args, cwd, env = {}) {
  const child = spawn(command, args, {
    cwd,
    env: { ...process.env, ...env },
    stdio: ["ignore", "pipe", "pipe"],
    windowsHide: true
  });

  child.stdout.on("data", (chunk) => process.stdout.write(chunk));
  child.stderr.on("data", (chunk) => process.stderr.write(chunk));
  return child;
}

async function waitFor(url, timeoutMs = 45000) {
  const started = Date.now();
  let lastError = "";

  while (Date.now() - started < timeoutMs) {
    try {
      const response = await fetch(url);
      if (response.ok) return response;
      lastError = `${response.status} ${response.statusText}`;
    } catch (error) {
      lastError = error instanceof Error ? error.message : "unknown error";
    }
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }

  throw new Error(`Timeout esperando ${url}: ${lastError}`);
}

const api = run(
  pythonExe,
  ["-m", "uvicorn", "api.main:app", "--host", "127.0.0.1", "--port", apiPort],
  rootDir
);
const next = run(
  process.execPath,
  [nextBin, "dev", "--hostname", "127.0.0.1", "--port", frontendPort],
  frontendDir,
  { KG_API_BASE: `http://127.0.0.1:${apiPort}` }
);

try {
  const health = await waitFor(`http://127.0.0.1:${apiPort}/health`);
  const home = await waitFor(`http://127.0.0.1:${frontendPort}`);
  const search = await waitFor(`http://127.0.0.1:${frontendPort}/api/kg/search?q=Don%20Julio`);
  const natural = await waitFor(`http://127.0.0.1:${frontendPort}/api/kg/search/natural?q=decks%20gastronomicos%20palermo`);

  const healthJson = await health.json();
  const homeHtml = await home.text();
  const searchJson = await search.json();
  const naturalJson = await natural.json();
  const firstEntityId = searchJson.results?.[0]?.id;
  let entityHtml = "";
  if (firstEntityId) {
    const entity = await waitFor(`http://127.0.0.1:${frontendPort}/entity/${firstEntityId}`);
    entityHtml = await entity.text();
  }

  console.log("\nSmoke OK");
  console.log(`api=${healthJson.status}`);
  console.log(`home_has_title=${homeHtml.includes("Palermo Knowledge Search")}`);
  console.log(`search_results=${searchJson.results?.length ?? 0}`);
  console.log(`entity_page=${Boolean(firstEntityId && entityHtml.includes("Cargando entidad"))}`);
  console.log(`natural_has_answer=${Boolean(naturalJson.answer)}`);
  console.log(`natural_citations=${naturalJson.citations?.length ?? 0}`);
  console.log(`natural_mentions=${naturalJson.mentioned_entities?.length ?? 0}`);
  console.log(`natural_explainability=${naturalJson.explainability?.length ?? 0}`);
  console.log(`natural_has_coordinates=${Boolean(naturalJson.mentioned_entities?.some((entity) => typeof entity.lat === "number" && typeof entity.lng === "number"))}`);
} finally {
  api.kill();
  next.kill();
}
