/* K96 PICKS — Electron main process (v2.8)
 * 1) Inaonyesha skrini ya "inapakia" PAPO HAPO (hakuna black screen tena).
 * 2) Inawasha backend: K96_PICKS.exe (kama ipo) → au `py` → au `python` + gui_server.py.
 * 3) Server ikiwaka → inafungua GUI. Ikishindwa → ukurasa wa error wenye sababu + suluhisho.
 */
const { app, BrowserWindow } = require("electron");
const path = require("path");
const fs = require("fs");
const http = require("http");
const { spawn } = require("child_process");

const PORT = 8777;
const URL_ = `http://127.0.0.1:${PORT}/`;
const BOOT_TIMEOUT_MS = 45000;
const APP_VERSION = "2.8.4";
let backend = null;
let win = null;
let bootLog = "";

// Packaged: faili za Python ziko resources/backend (extraResources — NJE ya app.asar,
// kwa sababu Python haiwezi kusoma ndani ya asar). Dev: folda ya juu (forebet_backend).
function backendDir() {
  return app.isPackaged ? path.join(process.resourcesPath, "backend") : path.join(__dirname, "..");
}

function esc(s) {
  return String(s).replace(/[&<>]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c]));
}

function page(body) {
  const html = `<!doctype html><html><head><meta charset="utf-8"><style>
    body{margin:0;height:100vh;display:flex;align-items:center;justify-content:center;background:#0a0e0c;
      color:#e9f0ea;font-family:"Segoe UI",Roboto,Arial,sans-serif}
    .box{max-width:760px;padding:32px;text-align:center}
    h1{font-size:20px;letter-spacing:.6px;margin:14px 0 6px} p{color:#9fb3a6;font-size:14px;line-height:1.6}
    .sp{width:42px;height:42px;border:4px solid #233028;border-top-color:#4ade9a;border-radius:50%;
      margin:0 auto;animation:r 1s linear infinite} @keyframes r{to{transform:rotate(360deg)}}
    .err{color:#ef4444} pre{text-align:left;background:#070b09;border:1px solid #233028;border-radius:10px;
      padding:12px;font-size:11.5px;color:#c2d2c7;max-height:260px;overflow:auto;white-space:pre-wrap}
    ol{text-align:left;color:#c2d2c7;font-size:13.5px;line-height:1.8}
    button{background:#22a86f;border:0;color:#02100a;font-weight:800;padding:10px 22px;border-radius:10px;
      cursor:pointer;font-size:14px;margin-top:10px}
  </style></head><body><div class="box">${body}</div></body></html>`;
  return "data:text/html;charset=utf-8," + encodeURIComponent(html);
}

function showLoading(msg) {
  if (!win) return;
  win.loadURL(page(`<div class="sp"></div><h1>K96 PICKS</h1><p>${esc(msg)}</p>`));
}

function showError(reason) {
  if (!win) return;
  const tail = bootLog.split(/\r?\n/).slice(-30).join("\n");
  win.loadURL(page(`
    <h1 class="err">✗ K96 PICKS haikuweza kuwaka</h1>
    <p>${esc(reason)}</p>
    <ol>
      <li>Hakikisha <b>Python</b> imesakinishwa (python.org — tick "Add python.exe to PATH").</li>
      <li>Endesha <b>INSTALL_K96.bat</b> mara moja (inasakinisha dependencies).</li>
      <li>Tengeneza <b>.env.local</b> kutoka <b>.env.example</b> kwenye folda ya backend, ujaze keys zako za Supabase.</li>
      <li>Funga programu nyingine inayotumia port ${PORT}, kisha jaribu tena.</li>
    </ol>
    ${tail ? `<pre>${esc(tail)}</pre>` : ""}
    <button onclick="location.href='k96://retry'">Jaribu tena</button>`));
}

function ping(cb) {
  const req = http.get(URL_, (res) => { res.resume(); cb(true); });
  req.on("error", () => cb(false));
  req.setTimeout(1500, () => { req.destroy(); });
}

// Server iliyopo ni ya toleo hili? (ya zamani ingeonyesha GUI ya zamani / black screen)
function version(cb) {
  const req = http.get(URL_ + "api/version", (res) => {
    let b = ""; res.on("data", (d) => (b += d));
    res.on("end", () => { try { cb(JSON.parse(b).version || null); } catch (_) { cb(null); } });
  });
  req.on("error", () => cb(null));
  req.setTimeout(2000, () => req.destroy());
}

