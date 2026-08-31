import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, resolve } from "node:path";

const target = resolve("dist/main/preload/preload.cjs");

const source = String.raw`const { contextBridge, ipcRenderer } = require("electron");

const api = {
  backendBaseUrl: () => ipcRenderer.invoke("synapse:backend-base-url"),
  reportBootstrap: (status) => ipcRenderer.invoke("synapse:bootstrap-reported", status),
  pickAttachmentFile: () => ipcRenderer.invoke("synapse:attachment:pick-file"),
  window: {
    minimize: () => ipcRenderer.invoke("synapse:window:minimize"),
    toggleMaximize: () => ipcRenderer.invoke("synapse:window:toggle-maximize"),
    isMaximized: () => ipcRenderer.invoke("synapse:window:is-maximized"),
    onMaximizedChange: (callback) => {
      const listener = (_event, maximized) => callback(maximized);
      ipcRenderer.on("synapse:window:maximized-changed", listener);
      return () => ipcRenderer.removeListener("synapse:window:maximized-changed", listener);
    },
    close: () => ipcRenderer.invoke("synapse:window:close")
  }
};

contextBridge.exposeInMainWorld("synapse", api);
`;

mkdirSync(dirname(target), { recursive: true });
writeFileSync(target, source, "utf-8");
