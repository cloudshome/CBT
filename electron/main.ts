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
      if (!mainWindow.isVisible()) mainWindow.show();
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

  // Priority 1: Packaged binary in bin/cbt_backend.exe (Win) or bin/cbt_backend (Linux)
  const isWin = process.platform === 'win32';
  const packagedExe = path.join(appRoot, 'bin', isWin ? 'cbt_backend.exe' : 'cbt_backend');
  const repoVenv = isWin
    ? path.resolve(__dirname, '../../.venv/Scripts/python.exe')
    : path.resolve(__dirname, '../../.venv/bin/python3');
  const appRootVenv = isWin
    ? path.join(appRoot, '.venv', 'Scripts', 'python.exe')
    : path.join(appRoot, '.venv', 'bin', 'python3');
  const venvPython = fs.existsSync(appRootVenv)
    ? appRootVenv
    : (fs.existsSync(repoVenv)
      ? repoVenv
      : (isWin ? 'python' : 'python3'));

  const scriptCandidates = [
    path.join(appRoot, 'cbt_backend.py'),
    path.resolve(__dirname, '../../cbt_backend.py'),
    path.join(app.getAppPath(), 'cbt_backend.py'),
  ];
  const backendScript = scriptCandidates.find((p) => fs.existsSync(p)) || path.join(appRoot, 'cbt_backend.py');
  const backendCwd = fs.existsSync(backendScript) ? path.dirname(backendScript) : appRoot;

  if (fs.existsSync(packagedExe)) {
    backendProcess = spawn(packagedExe, [], {
      cwd: appRoot,
      env: { ...process.env, CBT_BACKEND_PORT: '8000' },
    });
  } else {
    // Priority 2: Local Python virtual environment
    backendProcess = spawn(venvPython, [backendScript], {
      cwd: backendCwd,
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

function resolveAppIcon(): string | undefined {
  const iconNames = ['favicon.png', 'icon.png', 'favicon.ico'];
  const baseDirs = [
    path.join(appRoot, 'frontend', 'public'),
    path.join(app.getAppPath(), 'frontend', 'public'),
    path.resolve(__dirname, '../../frontend/public'),
  ];
  for (const base of baseDirs) {
    for (const name of iconNames) {
      const p = path.join(base, name);
      if (fs.existsSync(p)) return p;
    }
  }
  return undefined;
}

/**
 * Creates the primary Obsidian-themed Frameless BrowserWindow.
 */
function createMainWindow(): void {
  const windowIcon = resolveAppIcon();

  mainWindow = new BrowserWindow({
    width: 1440,
    height: 920,
    minWidth: 1200,
    minHeight: 760,
    frame: false, // Binance Desktop custom frameless style
    backgroundColor: '#05070c',
    icon: windowIcon,
    show: false,
    webPreferences: {
      preload: path.join(__dirname, 'preload.js'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  // Failsafe timer: display window within 1.5s even if ready-to-show is delayed
  const showFallbackTimer = setTimeout(() => {
    if (mainWindow && !mainWindow.isDestroyed() && !mainWindow.isVisible()) {
      console.log('[Electron Supervisor] Fallback: Displaying main window.');
      mainWindow.show();
      mainWindow.focus();
    }
  }, 1500);

  mainWindow.once('ready-to-show', () => {
    clearTimeout(showFallbackTimer);
    if (mainWindow && !mainWindow.isDestroyed()) {
      mainWindow.show();
      mainWindow.focus();
    }
  });

  mainWindow.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
    console.error(`[Electron Supervisor] did-fail-load: ${errorCode} - ${errorDescription} (${validatedURL})`);
    if (mainWindow && !mainWindow.isDestroyed()) {
      if (!mainWindow.isVisible()) mainWindow.show();
      if (validatedURL !== backendUrl) {
        console.log(`[Electron Supervisor] Falling back to backend server at ${backendUrl}`);
        mainWindow.loadURL(backendUrl);
      }
    }
  });

  // Load URL
  if (isDev && process.env.VITE_DEV_SERVER_URL) {
    mainWindow.loadURL(process.env.VITE_DEV_SERVER_URL);
  } else {
    const candidates = [
      path.join(appRoot, 'frontend', 'dist', 'index.html'),
      path.join(app.getAppPath(), 'frontend', 'dist', 'index.html'),
      path.resolve(__dirname, '../../frontend/dist/index.html'),
    ];
    const foundIndex = candidates.find((p) => fs.existsSync(p));
    if (foundIndex) {
      console.log(`[Electron Supervisor] Loading local UI from: ${foundIndex}`);
      mainWindow.loadFile(foundIndex);
    } else {
      console.log(`[Electron Supervisor] Loading remote UI from: ${backendUrl}`);
      mainWindow.loadURL(backendUrl);
    }
  }

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

/**
 * Configures the native System Tray.
 */
function setupSystemTray(): void {
  const iconPath = resolveAppIcon();
  if (!iconPath) {
    console.warn('[Electron Supervisor] App icon not found; skipping system tray setup.');
    return;
  }

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
  
  // Await backend readiness before displaying UI to eliminate initial sync errors
  try {
    await ensureBackendStarted();
  } catch (err) {
    console.error('[Electron Supervisor] Backend initialization error:', err);
  }

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
