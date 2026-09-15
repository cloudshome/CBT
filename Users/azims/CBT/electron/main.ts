import {
  app,
  BrowserWindow,
  ipcMain,
  Menu,
  Tray,
  powerSaveBlocker,
  dialog,
} from 'electron';
import * as path from 'path';
import * as fs from 'fs';
import { spawn, ChildProcess } from 'child_process';
import * as http from 'http';

let mainWindow: BrowserWindow | null = null;
let tray: Tray | null = null;
let backendProcess: ChildProcess | null = null;
let powerBlockerId: number | null = null;
let backendUrl = 'http://127.0.0.1:8000';

const isDev = process.env.NODE_ENV === 'development' || !app.isPackaged;
const appRoot = app.isPackaged
  ? path.dirname(app.getPath('exe'))
  : path.resolve(__dirname, '../..');

// Single-instance application lock
const gotTheLock = app.requestSingleInstanceLock();
if (!gotTheLock) {
  app.quit();
} else {
  app.on('second-instance', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.focus();
    }
  });
}

/**
 * Checks if the CBT Python backend is already running on loopback 127.0.0.1:8000.
 */
function isBackendReachable(urlStr: string): Promise<boolean> {
  return new Promise((resolve) => {
    const req = http.get(`${urlStr}/api/system/setup-status`, (res) => {
      resolve(res.statusCode === 200 || res.statusCode === 404);
    });
    req.on('error', () => resolve(false));
    req.setTimeout(1500, () => {
      req.destroy();
      resolve(false);
    });
  });
}

/**
 * Spawns the local CBT Python backend process on loopback 127.0.0.1.
 */
async function ensureBackendStarted(): Promise<void> {
  const alreadyUp = await isBackendReachable(backendUrl);
  if (alreadyUp) {
    console.log(`[Electron Supervisor] CBT Backend is already responding at ${backendUrl}`);
    return;
  }

  console.log('[Electron Supervisor] Spawning CBT background server...');
  const logsDir = path.join(appRoot, 'data', 'logs');
  if (!fs.existsSync(logsDir)) {
    fs.mkdirSync(logsDir, { recursive: true });
  }
  const logStream = fs.createWriteStream(path.join(logsDir, 'cbt_backend.log'), { flags: 'a' });

  // Priority 1: Packaged binary in bin/cbt_backend.exe
  const packagedExe = path.join(appRoot, 'bin', 'cbt_backend.exe');
  if (fs.existsSync(packagedExe)) {
    backendProcess = spawn(packagedExe, [], {
      cwd: appRoot,
      env: { ...process.env, CBT_BACKEND_PORT: '8000' },
    });
  } else {
    // Priority 2: Local Python virtual environment
    const venvPythonWin = path.join(appRoot, '.venv', 'Scripts', 'python.exe');
    const pythonExe = fs.existsSync(venvPythonWin) ? venvPythonWin : 'python';
    backendProcess = spawn(pythonExe, ['cbt_backend.py'], {
      cwd: appRoot,
      env: { ...process.env, CBT_BACKEND_PORT: '8000' },
    });
  }

  if (backendProcess) {
    backendProcess.stdout?.pipe(logStream);
    backendProcess.stderr?.pipe(logStream);

    backendProcess.on('exit', (code, signal) => {
      console.log(`[Electron Supervisor] Backend exited with code ${code}, signal ${signal}`);
      backendProcess = null;
    });
  }

  // Poll until ready (up to 20 seconds)
  const maxAttempts = 40;
  for (let i = 0; i < maxAttempts; i++) {
    await new Promise((r) => setTimeout(r, 500));
    if (await isBackendReachable(backendUrl)) {
      console.log(`[Electron Supervisor] Backend successfully connected at ${backendUrl}`);
      return;
    }
  }
  console.warn('[Electron Supervisor] Backend probe timed out; proceeding to render UI.');
}

/**
 * Creates the primary Obsidian-themed Frameless BrowserWindow.
 */
function createMainWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1200,
    minHeight: 760,
    frame: false, // Binance Desktop custom frameless style
    backgroundColor: '#05070c',
    icon: path.join(__dirname, '../../frontend/public/favicon.ico'),
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  // Load URL
  if (isDev && process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
  } else {
    const indexPath = path.join(appRoot, 'frontend', 'dist', 'index.html');
    if (fs.existsSync(indexPath)) {
      mainWindow.loadFile(indexPath);
    } else {
      mainWindow.loadURL(backendUrl);
    }
  }

  mainWindow.once('ready-to-show', () => {
    if (mainWindow) {
      mainWindow.show();
      mainWindow.focus();
    }
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

/**
 * Configures the Windows native System Tray.
 */
function setupSystemTray(): void {
  const iconPath = path.join(__dirname, '../../frontend/public/favicon.ico');
  if (!fs.existsSync(iconPath)) return;

  tray = new Tray(iconPath);
  const contextMenu = Menu.buildFromTemplate([
    {
      label: 'Open Crypto Brain Terminal',
      click: () => {
        if (mainWindow) {
          if (mainWindow.isMinimized()) mainWindow.restore();
          mainWindow.show();
          mainWindow.focus();
        }
      },
    },
    { type: 'separator' },
    {
      label: 'Trading Mode: PAPER_TRADING (Safe)',
      enabled: false,
    },
    {
      label: 'Emergency Master Kill Switch',
      click: async () => {
        const choice = dialog.showMessageBoxSync({
          type: 'warning',
          buttons: ['ENGAGE KILL SWITCH', 'Cancel'],
          defaultId: 1,
          title: 'Emergency Master Kill Switch',
          message: 'Halt all algorithmic execution and cancel pending orders immediately?',
        });
        if (choice === 0) {
          try {
            http.get(`${backendUrl}/api/execution/kill-switch?engage=true`);
          } catch (e) {
            console.error('Kill switch signal failed:', e);
          }
        }
      },
    },
    { type: 'separator' },
    {
      label: 'Quit CTB Terminal',
      click: () => {
        app.quit();
      },
    },
  ]);

  tray.setToolTip('Crypto Brain Terminal (CBT / SKY)');
  tray.setContextMenu(contextMenu);
  tray.on('double-click', () => {
    if (mainWindow) {
      if (mainWindow.isMinimized()) mainWindow.restore();
      mainWindow.show();
      mainWindow.focus();
    }
  });
}

/**
 * IPC Handlers for frameless titlebar window controls.
 */
function registerIpcHandlers(): void {
  ipcMain.on('window:minimize', () => {
    if (mainWindow) mainWindow.minimize();
  });

  ipcMain.on('window:maximize', () => {
    if (mainWindow) {
      if (mainWindow.isMaximized()) {
        mainWindow.unmaximize();
      } else {
        mainWindow.maximize();
      }
    }
  });

  ipcMain.on('window:close', () => {
    if (mainWindow) mainWindow.close();
  });

  ipcMain.handle('window:isMaximized', () => {
    return mainWindow ? mainWindow.isMaximized() : false;
  });

  ipcMain.handle('system:getAppVersion', () => {
    return app.getVersion();
  });

  ipcMain.handle('system:getBackendUrl', () => {
    return backendUrl;
  });
}

// Application Lifecycle
app.whenReady().then(async () => {
  powerBlockerId = powerSaveBlocker.start('prevent-app-suspension');
  registerIpcHandlers();
  await ensureBackendStarted();
  createMainWindow();
  setupSystemTray();

  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createMainWindow();
    }
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit();
  }
});

app.on('before-quit', () => {
  if (powerBlockerId !== null) {
    powerSaveBlocker.stop(powerBlockerId);
  }
  if (backendProcess) {
    console.log('[Electron Supervisor] Terminating backend process...');
    backendProcess.kill('SIGTERM');
    backendProcess = null;
  }
});
