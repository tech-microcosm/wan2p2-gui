// Tauri desktop wrapper for Wan2.2 Video Generator
// Launches Python backend and opens native window

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Command, Child};
use std::thread;
use std::time::Duration;
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, Ordering};
use tauri::Manager;
use tokio::net::TcpListener;
use std::fs::OpenOptions;
use std::io::Write;

static PYTHON_PROCESS: Mutex<Option<Child>> = Mutex::new(None);
static APP_INITIALIZED: AtomicBool = AtomicBool::new(false);

/// Helper function to log to both stderr and a file
fn log_to_file(msg: &str) {
    eprintln!("{}", msg);
    
    // Also write to a log file in temp directory for easier debugging
    if let Ok(temp_dir) = std::env::temp_dir().canonicalize() {
        let log_path = temp_dir.join("wan2p2-gui-debug.log");
        if let Ok(mut file) = OpenOptions::new()
            .create(true)
            .append(true)
            .open(&log_path)
        {
            let timestamp = std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs();
            let _ = writeln!(file, "[{}] {}", timestamp, msg);
        }
    }
}

#[tauri::command]
fn get_app_version() -> String {
    "0.1.2".to_string()
}

#[tauri::command]
fn get_backend_url() -> String {
    "http://localhost:7860".to_string()
}

/// Check if a port is available by trying to bind to it
async fn is_port_available(port: u16) -> bool {
    match TcpListener::bind(format!("127.0.0.1:{}", port)).await {
        Ok(_) => true,
        Err(_) => false,
    }
}

/// Wait for the backend to be ready
async fn wait_for_backend(max_attempts: u32) -> bool {
    for attempt in 1..=max_attempts {
        if !is_port_available(7860).await {
            // Port is in use, backend is likely running
            println!("✅ Backend is ready on port 7860 (attempt {})", attempt);
            return true;
        }
        
        if attempt < max_attempts {
            println!("⏳ Waiting for backend to start... (attempt {}/{})", attempt, max_attempts);
            thread::sleep(Duration::from_millis(500));
        }
    }
    
    println!("❌ Backend failed to start after {} attempts", max_attempts);
    false
}

/// Launch the Python backend process
fn launch_python_backend(app: &tauri::App) -> Result<Child, String> {
    // Check if we're in dev mode by looking for venv
    let venv_python = if cfg!(windows) {
        "../venv/Scripts/python.exe"
    } else {
        "../venv/bin/python"
    };
    
    if std::path::Path::new(venv_python).exists() {
        println!("🚀 [DEV MODE] Launching Python backend from venv: {} -m src.main", venv_python);
        let child = Command::new(venv_python)
            .args(&["-m", "src.main"])
            .spawn()
            .map_err(|e| {
                let error_msg = format!("❌ Failed to launch Python backend from venv: {}", e);
                println!("{}", error_msg);
                error_msg
            })?;
        
        println!("✅ Python backend process started (PID: {})", child.id());
        return Ok(child);
    }
    
    // Production mode: use Tauri's resource resolver API
    let exe_name = if cfg!(windows) {
        "wan2p2-gui.exe"
    } else {
        "wan2p2-gui"
    };
    
    log_to_file("🔍 [DEBUG] Searching for Python backend executable...");
    log_to_file(&format!("🔍 [DEBUG] Current working directory: {:?}", std::env::current_dir()));
    
    // Use Tauri's official resource path resolver
    let resource_path = format!("resources/wan2p2-gui/{}", exe_name);
    log_to_file(&format!("🔍 [DEBUG] Resolving resource path: {}", resource_path));
    
    let backend_path = app.path()
        .resolve(&resource_path, tauri::path::BaseDirectory::Resource)
        .map_err(|e| {
            let error_msg = format!("❌ Failed to resolve resource path '{}': {}", resource_path, e);
            log_to_file(&error_msg);
            error_msg
        })?;
    
    log_to_file(&format!("🔍 [DEBUG] Resolved backend path: {:?}", backend_path));
    log_to_file(&format!("🔍 [DEBUG] Backend exists: {}", backend_path.exists()));
    
    if !backend_path.exists() {
        let error_msg = format!(
            "❌ Python backend executable not found at resolved path: {:?}\n\nPlease ensure the Python backend is built and bundled correctly.",
            backend_path
        );
        log_to_file(&error_msg);
        return Err(error_msg);
    }
    
    log_to_file(&format!("✅ [DEBUG] Found backend at: {:?}", backend_path));
    log_to_file(&format!("🚀 Launching Python backend from: {:?}", backend_path));
    
    let child = Command::new(&backend_path)
        .spawn()
        .map_err(|e| {
            let error_msg = format!("❌ Failed to launch Python backend at {:?}: {}\n\nPlease check:\n1. Python backend is built\n2. All dependencies are installed\n3. No antivirus blocking execution", backend_path, e);
            log_to_file(&error_msg);
            error_msg
        })?;
    
    println!("✅ Python backend process started (PID: {})", child.id());
    Ok(child)
}

/// Stop the Python backend process
fn stop_python_backend() {
    if let Ok(mut process) = PYTHON_PROCESS.lock() {
        if let Some(mut child) = process.take() {
            let _ = child.kill();
            let _ = child.wait();
            println!("✅ Python backend process stopped");
        }
    }
}

fn main() {
    println!("===============================================");
    println!("🚀 MAIN FUNCTION CALLED - App starting");
    println!("===============================================");
    
    tauri::Builder::default()
        .setup(|app| {
            log_to_file("🔧 [SETUP] Setup function called");
            
            // Prevent duplicate initialization
            if APP_INITIALIZED.swap(true, Ordering::SeqCst) {
                log_to_file("⚠️ [SETUP] WARNING: App already initialized! Setup called multiple times!");
                log_to_file("⚠️ [SETUP] This should NOT happen - indicates a bug");
                return Ok(());
            }
            
            log_to_file("✅ [SETUP] First initialization - proceeding");
            
            // Check how many windows exist
            let window_labels: Vec<String> = app.webview_windows()
                .iter()
                .map(|(label, _)| label.clone())
                .collect();
            log_to_file(&format!("📊 [SETUP] Current windows: {} - Labels: {:?}", window_labels.len(), window_labels));
            
            // Launch Python backend on app startup
            log_to_file("🐍 [SETUP] Launching Python backend...");
            match launch_python_backend(app) {
                Ok(child) => {
                    if let Ok(mut process) = PYTHON_PROCESS.lock() {
                        *process = Some(child);
                    }
                    log_to_file("✅ [SETUP] Backend launched successfully");
                }
                Err(e) => {
                    log_to_file(&format!("❌ [SETUP] Failed to launch backend: {}", e));
                    // Don't exit - let the window show an error page
                    return Ok(());
                }
            }
            
            log_to_file("✅ [SETUP] Setup complete - loading page will handle redirect");
            
            Ok(())
        })
        .on_window_event(|window, event| {
            match event {
                tauri::WindowEvent::CloseRequested { .. } => {
                    println!("🛑 [WINDOW EVENT] Close requested for window: {}", window.label());
                    stop_python_backend();
                }
                tauri::WindowEvent::Focused(focused) => {
                    println!("�️  [WINDOW EVENT] Window {} focus changed: {}", window.label(), focused);
                }
                _ => {
                    // Log all other events to catch anything unusual
                    println!("📝 [WINDOW EVENT] Window {} event: {:?}", window.label(), event);
                }
            }
        })
        .invoke_handler(tauri::generate_handler![get_app_version, get_backend_url])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
    
    println!("🏁 [MAIN] App shutdown");
}
