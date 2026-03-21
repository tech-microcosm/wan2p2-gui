// Tauri desktop wrapper for Wan2.2 Video Generator
// Launches Python backend and opens native window

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::process::{Command, Child};
use std::thread;
use std::time::Duration;
use std::sync::Mutex;
use tauri::Manager;
use tokio::net::TcpListener;

static PYTHON_PROCESS: Mutex<Option<Child>> = Mutex::new(None);

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
    // Determine the path to the Python executable
    let exe_name = if cfg!(windows) {
        "wan2p2-gui.exe"
    } else {
        "wan2p2-gui"
    };
    
    // Try to find the executable in the app resources
    let exe_path = if cfg!(debug_assertions) {
        // Development: look in dist directory
        format!("./dist/wan2p2-gui/{}", exe_name)
    } else {
        // Production: look in the app bundle
        #[cfg(target_os = "macos")]
        {
            format!("../Resources/wan2p2-gui/{}", exe_name)
        }
        #[cfg(not(target_os = "macos"))]
        {
            format!("./wan2p2-gui/{}", exe_name)
        }
    };
    
    println!("🚀 Launching Python backend from: {}", exe_path);
    
    let child = Command::new(&exe_path)
        .spawn()
        .map_err(|e| format!("Failed to launch Python backend: {}", e))?;
    
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
    tauri::Builder::default()
        .setup(|app| {
            // Launch Python backend on app startup
            match launch_python_backend() {
                Ok(child) => {
                    if let Ok(mut process) = PYTHON_PROCESS.lock() {
                        *process = Some(child);
                    }
                    println!("✅ Backend launched successfully");
                }
                Err(e) => {
                    eprintln!("❌ {}", e);
                    std::process::exit(1);
                }
            }
            
            // Wait for backend to be ready
            let rt = tokio::runtime::Runtime::new().unwrap();
            if !rt.block_on(wait_for_backend(30)) {
                eprintln!("❌ Backend failed to start");
                std::process::exit(1);
            }
            
            // Get the main window and navigate to the backend
            let window = app.get_webview_window("main").unwrap();
            let _ = window.eval("window.location.href = 'http://localhost:7860'");
            
            Ok(())
        })
        .on_window_event(|window, event| {
            match event {
                tauri::WindowEvent::CloseRequested { api, .. } => {
                    // Stop the backend when the window is closed
                    stop_python_backend();
                    api.prevent_close();
                    window.close().unwrap();
                }
                _ => {}
            }
        })
        .invoke_handler(tauri::generate_handler![get_app_version, get_backend_url])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
