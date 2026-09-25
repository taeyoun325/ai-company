// 화면 시험용 서버 (DAY 26) — 백엔드와 프론트를 **격리된 곳에** 띄운다.
//
//   node e2e/serve.mjs backend     → http://127.0.0.1:8765  (Mock · 임시 데이터 폴더)
//   node e2e/serve.mjs frontend    → http://127.0.0.1:3765  (next dev · .next-e2e)
//
// ## 왜 따로 띄우나
//
// 개발 중인 서버(3000 · 8000)를 그대로 쓰면 시험이 **내 프로젝트 목록과 지갑**
// 위에서 돈다. 시험이 만든 프로젝트가 목록에 쌓이고(DAY 22 에 색인에 456행이
// 쌓였던 것과 같은 사고), 거꾸로 내가 만든 프로젝트 때문에 시험이 흔들린다.
// 포트·데이터 폴더·Next 빌드 폴더를 전부 따로 쓴다 — 켜둔 개발 서버를 건드리지
// 않는다(같은 `.next` 를 두 dev 서버가 쓰면 서로의 캐시를 깬다).
//
// 데이터 폴더는 `E2E_DATA_DIR` 이 있으면 거기, 없으면 임시 폴더를 새로 만든다.
import { spawn } from "node:child_process";
import { existsSync, mkdtempSync } from "node:fs";
import { tmpdir } from "node:os";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const frontend = path.resolve(here, "..");
const root = path.resolve(frontend, "..");

export const BACKEND_PORT = Number(process.env.E2E_BACKEND_PORT ?? 8765);
export const FRONTEND_PORT = Number(process.env.E2E_FRONTEND_PORT ?? 3765);

function python() {
  const candidates = [
    path.join(root, ".venv", "Scripts", "python.exe"),
    path.join(root, ".venv", "bin", "python"),
  ];
  return candidates.find((p) => existsSync(p)) ?? "python";
}

function run(cmd, args, opts) {
  const child = spawn(cmd, args, { stdio: "inherit", ...opts });
  const stop = () => child.kill();
  process.on("SIGINT", stop);
  process.on("SIGTERM", stop);
  child.on("exit", (code) => process.exit(code ?? 0));
}

const which = process.argv[2];
if (which === "backend") {
  const data = process.env.E2E_DATA_DIR
    ?? mkdtempSync(path.join(tmpdir(), "ai-company-e2e-"));
  console.log(`[e2e] backend data → ${data}`);
  run(python(), [path.join(root, "backend", "run.py"), "--port", String(BACKEND_PORT)], {
    cwd: root,
    env: {
      ...process.env,
      DATA_DIR: data,
      PROJECTS_DIR: path.join(data, "projects"),
      LOGS_DIR: path.join(data, "logs"),
      PROVIDER_MODE: "mock",
      DEPLOY_MODE: "local",
      PYTHONIOENCODING: "utf-8",
      // 실제 키가 환경에 있어도 시험은 Mock 으로만 돈다 — 돈이 나가면 안 된다.
      ANTHROPIC_API_KEY: "",
      OPENAI_API_KEY: "",
      GEMINI_API_KEY: "",
      GOOGLE_API_KEY: "",
    },
  });
} else if (which === "frontend") {
  const next = path.join(frontend, "node_modules", "next", "dist", "bin", "next");
  run(process.execPath, [next, "dev", "-p", String(FRONTEND_PORT), "-H", "127.0.0.1"], {
    cwd: frontend,
    env: {
      ...process.env,
      BACKEND_ORIGIN: `http://127.0.0.1:${BACKEND_PORT}`,
      NEXT_DIST_DIR: ".next-e2e",
      NEXT_TELEMETRY_DISABLED: "1",
    },
  });
} else {
  console.error("usage: node e2e/serve.mjs backend|frontend");
  process.exit(2);
}
