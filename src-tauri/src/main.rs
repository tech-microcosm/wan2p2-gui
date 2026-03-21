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
    let exe_name = if cfg!(windows) {
        "wan2p2-gui.exe"
    } else {
        "wan2p2-gui"
    };
    
    // Try multiple paths in order of preference
    let paths = vec![
        // Production: bundled resources directory
        format!("./resources/wan2p2-gui/{}", exe_name),
        // Development mode
        format!("./dist/wan2p2-gui/{}", exe_name),
        // Production: bundled with app
        format!("./wan2p2-gui/{}", exe_name),
        // macOS app bundle
        format!("../Resources/wan2p2-gui/{}", exe_name),
        // Windows portable
        exe_name.to_string(),
    ];
    
    let mut exe_path = String::new();
    for path in &paths {
        if std::path::Path::new(&path).exists() {
            exe_path = path.clone();
            break;
        }
    }
    
    if exe_path.is_empty() {
        let paths_str = paths.join(", ");
        return Err(format!("Python backend executable not found. Checked: {}", paths_str));
    }
    
    println!("🚀 Launching Python backend from: {}", exe_path);
    
    let child = Command::new(&exe_path)
        .spawn()
        .map_err(|e| format!("Failed to launch Python backend at {}: {}", exe_path, e))?;
    
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
