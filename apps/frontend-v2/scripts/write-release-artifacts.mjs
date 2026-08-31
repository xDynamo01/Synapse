import crypto from "node:crypto";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";

const scriptDir = path.dirname(fileURLToPath(import.meta.url));
const appRoot = path.resolve(scriptDir, "..");
const releaseDir = path.join(appRoot, "release");
const packageJson = JSON.parse(await fs.readFile(path.join(appRoot, "package.json"), "utf8"));

async function fileExists(filePath) {
  try {
    const stat = await fs.stat(filePath);
    return stat.isFile();
  } catch {
    return false;
  }
}

async function sha256(filePath) {
  const hash = crypto.createHash("sha256");
  hash.update(await fs.readFile(filePath));
  return hash.digest("hex").toUpperCase();
}

const publicVersion = "v0.01";
const installerName = `Synapse-Setup-${publicVersion}.exe`;
const installerPath = path.join(releaseDir, installerName);

if (!(await fileExists(installerPath))) {
  throw new Error(`Installer not found: ${installerPath}`);
}

const artifactHash = await sha256(installerPath);
const manifest = {
  version: publicVersion,
  package_version: packageJson.version,
  product_name: packageJson.build?.productName ?? "Synapse",
  app_id: packageJson.build?.appId ?? null,
  platform: "win32",
  architecture: "x64",
  artifact: installerName,
  sha256: artifactHash,
  signing_status: "UNSIGNED",
  installer: {
    target: "nsis",
    one_click: Boolean(packageJson.build?.nsis?.oneClick),
    per_machine: Boolean(packageJson.build?.nsis?.perMachine)
  },
  runtime: {
    electron: packageJson.devDependencies?.electron ?? null,
    backend_sidecar: "synapse-backend/synapse_backend.exe",
    sidecar_launch: "electron-main-supervised",
    backend_endpoint: "dynamic-loopback-handshake",
    voice: {
      stt_engine: "faster_whisper",
      stt_model: "tiny",
      tts_engine: "piper",
      default_voice_pack: "synapse-default-v0.01",
      default_voice_count: 6
    }
  },
  generated_at_utc: new Date().toISOString()
};

await fs.writeFile(
  path.join(releaseDir, "checksums.txt"),
  `${artifactHash}  ${installerName}\n`,
  "utf8"
);
await fs.writeFile(
  path.join(releaseDir, "release-manifest.json"),
  `${JSON.stringify(manifest, null, 2)}\n`,
  "utf8"
);
await fs.writeFile(
  path.join(releaseDir, "release-notes.md"),
  `# Synapse ${publicVersion} Windows Release Candidate\n\n` +
    `Signing status: **UNSIGNED**.\n\n` +
    `## Included\n\n` +
    `- Frontend V2 Electron shell.\n` +
    `- Packaged backend sidecar launched by the Electron main process.\n` +
    `- Packaged Faster-Whisper tiny STT model.\n` +
    `- Packaged Piper TTS runtime and Synapse Default Voice Pack with 6 voices.\n` +
    `- Official Synapse icon assets.\n` +
    `- NSIS Windows installer.\n\n` +
    `## Validation scope\n\n` +
    `This release candidate must be validated through the gates recorded in ` +
    `docs/frontend/RELEASE_PLAN.md before being treated as ready.\n\n` +
    `## Known limits\n\n` +
    `- The installer is unsigned because no legitimate signing certificate is configured.\n` +
    `- Auto-update is not implemented in this release candidate.\n`,
  "utf8"
);

console.log(`artifact=${installerPath}`);
console.log(`sha256=${artifactHash}`);
