use serde_json::Value;
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::thread;
use std::time::Duration;
use tauri::Manager;

const SIDECAR_URL: &str = "http://127.0.0.1:18765";

struct SidecarState {
    child: Mutex<Option<Child>>,
}

fn python_bin() -> String {
    std::env::var("MAILRAG_PYTHON").unwrap_or_else(|_| "python3".to_string())
}

fn sidecar_script(_app: &tauri::AppHandle) -> PathBuf {
    if let Ok(custom) = std::env::var("MAILRAG_SIDECAR") {
        return PathBuf::from(custom);
    }
    // Dev: walk up from cwd / executable to find python/sidecar.py
    let mut starts = vec![
        std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")),
    ];
    if let Ok(exe) = std::env::current_exe() {
        if let Some(parent) = exe.parent() {
            starts.push(parent.to_path_buf());
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
    let script = sidecar_script(app);
    if !script.exists() {
        return Err(format!("sidecar script not found: {}", script.display()));
    }
    let mut python_dir = script.clone();
    python_dir.pop();

    Command::new(python_bin())
        .arg(&script)
        .current_dir(&python_dir)
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
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
    let state = app.state::<SidecarState>();
    {
        let mut guard = state.child.lock().map_err(|_| "sidecar lock poisoned")?;
        let alive = guard
            .as_mut()
            .map(|c| c.try_wait().ok().flatten().is_none())
            .unwrap_or(false);
        if !alive {
            *guard = Some(spawn_sidecar(app)?);
        }
    }
    if wait_healthy(8_000) {
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
    if wait_healthy(8_000) {
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
