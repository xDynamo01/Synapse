import { contextBridge, ipcRenderer } from "electron";
import type { NativeFilePickerResult, SynapseNativeApi } from "../shared/types.js";

const api: SynapseNativeApi = {
  backendBaseUrl: () => ipcRenderer.invoke("synapse:backend-base-url") as Promise<string>,
  reportBootstrap: (status) => ipcRenderer.invoke("synapse:bootstrap-reported", status) as Promise<void>,
  pickAttachmentFile: () => ipcRenderer.invoke("synapse:attachment:pick-file") as Promise<NativeFilePickerResult>,
  window: {
    minimize: () => ipcRenderer.invoke("synapse:window:minimize") as Promise<void>,
    toggleMaximize: () => ipcRenderer.invoke("synapse:window:toggle-maximize") as Promise<boolean>,
    isMaximized: () => ipcRenderer.invoke("synapse:window:is-maximized") as Promise<boolean>,
    onMaximizedChange: (callback) => {
      const listener = (_event: Electron.IpcRendererEvent, maximized: boolean): void => callback(maximized);
      ipcRenderer.on("synapse:window:maximized-changed", listener);
      return () => ipcRenderer.removeListener("synapse:window:maximized-changed", listener);
    },
    close: () => ipcRenderer.invoke("synapse:window:close") as Promise<void>
  }
};

contextBridge.exposeInMainWorld("synapse", api);
