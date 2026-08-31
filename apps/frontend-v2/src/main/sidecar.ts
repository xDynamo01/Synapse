import { ChildProcess, spawn } from "node:child_process";
import fs from "node:fs/promises";
import http from "node:http";
import path from "node:path";

export interface BackendHandshake {
  schema_version: number;
  host: string;
  port: number;
  pid: number;
  token: string;
  started_at: string;
  version: string;
}

export interface SidecarSupervisorOptions {
  appUserDataPath: string;
  currentDir: string;
  isPackaged: boolean;
  resourcesPath: string;
  explicitBackendUrl?: string;
  explicitSidecarPath?: string;
  startupTimeoutMs?: number;
  diagnosticsPath?: string;
}

export interface SidecarRuntimeState {
  mode: "external" | "owned";
  baseUrl: string;
  pid: number | null;
  handshake: BackendHandshake | null;
  startup: BackendStartupReadiness | null;
}

export interface BackendStartupResource {
  resource: string;
  action: string;
  status: string;
  duration_ms: number;
  required?: boolean;
  error_type?: string | null;
  error?: string | null;
}

export interface BackendStartupReadiness {
  schema: "synapse-sidecar-startup-ready-v1";
  ready: boolean;
  startup_status: string;
  resources: BackendStartupResource[];
}

const handshakeRelativePath = path.join("runtime", "backend-handshake.json");

export class SidecarStartupError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "SidecarStartupError";
  }
}

export class BackendSidecarSupervisor {
  private readonly options: Required<Pick<SidecarSupervisorOptions, "startupTimeoutMs">> &
    Omit<SidecarSupervisorOptions, "startupTimeoutMs">;
  private process: ChildProcess | null = null;
  private runtimeState: SidecarRuntimeState | null = null;
  private startup: Promise<SidecarRuntimeState> | null = null;
  private stopping = false;

  constructor(options: SidecarSupervisorOptions) {
    this.options = {
      ...options,
      startupTimeoutMs: options.startupTimeoutMs ?? 60_000
    };
  }

  ensureStarted(): Promise<SidecarRuntimeState> {
    if (this.runtimeState) {
      return Promise.resolve(this.runtimeState);
    }
    if (this.startup) {
      return this.startup;
    }
    this.startup = this.start().catch((error: unknown) => {
      this.startup = null;
      throw error;
    });
    return this.startup;
  }

  async stop(): Promise<void> {
    this.stopping = true;
    const owned = this.process;
    this.process = null;
    this.runtimeState = null;
    this.startup = null;
    if (!owned || owned.killed || owned.exitCode !== null) {
      return;
    }
    owned.kill();
    await waitForExit(owned, 5_000);
    if (owned.exitCode === null && !owned.killed) {
      owned.kill("SIGKILL");
      await waitForExit(owned, 2_000);
    }
  }

