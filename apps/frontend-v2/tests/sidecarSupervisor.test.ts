import { spawn } from "node:child_process";
import fs from "node:fs/promises";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { afterEach, describe, expect, it } from "vitest";
import { BackendSidecarSupervisor, resolveSidecarPath, waitForBackendReadiness, waitForHandshake } from "../src/main/sidecar";

const temporaryDirectories: string[] = [];

afterEach(async () => {
  await Promise.all(temporaryDirectories.splice(0).map((directory) => fs.rm(directory, { recursive: true, force: true })));
});

async function temporaryDirectory(): Promise<string> {
  const directory = await fs.mkdtemp(path.join(os.tmpdir(), "synapse-sidecar-test-"));
  temporaryDirectories.push(directory);
  return directory;
}

describe("backend sidecar supervisor", () => {
  it("sets the Electron app name before resolving userData paths", async () => {
    const main = await fs.readFile(path.resolve("src/main/main.ts"), "utf8");
    const setNameIndex = main.indexOf('app.setName("Synapse")');
    const getPathIndex = main.indexOf('app.getPath("userData")');

    expect(setNameIndex).toBeGreaterThanOrEqual(0);
    expect(getPathIndex).toBeGreaterThan(setNameIndex);
  });

  it("resolves an explicit sidecar path before packaged and repository fallbacks", async () => {
    const directory = await temporaryDirectory();
    const executable = path.join(directory, "synapse_backend.exe");
    await fs.writeFile(executable, "");

    await expect(
      resolveSidecarPath({
        currentDir: directory,
        explicitSidecarPath: executable,
        isPackaged: false,
        resourcesPath: directory
      })
    ).resolves.toBe(executable);
  });

  it("allows retry after a failed startup attempt", async () => {
    const directory = await temporaryDirectory();
    const missingSidecar = path.join(directory, "missing-synapse-backend.exe");
    const supervisor = new BackendSidecarSupervisor({
      appUserDataPath: directory,
      currentDir: directory,
      explicitSidecarPath: missingSidecar,
      isPackaged: false,
      resourcesPath: directory,
      startupTimeoutMs: 100
    });

    await expect(supervisor.ensureStarted()).rejects.toThrow("Synapse backend sidecar executable was not found.");
    await expect(supervisor.ensureStarted()).rejects.toThrow("Synapse backend sidecar executable was not found.");
  });

  it("accepts a valid backend handshake", async () => {
    const directory = await temporaryDirectory();
    const handshakePath = path.join(directory, "backend-handshake.json");
    const child = spawn(process.execPath, ["-e", "setTimeout(() => {}, 5000)"], { stdio: "ignore" });
    await fs.writeFile(
      handshakePath,
      JSON.stringify({
        schema_version: 1,
        host: "127.0.0.1",
        port: 54321,
        pid: child.pid,
        token: "token",
        started_at: "2026-08-26T00:00:00Z",
        version: "0.1.0"
      })
    );

    await expect(waitForHandshake(handshakePath, child, 1000)).resolves.toMatchObject({
      host: "127.0.0.1",
      port: 54321
    });
    child.kill();
  });

  it("rejects a stale handshake from a previous sidecar process", async () => {
    const directory = await temporaryDirectory();
    const handshakePath = path.join(directory, "backend-handshake.json");
    const child = spawn(process.execPath, ["-e", "setTimeout(() => {}, 5000)"], { stdio: "ignore" });
    await fs.writeFile(
      handshakePath,
      JSON.stringify({
        schema_version: 1,
        host: "127.0.0.1",
        port: 54321,
        pid: 1,
        token: "token",
        started_at: "2026-08-26T00:00:00Z",
        version: "0.1.0"
      })
    );

    await expect(waitForHandshake(handshakePath, child, 150)).rejects.toThrow("stale handshake");
    child.kill();
  });

  it("rejects when the sidecar exits before producing a handshake", async () => {
    const directory = await temporaryDirectory();
    const handshakePath = path.join(directory, "backend-handshake.json");
    const child = spawn(process.execPath, ["-e", "process.exit(42)"], { stdio: "ignore" });

    await expect(waitForHandshake(handshakePath, child, 1000)).rejects.toThrow(
      "Synapse backend sidecar exited before readiness"
    );
  });

  it("rejects readiness timeout without silently using a localhost fallback", async () => {
    const directory = await temporaryDirectory();
    const handshakePath = path.join(directory, "backend-handshake.json");
    const child = spawn(process.execPath, ["-e", "setTimeout(() => {}, 5000)"], { stdio: "ignore" });

    await expect(waitForHandshake(handshakePath, child, 150)).rejects.toThrow(
      "Synapse backend sidecar did not become ready"
    );
    child.kill();
  });

  it("accepts post-startup readiness only after lifecycle-ready probe succeeds", async () => {
    const server = await readinessServer({ ready: true, startup_status: "ready" });
    const child = spawn(process.execPath, ["-e", "setTimeout(() => {}, 5000)"], { stdio: "ignore" });

    try {
      await expect(waitForBackendReadiness(server.baseUrl, child, 1000)).resolves.toMatchObject({
        schema: "synapse-sidecar-startup-ready-v1",
        ready: true,
        startup_status: "ready"
      });
    } finally {
      child.kill();
      await server.close();
    }
  });

  it("accepts post-startup readiness when lifecycle is degraded but not failed", async () => {
    const server = await readinessServer({ ready: true, startup_status: "degraded" });
    const child = spawn(process.execPath, ["-e", "setTimeout(() => {}, 5000)"], { stdio: "ignore" });

    try {
      await expect(waitForBackendReadiness(server.baseUrl, child, 1000)).resolves.toMatchObject({
        ready: true,
        startup_status: "degraded"
      });
    } finally {
      child.kill();
      await server.close();
    }
  });

  it("rejects handshake-era readiness when lifecycle probe is unavailable", async () => {
    const server = await readinessServer({ ready: false, startup_status: "missing-startup-report", statusCode: 503 });
    const child = spawn(process.execPath, ["-e", "setTimeout(() => {}, 5000)"], { stdio: "ignore" });

    try {
      await expect(waitForBackendReadiness(server.baseUrl, child, 150)).rejects.toThrow(
        "did not pass post-startup readiness"
      );
    } finally {
      child.kill();
      await server.close();
    }
  });

  it("rejects when the sidecar exits before post-startup readiness", async () => {
    const server = await readinessServer({ ready: false, startup_status: "failed", statusCode: 503 });
    const child = spawn(process.execPath, ["-e", "setTimeout(() => process.exit(0), 50)"], { stdio: "ignore" });

    try {
      await expect(waitForBackendReadiness(server.baseUrl, child, 1000)).rejects.toThrow(
        "exited before post-startup readiness"
      );
    } finally {
      await server.close();
    }
  });
});

async function readinessServer(payload: {
  ready: boolean;
  startup_status: string;
  statusCode?: number;
}): Promise<{ baseUrl: string; close: () => Promise<void> }> {
  const server = http.createServer((_request, response) => {
    const body = JSON.stringify({
      schema: "synapse-sidecar-startup-ready-v1",
      ready: payload.ready,
      startup_status: payload.startup_status,
      resources: []
    });
    response.statusCode = payload.statusCode ?? 200;
    response.setHeader("X-Synapse-Service", "synapse-backend");
    response.setHeader("Content-Type", "application/json");
    response.end(body);
  });
  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const address = server.address();
  if (!address || typeof address === "string") {
    throw new Error("Test readiness server did not bind to a TCP port.");
  }
  return {
    baseUrl: `http://127.0.0.1:${address.port}`,
    close: () => new Promise((resolve) => server.close(() => resolve()))
  };
}
