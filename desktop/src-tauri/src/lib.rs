use serde_json::Value;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;
use tauri::Manager;

const SIDECAR_URL: &str = "http://127.0.0.1:18765";
const SIDECAR_BIN: &str = "mailrag-sidecar";

struct SidecarState {
    child: Mutex<Option<Child>>,
}

fn python_bin() -> String {
    std::env::var("MAILRAG_PYTHON").unwrap_or_else(|_| "python3".to_string())
}

fn sidecar_binary_name() -> &'static str {
    if cfg!(windows) {
        "mailrag-sidecar.exe"
    } else {
        SIDECAR_BIN
    }
}

fn candidate_sidecar_bins(app: &tauri::AppHandle) -> Vec<PathBuf> {
    let mut out = Vec::new();
    if let Ok(custom) = std::env::var("MAILRAG_SIDECAR_BIN") {
        out.push(PathBuf::from(custom));
    }
    let name = sidecar_binary_name();
    if let Ok(exe) = std::env::current_exe() {
        if let Some(dir) = exe.parent() {
            out.push(dir.join(name));
            // macOS .app: Contents/MacOS → also check Resources
            if let Some(contents) = dir.parent() {
                out.push(contents.join("Resources").join(name));
                out.push(contents.join("Resources").join("bin").join(name));
            }
        }
    }
    if let Ok(res) = app.path().resource_dir() {
        out.push(res.join(name));
        out.push(res.join("bin").join(name));
    }
    // Dev binaries folder
    out.push(PathBuf::from("src-tauri/binaries").join(name));
    out.push(PathBuf::from("binaries").join(name));
    out
}

fn find_sidecar_binary(app: &tauri::AppHandle) -> Option<PathBuf> {
    candidate_sidecar_bins(app).into_iter().find(|p| p.is_file())
}

fn sidecar_script(_app: &tauri::AppHandle) -> PathBuf {
    if let Ok(custom) = std::env::var("MAILRAG_SIDECAR") {
        return PathBuf::from(custom);
    }
    let mut starts = vec![std::env::current_dir().unwrap_or_else(|_| PathBuf::from("."))];
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            starts.push(parent.to_path_buf());
            if let Some(contents) = parent.parent() {
                starts.push(contents.join("Resources"));
            }
        }
    }
    for mut path in starts {
        for _ in 0..8 {
            let candidate = path.join("python/sidecar.py");
            if candidate.exists() {
                return candidate.canonicalize().unwrap_or(candidate);
            }
            let candidate2 = path.join("../python/sidecar.py");
            if candidate2.exists() {
                return candidate2.canonicalize().unwrap_or(candidate2);
            }
            if let Some(parent) = path.parent() {
                path = parent.to_path_buf();
            } else {
                break;
            }
        }
    }
    PathBuf::from("../python/sidecar.py")
}

fn spawn_sidecar(app: &tauri::AppHandle) -> Result<Child, String> {
    if let Some(bin) = find_sidecar_binary(app) {
        return Command::new(&bin)
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|e| format!("failed to start sidecar binary {}: {e}", bin.display()));
    }

    let script = sidecar_script(app);
    if !script.exists() {
        return Err(format!(
            "sidecar not found (binary '{}' or script {}). Build with scripts/build_sidecar.sh first.",
            sidecar_binary_name(),
            script.display()
        ));
    }
    let mut python_dir = script.clone();
    python_dir.pop();

    // Prefer project venv python when present
    let venv_python = python_dir.join(".venv/bin/python");
    let venv_python_win = python_dir.join(".venv/Scripts/python.exe");
    let py = if venv_python.is_file() {
        venv_python.to_string_lossy().to_string()
    } else if venv_python_win.is_file() {
        venv_python_win.to_string_lossy().to_string()
    } else {
        python_bin()
    };

    Command::new(py)
        .arg(&script)
        .current_dir(&python_dir)
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| format!("failed to start sidecar: {e}"))
}

fn wait_healthy(timeout_ms: u64) -> bool {
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(2))
        .build()
        .ok();
    let Some(client) = client else {
        return false;
    };
    let steps = (timeout_ms / 200).max(1);
    for _ in 0..steps {
        if let Ok(resp) = client.get(format!("{SIDECAR_URL}/health")).send() {
            if resp.status().is_success() {
                return true;
            }
        }
        thread::sleep(Duration::from_millis(200));
    }
    false
}

fn ensure_sidecar(app: &tauri::AppHandle) -> Result<(), String> {
    // Prefer an already-healthy process on the fixed port. Spawning another
    // instance would fail to bind and leave an orphan unmanaged child.
    if wait_healthy(400) {
        return Ok(());
    }
    let state = app.state::<SidecarState>();
    {
        let mut guard = state.child.lock().map_err(|_| "sidecar lock poisoned")?;
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        *guard = Some(spawn_sidecar(app)?);
    }
    if wait_healthy(12_000) {
        Ok(())
    } else {
        Err("AIエンジンとの接続に失敗しました。".into())
    }
}

#[tauri::command]
fn sidecar_health(app: tauri::AppHandle) -> Result<Value, String> {
    ensure_sidecar(&app)?;
    let client = reqwest::blocking::Client::new();
    let resp = client
        .get(format!("{SIDECAR_URL}/health"))
        .send()
        .map_err(|e| e.to_string())?;
    resp.json().map_err(|e| e.to_string())
}

#[tauri::command]
fn sidecar_request(app: tauri::AppHandle, payload: Value) -> Result<Value, String> {
    ensure_sidecar(&app)?;
    let client = reqwest::blocking::Client::builder()
        .timeout(Duration::from_secs(120))
        .build()
        .map_err(|e| e.to_string())?;
    let resp = client
        .post(SIDECAR_URL)
        .json(&payload)
        .send()
        .map_err(|e| format!("Gemini/Sidecar request failed: {e}"))?;
    resp.json().map_err(|e| e.to_string())
}

#[tauri::command]
fn restart_sidecar(app: tauri::AppHandle) -> Result<Value, String> {
    let state = app.state::<SidecarState>();
    {
        let mut guard = state.child.lock().map_err(|_| "sidecar lock poisoned")?;
        if let Some(mut child) = guard.take() {
            let _ = child.kill();
            let _ = child.wait();
        }
        *guard = Some(spawn_sidecar(&app)?);
    }
    if wait_healthy(12_000) {
        Ok(serde_json::json!({"success": true}))
    } else {
        Err("AIエンジンとの接続に失敗しました。".into())
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_opener::init())
        .manage(SidecarState {
            child: Mutex::new(None),
        })
        .setup(|app| {
            let handle = app.handle().clone();
            thread::spawn(move || {
                let _ = ensure_sidecar(&handle);
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            sidecar_health,
            sidecar_request,
            restart_sidecar
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
