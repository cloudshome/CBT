import { contextBridge, ipcRenderer } from 'electron';

export interface CtbDesktopAPI {
  minimize: () => void;
  maximize: () => void;
  close: () => void;
  isMaximized: () => Promise<boolean>;
  getAppVersion: () => Promise<string>;
  openExternal: (url: string) => Promise<void>;
  getBackendUrl: () => Promise<string>;
}

const ctbAPI: CtbDesktopAPI = {
  minimize: () => ipcRenderer.send('window:minimize'),
  maximize: () => ipcRenderer.send('window:maximize'),
  close: () => ipcRenderer.send('window:close'),
  isMaximized: () => ipcRenderer.invoke('window:isMaximized'),
  getAppVersion: () => ipcRenderer.invoke('system:getAppVersion'),
  openExternal: (url: string) => ipcRenderer.invoke('shell:openExternal', url),
  getBackendUrl: () => ipcRenderer.invoke('system:getBackendUrl'),
};

contextBridge.exposeInMainWorld('ctb', ctbAPI);
