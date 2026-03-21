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

static PYTHON_PROCESS: Mutex<Option<Child>> = Mutex::new(None);
static APP_INITIALIZED: AtomicBool = AtomicBool::new(false);

#[tauri::command]
fn get_app_version() -> String {
    "0.1.0".to_string()
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

/// Launch the Python backend executable
fn launch_python_backend() -> Result<Child, String> {
    // In dev mode, try to run Python script directly from venv
    #[cfg(debug_assertions)]
    {
        let venv_python = if cfg!(windows) {
            "../venv/Scripts/python.exe"
        } else {
            "../venv/bin/python"
        };
        
        // Check if venv python exists
        if std::path::Path::new(&venv_python).exists() {
            println!("🚀 [DEV MODE] Launching Python backend from venv: {} -m src.main", venv_python);
            
            // Run as module from project root to support relative imports
            let child = Command::new(venv_python)
                .arg("-m")
                .arg("src.main")
                .current_dir("..") // Run from project root
                .spawn()
                .map_err(|e| format!("Failed to launch Python script: {}", e))?;
            
            println!("✅ Python backend process started (PID: {})", child.id());
            return Ok(child);
        }
    }
    
    // Production mode or fallback: use PyInstaller executable
    let exe_name = if cfg!(windows) {
        "wan2p2-gui.exe"
    } else {
        "wan2p2-gui"
    };
    
    // Get the current executable's directory to avoid recursion
    let current_exe = std::env::current_exe().unwrap_or_default();
    let current_exe_str = current_exe.to_string_lossy().to_string();
    
    // Try multiple paths in order of preference
    let paths = vec![
        // Development mode (from src-tauri directory) - check this first
        format!("../dist/wan2p2-gui/{}", exe_name),
        // Development mode (from project root)
        format!("./dist/wan2p2-gui/{}", exe_name),
        // Production: bundled resources directory
        format!("./resources/wan2p2-gui/{}", exe_name),
        // Production: bundled with app
        format!("./wan2p2-gui/{}", exe_name),
        // macOS app bundle
        format!("../Resources/wan2p2-gui/{}", exe_name),
    ];
    
    println!("🔍 [DEBUG] Searching for Python backend executable...");
    println!("🔍 [DEBUG] Current working directory: {:?}", std::env::current_dir());
    
    let mut exe_path = String::new();
    for path in &paths {
        let exists = std::path::Path::new(&path).exists();
        println!("🔍 [DEBUG] Checking path: {} - Exists: {}", path, exists);
        if exists {
            // Check if this is the same as the current executable to prevent recursion
            let canonical_path = std::fs::canonicalize(path).unwrap_or_default();
            let canonical_current = std::fs::canonicalize(&current_exe).unwrap_or_default();
            
            if canonical_path == canonical_current {
                println!("⚠️  [DEBUG] Skipping {} - it's the current executable (would cause infinite loop)", path);
                continue;
            }
            
            exe_path = path.clone();
            println!("✅ [DEBUG] Found backend at: {}", exe_path);
            break;
        }
    }
    
    if exe_path.is_empty() {
        let paths_str = paths.join("\n  - ");
        let error_msg = format!(
            "❌ Python backend executable not found!\n\nSearched paths:\n  - {}\n\nCurrent directory: {:?}\n\nCurrent executable: {}\n\nPlease ensure the Python backend is built using:\n  python -m pip install -r requirements.txt\n  .\\build_executable.bat",
            paths_str,
            std::env::current_dir(),
            current_exe_str
        );
        println!("{}", error_msg);
        return Err(error_msg);
    }
    
    println!("🚀 Launching Python backend from: {}", exe_path);
    
    let child = Command::new(&exe_path)
        .spawn()
        .map_err(|e| {
            let error_msg = format!("❌ Failed to launch Python backend at {}: {}\n\nPlease check:\n1. Python backend is built\n2. All dependencies are installed\n3. No antivirus blocking execution", exe_path, e);
            println!("{}", error_msg);
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
            println!("🔧 [SETUP] Setup function called");
            
            // Prevent duplicate initialization
            if APP_INITIALIZED.swap(true, Ordering::SeqCst) {
                eprintln!("⚠️ [SETUP] WARNING: App already initialized! Setup called multiple times!");
                eprintln!("⚠️ [SETUP] This should NOT happen - indicates a bug");
                return Ok(());
            }
            
            println!("✅ [SETUP] First initialization - proceeding");
            
            // Check how many windows exist
            let window_labels: Vec<String> = app.webview_windows()
                .iter()
                .map(|(label, _)| label.clone())
                .collect();
            println!("📊 [SETUP] Current windows: {} - Labels: {:?}", window_labels.len(), window_labels);
            
            // Launch Python backend on app startup
            println!("🐍 [SETUP] Launching Python backend...");
            match launch_python_backend() {
                Ok(child) => {
                    if let Ok(mut process) = PYTHON_PROCESS.lock() {
                        *process = Some(child);
                    }
                    println!("✅ [SETUP] Backend launched successfully");
                }
                Err(e) => {
                    eprintln!("❌ [SETUP] Failed to launch backend: {}", e);
                    // Don't exit - let the window show an error page
                    return Ok(());
                }
            }
            
            println!("✅ [SETUP] Setup complete - loading page will handle redirect");
            
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