  private async start(): Promise<SidecarRuntimeState> {
    const explicitBackendUrl = this.options.explicitBackendUrl?.trim();
    if (explicitBackendUrl) {
      this.runtimeState = {
        mode: "external",
        baseUrl: explicitBackendUrl.replace(/\/$/, ""),
        pid: null,
        handshake: null,
        startup: null
      };
      return this.runtimeState;
    }

    const sidecarPath = await resolveSidecarPath(this.options);
    const dataDir = this.options.appUserDataPath;
    const handshakePath = path.join(dataDir, handshakeRelativePath);
    await fs.rm(handshakePath, { force: true });

    const diagnosticsPath = this.options.diagnosticsPath ?? path.join(dataDir, "runtime", "sidecar-startup.log");
    await fs.mkdir(path.dirname(diagnosticsPath), { recursive: true });
    await appendDiagnostic(diagnosticsPath, `spawn path=${sidecarPath} cwd=${path.dirname(sidecarPath)} data_dir=${dataDir}`);
    const child = spawn(sidecarPath, ["--host", "127.0.0.1", "--port", "0"], {
      cwd: path.dirname(sidecarPath),
      env: {
        ...process.env,
        SYNAPSE_DATA_DIR: dataDir,
        SYNAPSE_HOST: "127.0.0.1",
        SYNAPSE_PORT: "0"
      },
      stdio: ["ignore", "pipe", "pipe"],
      windowsHide: true
    });
    this.process = child;
    child.stdout?.on("data", (chunk: Buffer) => void appendDiagnostic(diagnosticsPath, sanitizeDiagnostic(chunk.toString())));
    child.stderr?.on("data", (chunk: Buffer) => void appendDiagnostic(diagnosticsPath, sanitizeDiagnostic(chunk.toString())));
    child.once("exit", (code, signal) => {
      void appendDiagnostic(diagnosticsPath, `exit code=${code ?? "null"} signal=${signal ?? "none"}`);
      if (!this.stopping) {
        this.runtimeState = null;
        this.startup = null;
      }
    });

    await appendDiagnostic(diagnosticsPath, `waiting handshake path=${handshakePath} timeout_ms=${this.options.startupTimeoutMs}`);
    const handshake = await waitForHandshake(handshakePath, child, this.options.startupTimeoutMs, diagnosticsPath);
    const baseUrl = `http://${normalizeLoopbackHost(handshake.host)}:${handshake.port}`;
    await appendDiagnostic(diagnosticsPath, `handshake accepted pid=${handshake.pid} port=${handshake.port} base_url=${baseUrl}`);
    const startup = await waitForBackendReadiness(baseUrl, child, this.options.startupTimeoutMs, diagnosticsPath);
    await appendDiagnostic(diagnosticsPath, `post-startup readiness accepted status=${startup.startup_status}`);
    this.runtimeState = {
      mode: "owned",
      baseUrl,
      pid: child.pid ?? handshake.pid,
      handshake,
      startup
    };
    return this.runtimeState;
  }
}

export async function resolveSidecarPath(options: Pick<SidecarSupervisorOptions, "currentDir" | "explicitSidecarPath" | "isPackaged" | "resourcesPath">): Promise<string> {
  const candidates = [
    options.explicitSidecarPath,
    options.isPackaged
      ? path.join(options.resourcesPath, "synapse-backend", "synapse_backend.exe")
      : null,
    path.resolve(options.currentDir, "../../../../../backend/dist/synapse_backend/synapse_backend.exe")
  ].filter((candidate): candidate is string => Boolean(candidate));

  for (const candidate of candidates) {
    try {
      const stat = await fs.stat(candidate);
      if (stat.isFile()) {
        return candidate;
      }
    } catch {
      continue;
    }
  }
  throw new SidecarStartupError("Synapse backend sidecar executable was not found.");
}

export async function waitForHandshake(
  handshakePath: string,
  child: ChildProcess,
  timeoutMs: number,
  diagnosticsPath?: string
): Promise<BackendHandshake> {
  const deadline = Date.now() + timeoutMs;
  let lastParseError: unknown = null;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      const diagnostics = diagnosticsPath ? await readDiagnosticTail(diagnosticsPath) : "";
      throw new SidecarStartupError(`Synapse backend sidecar exited before readiness with code ${child.exitCode}.${diagnostics ? ` Diagnostics: ${diagnostics}` : ""}`);
    }
    try {
      const raw = await fs.readFile(handshakePath, "utf8");
      const handshake = JSON.parse(raw) as BackendHandshake;
      validateHandshake(handshake, child.pid ?? null);
      return handshake;
    } catch (error) {
      lastParseError = error;
      await delay(100);
    }
  }
  throw new SidecarStartupError(
    `Synapse backend sidecar did not become ready within ${timeoutMs}ms.${lastParseError instanceof Error ? ` Last handshake error: ${lastParseError.message}` : ""}`
  );
}

