import { app, BrowserWindow, dialog, ipcMain } from "electron";
import type { OpenDialogOptions } from "electron";
import fs from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { BackendSidecarSupervisor } from "./sidecar.js";

app.setName("Synapse");
app.commandLine.appendSwitch("autoplay-policy", "no-user-gesture-required");

const currentFile = fileURLToPath(import.meta.url);
const currentDir = path.dirname(currentFile);
const isDevelopment = process.env.SYNAPSE_FRONTEND_DEV === "1";
const smokeMode = process.env.SYNAPSE_ELECTRON_SMOKE === "1";
const iconPath = path.join(currentDir, "../../../assets/icons/synapse.ico");
const maxAttachmentBytes = 25 * 1024 * 1024;
const sidecarStartupTimeoutMs = Number.parseInt(process.env.SYNAPSE_SIDECAR_STARTUP_TIMEOUT_MS ?? "120000", 10);
const sidecarSupervisor = new BackendSidecarSupervisor({
  appUserDataPath: app.getPath("userData"),
  currentDir,
  explicitBackendUrl: process.env.SYNAPSE_BACKEND_URL,
  explicitSidecarPath: process.env.SYNAPSE_BACKEND_SIDECAR_PATH,
  isPackaged: app.isPackaged,
  resourcesPath: process.resourcesPath,
  startupTimeoutMs: Number.isFinite(sidecarStartupTimeoutMs) ? sidecarStartupTimeoutMs : 120_000,
  diagnosticsPath: path.join(app.getPath("userData"), "runtime", "sidecar-startup.log")
});

let mainWindow: BrowserWindow | null = null;
let sidecarStopCompleted = false;

function createMainWindow(): BrowserWindow {
  const window = new BrowserWindow({
    width: 1320,
    height: 840,
    minWidth: 980,
    minHeight: 640,
    title: "Synapse",
    icon: iconPath,
    frame: false,
    show: false,
    backgroundColor: "#03090d",
    titleBarStyle: "hidden",
    webPreferences: {
      preload: path.join(currentDir, "../preload/preload.cjs"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      webSecurity: true
    }
  });
  window.removeMenu();
  mainWindow = window;
  if (isDevelopment) {
    void window.loadURL("http://127.0.0.1:5174");
  } else {
    void window.loadFile(path.join(currentDir, "../../renderer/index.html"));
  }
  window.once("ready-to-show", () => {
    window.show();
  });
  window.on("maximize", () => {
    window.webContents.send("synapse:window:maximized-changed", true);
  });
  window.on("unmaximize", () => {
    window.webContents.send("synapse:window:maximized-changed", false);
  });
  window.on("enter-full-screen", () => {
    window.webContents.send("synapse:window:maximized-changed", true);
  });
  window.on("leave-full-screen", () => {
    window.webContents.send("synapse:window:maximized-changed", window.isMaximized());
  });
  if (smokeMode) {
    window.webContents.once("did-finish-load", () => {
      setTimeout(() => app.quit(), 200);
    });
  }
  return window;
}

function registerIpc(): void {
  ipcMain.handle("synapse:backend-base-url", async () => {
    const runtime = await sidecarSupervisor.ensureStarted();
    return runtime.baseUrl;
  });
  ipcMain.handle("synapse:bootstrap-reported", async (_event, status: unknown) => {
    if (status !== "ready" && status !== "onboarding" && status !== "degraded" && status !== "failed") {
      throw new Error("Invalid bootstrap status.");
    }
  });
  ipcMain.handle("synapse:attachment:pick-file", async (event) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    const selectedPath = await selectAttachmentPath(window);
    if (!selectedPath) {
      return { status: "cancelled" };
    }
    try {
      if (selectedPath.startsWith("\\\\")) {
        return { status: "failed", error: "Network paths are not supported for attachments." };
      }
      const before = await fs.lstat(selectedPath);
      if (!before.isFile() || before.isSymbolicLink()) {
        return { status: "failed", error: "Selected item is not a regular file." };
      }
      if (before.size === 0) {
        return { status: "failed", error: "Empty files are not supported." };
      }
      if (before.size > maxAttachmentBytes) {
        return { status: "failed", error: "File exceeds the 25 MiB attachment limit." };
      }
      const content = await fs.readFile(selectedPath);
      const after = await fs.lstat(selectedPath);
      if (before.size !== after.size || before.mtimeMs !== after.mtimeMs) {
        return { status: "failed", error: "File changed during selection. Try again." };
      }
      const filename = path.basename(selectedPath);
      const mimeType = mimeTypeFor(filename);
      if (!mimeType) {
        return { status: "failed", error: "File type is not supported for attachments." };
      }
      return {
        status: "selected",
        filename,
        mime_type: mimeType,
        size: content.byteLength,
        content_base64: content.toString("base64")
      };
    } catch {
      return { status: "failed", error: "Selected file could not be read." };
    }
  });
  ipcMain.handle("synapse:window:minimize", (event) => {
    BrowserWindow.fromWebContents(event.sender)?.minimize();
  });
  ipcMain.handle("synapse:window:toggle-maximize", (event) => {
    const window = BrowserWindow.fromWebContents(event.sender);
    if (!window) {
      return false;
    }
    if (window.isMaximized()) {
      window.unmaximize();
    } else {
      window.maximize();
    }
    return window.isMaximized();
  });
  ipcMain.handle("synapse:window:is-maximized", (event) => {
    return BrowserWindow.fromWebContents(event.sender)?.isMaximized() ?? false;
  });
  ipcMain.handle("synapse:window:close", (event) => {
    BrowserWindow.fromWebContents(event.sender)?.close();
  });
}

async function selectAttachmentPath(window: BrowserWindow | null): Promise<string | null> {
  const options: OpenDialogOptions = {
    title: "Select attachment",
    properties: ["openFile"],
    filters: [
      { name: "Supported files", extensions: ["pdf", "png", "jpg", "jpeg", "txt", "md", "csv", "json"] }
    ]
  };
  const result = window ? await dialog.showOpenDialog(window, options) : await dialog.showOpenDialog(options);
  if (result.canceled || result.filePaths.length === 0) {
    return null;
  }
  return result.filePaths[0];
}

function mimeTypeFor(filename: string): string | null {
  switch (path.extname(filename).toLowerCase()) {
    case ".pdf":
      return "application/pdf";
    case ".png":
      return "image/png";
    case ".jpg":
    case ".jpeg":
      return "image/jpeg";
    case ".txt":
      return "text/plain";
    case ".md":
      return "text/markdown";
    case ".csv":
      return "text/csv";
    case ".json":
      return "application/json";
    default:
      return null;
  }
}

void app.whenReady().then(() => {
  registerIpc();
  void sidecarSupervisor.ensureStarted().catch((error) => {
    console.error("SYNAPSE_SIDECAR_STARTUP_FAILED", error);
  });
  createMainWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});

app.on("will-quit", (event) => {
  if (sidecarStopCompleted) {
    return;
  }
  event.preventDefault();
  void sidecarSupervisor.stop().finally(() => {
    sidecarStopCompleted = true;
    app.quit();
  });
});