function killPortOwner(done) {
  if (process.platform !== "win32") return done();
  const k = spawn("cmd", ["/c", `for /f "tokens=5" %a in ('netstat -ano ^| findstr ":${PORT}" ^| findstr "LISTENING"') do taskkill /F /T /PID %a`],
    { windowsHide: true });
  k.on("exit", () => setTimeout(done, 800));
  k.on("error", () => done());
}

function candidates(dir) {
  const exe = path.join(dir, "K96_PICKS.exe");
  const gui = path.join(dir, "gui_server.py");
  const list = [];
  if (fs.existsSync(exe)) list.push([exe, []]);
  if (fs.existsSync(gui)) {
    if (process.platform === "win32") list.push(["py", ["-3", gui]]);
    list.push(["python", [gui]], ["python3", [gui]]);
  }
  return list;
}

function trySpawn(list, i, onFail) {
  if (i >= list.length) return onFail("Python haikupatikana (py / python) — au gui_server.py haipo.");
  const [cmd, args] = list[i];
  bootLog += `\n> ${cmd} ${args.join(" ")}\n`;
  let failed = false;
  try {
    backend = spawn(cmd, args, {
      cwd: backendDir(), windowsHide: true,
      env: { ...process.env, PYTHONUTF8: "1", PYTHONIOENCODING: "utf-8", K96_NO_BROWSER: "1" },
    });
  } catch (e) {
    bootLog += `spawn error: ${e}\n`;
    return trySpawn(list, i + 1, onFail);
  }
  backend.stdout.on("data", (d) => { bootLog += d.toString(); });
  backend.stderr.on("data", (d) => { bootLog += d.toString(); });
  backend.on("error", (e) => {               // ENOENT: amri haipo → jaribu inayofuata
    if (failed) return; failed = true;
    bootLog += `(${cmd} haipatikani: ${e.code || e})\n`;
    trySpawn(list, i + 1, onFail);
  });
  backend.on("exit", (code) => {
    if (failed) return;
    if (code !== 0 && code !== null) {
      failed = true;
      bootLog += `(${cmd} imesimama, code ${code})\n`;
      // `py` ipo lakini script imeanguka → error halisi ya Python, usijaribu nyingine
      onFail(`Backend imesimama (code ${code}). Soma error hapa chini.`);
    }
  });
}

function boot() {
  bootLog = "";
  showLoading("Inawasha injini... (sekunde chache)");
  ping((up) => {
    if (!up) return spawnAndWait();
    version((v) => {
      if (v === APP_VERSION) return win.loadURL(URL_);   // toleo hili tayari hewani (mf. K96_START.bat)
      bootLog += `(server ya zamani kwenye port ${PORT}: version ${v || "?"} — naizima)\n`;
      showLoading("Nazima K96 ya zamani iliyobaki nyuma...");
      killPortOwner(spawnAndWait);
    });
  });
}

function spawnAndWait() {
  {
    const dir = backendDir();
    const list = candidates(dir);
    if (!list.length) return showError(`Faili za backend hazikupatikana kwenye: ${dir}`);
    let done = false, poll = null;
    const fail = (reason) => { if (!done) { done = true; if (poll) clearInterval(poll); showError(reason); } };
    trySpawn(list, 0, fail);
    const t0 = Date.now();
    poll = setInterval(() => {
      ping((ok) => {
        if (done) return;
        if (ok) { done = true; clearInterval(poll); win.loadURL(URL_); }
        else if (Date.now() - t0 > BOOT_TIMEOUT_MS) fail(`Server haikujibu ndani ya sekunde ${BOOT_TIMEOUT_MS / 1000}.`);
      });
    }, 700);
  }
}

function createWindow() {
  win = new BrowserWindow({
    width: 1240, height: 840, minWidth: 380, minHeight: 600,
    backgroundColor: "#0a0e0c",
    icon: path.join(__dirname, "logo_k96.ico"),
    webPreferences: { contextIsolation: true },
    autoHideMenuBar: true,
    title: "K96 PICKS — Smart Pick Engine",
  });
  // kitufe cha "Jaribu tena" kwenye ukurasa wa error
  win.webContents.on("will-navigate", (e, url) => {
    if (url.startsWith("k96://retry")) { e.preventDefault(); stopBackend(); boot(); }
  });
  // GUI ikishindwa kupakia baadaye (mf. server ilizimika) → error page, si black screen
  win.webContents.on("did-fail-load", (_e, code, desc, url) => {
    if (url && url.startsWith(URL_)) showError(`GUI haikupakia (${desc || code}).`);
  });
  boot();
}

function stopBackend() {
  if (backend) { try { backend.kill(); } catch (_) {} backend = null; }
}

app.whenReady().then(createWindow);
app.on("window-all-closed", () => { stopBackend(); app.quit(); });
app.on("before-quit", stopBackend);