export async function waitForBackendReadiness(
  baseUrl: string,
  child: ChildProcess,
  timeoutMs: number,
  diagnosticsPath?: string
): Promise<BackendStartupReadiness> {
  const deadline = Date.now() + timeoutMs;
  let lastError: unknown = null;
  while (Date.now() < deadline) {
    if (child.exitCode !== null) {
      const diagnostics = diagnosticsPath ? await readDiagnosticTail(diagnosticsPath) : "";
      throw new SidecarStartupError(
        `Synapse backend sidecar exited before post-startup readiness with code ${child.exitCode}.${diagnostics ? ` Diagnostics: ${diagnostics}` : ""}`
      );
    }
    try {
      const response = await readBackendStartupReadiness(baseUrl);
      const payload = response.payload;
      if (
        response.statusCode >= 200 &&
        response.statusCode < 300 &&
        response.serviceHeader === "synapse-backend" &&
        payload.schema === "synapse-sidecar-startup-ready-v1" &&
        payload.ready === true &&
        (payload.startup_status === "ready" || payload.startup_status === "degraded")
      ) {
        return payload;
      }
      lastError = new SidecarStartupError(
        `Backend post-startup readiness probe returned ${response.statusCode} (${payload.startup_status ?? "unknown"}).`
      );
    } catch (error) {
      lastError = error;
    }
    await delay(100);
  }
  const diagnostics = diagnosticsPath ? await readDiagnosticTail(diagnosticsPath) : "";
  throw new SidecarStartupError(
    `Synapse backend sidecar did not pass post-startup readiness within ${timeoutMs}ms.${diagnostics ? ` Diagnostics: ${diagnostics}` : ""}${lastError instanceof Error ? ` Last error: ${lastError.message}` : ""}`
  );
}

function readBackendStartupReadiness(baseUrl: string): Promise<{
  statusCode: number;
  serviceHeader: string | undefined;
  payload: BackendStartupReadiness;
}> {
  return new Promise((resolve, reject) => {
    const probeUrl = new URL("/api/sidecar/startup-ready", baseUrl.replace(/\/$/, ""));
    const request = http.get(probeUrl, { timeout: 1_000 }, (response) => {
      let body = "";
      response.setEncoding("utf8");
      response.on("data", (chunk: string) => {
        body += chunk;
      });
      response.on("end", () => {
        try {
          const serviceHeader = response.headers["x-synapse-service"];
          resolve({
            statusCode: response.statusCode ?? 0,
            serviceHeader: Array.isArray(serviceHeader) ? serviceHeader[0] : serviceHeader,
            payload: JSON.parse(body) as BackendStartupReadiness
          });
        } catch (error) {
          reject(error);
        }
      });
    });
    request.on("timeout", () => {
      request.destroy(new SidecarStartupError("Backend post-startup readiness probe timed out."));
    });
    request.on("error", reject);
  });
}

async function appendDiagnostic(filePath: string, message: string): Promise<void> {
  try {
    await fs.appendFile(filePath, `${new Date().toISOString()} ${message.trim()}\n`, "utf8");
  } catch {
    // Diagnostics must never affect sidecar startup.
  }
}

async function readDiagnosticTail(filePath: string): Promise<string> {
  try {
    const content = await fs.readFile(filePath, "utf8");
    return content.slice(-1200).replace(/\s+/g, " ").trim();
  } catch {
    return "";
  }
}

function sanitizeDiagnostic(value: string): string {
  return value.replace(/(token|api[_-]?key|secret)\s*[=:]\s*[^\s]+/gi, "$1=<redacted>");
}

function validateHandshake(handshake: BackendHandshake, expectedPid: number | null): void {
  if (
    handshake.schema_version !== 1 ||
    typeof handshake.host !== "string" ||
    typeof handshake.port !== "number" ||
    handshake.port <= 0 ||
    typeof handshake.pid !== "number" ||
    typeof handshake.token !== "string"
  ) {
    throw new SidecarStartupError("Synapse backend sidecar produced an invalid handshake.");
  }
  if (expectedPid !== null && handshake.pid !== expectedPid) {
    throw new SidecarStartupError("Synapse backend sidecar produced a stale handshake.");
  }
}

function normalizeLoopbackHost(host: string): string {
  return host === "0.0.0.0" || host === "::" ? "127.0.0.1" : host;
}

function delay(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

function waitForExit(child: ChildProcess, timeoutMs: number): Promise<void> {
  if (child.exitCode !== null) {
    return Promise.resolve();
  }
  return new Promise((resolve) => {
    const timeout = setTimeout(resolve, timeoutMs);
    child.once("exit", () => {
      clearTimeout(timeout);
      resolve();
    });
  });
}
