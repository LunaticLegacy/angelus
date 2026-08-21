#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::{
    env,
    net::{TcpListener, TcpStream},
    path::PathBuf,
    process::{Child, Command, Stdio},
    thread,
    time::Duration,
};

use tauri::{Manager, WebviewUrl, WebviewWindowBuilder};

/// Owns the Python child process for the lifetime of the desktop window.
struct BackendProcess(Child);

impl Drop for BackendProcess {
    /// Stop the local FastAPI process when the Tauri application exits.
    fn drop(&mut self) {
        let _ = self.0.kill();
        let _ = self.0.wait();
    }
}

/// Pick an ephemeral localhost port so another local service cannot block startup.
fn reserve_port() -> Result<u16, String> {
    let listener = TcpListener::bind(("127.0.0.1", 0)).map_err(|error| error.to_string())?;
    listener
        .local_addr()
        .map(|address| address.port())
        .map_err(|error| error.to_string())
}

/// Resolve the persistent backend state directory.
///
/// Desktop builds store sessions and connectors under the per-user app data
/// directory so research traces survive application restarts.  An explicit
/// ``ANGELUS_STATE_DIR`` always wins and is used by tests and scripting.
fn backend_state_dir(app: &tauri::AppHandle) -> Result<PathBuf, String> {
    if let Ok(dir) = env::var("ANGELUS_STATE_DIR") {
        return Ok(PathBuf::from(dir));
    }
    app.path()
        .app_data_dir()
        .map(|dir| dir.join("workspace"))
        .map_err(|error| format!("unable to resolve app data directory: {error}"))
}

/// Resolve the packaged sidecar, or use the explicit executable for development.
fn backend_command(app: &tauri::AppHandle, port: u16) -> Result<Command, String> {
    let mut command = if let Ok(executable) = env::var("ANGELUS_BACKEND_EXECUTABLE") {
        Command::new(executable)
    } else if cfg!(debug_assertions) {
        let mut command = Command::new("python");
        command.args(["-m", "angelus", "web"]);
        command.current_dir(PathBuf::from(env!("CARGO_MANIFEST_DIR")).join(".."));
        command
    } else {
        let resource = app
            .path()
            .resource_dir()
            .map_err(|error| error.to_string())?
            .join("binaries")
            .join(if cfg!(windows) {
                "angelus-backend.exe"
            } else {
                "angelus-backend"
            });
        Command::new(resource)
    };

    // Keep the backend loopback-only; the desktop webview is its only client.
    command.args(["--host", "127.0.0.1", "--port", &port.to_string()]);

    // Pin backend state to a stable directory. Packaged PyInstaller
    // ``--onefile`` sidecars run from a temporary extraction directory, so
    // the backend's default project-local ``workspace`` would otherwise be
    // wiped on every exit. Set the canonical Angelus name and its legacy
    // LLMFetcher alias together, matching `angelus --state-dir`.
    if cfg!(debug_assertions) {
        if let Ok(dir) = env::var("ANGELUS_STATE_DIR") {
            command.env("ANGELUS_STATE_DIR", &dir);
            command.env("LLMFETCHER_STATE_DIR", dir);
        }
    } else {
        let dir = backend_state_dir(app)?;
        command.env("ANGELUS_STATE_DIR", &dir);
        command.env("LLMFETCHER_STATE_DIR", &dir);
    }

    command
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::inherit());
    Ok(command)
}

/// Start the backend and wait until its HTTP socket accepts connections.
fn start_backend(app: &tauri::AppHandle, port: u16) -> Result<Child, String> {
    let mut child = backend_command(app, port)?
        .spawn()
        .map_err(|error| format!("unable to start Angelus backend: {error}"))?;
    for _ in 0..100 {
        if TcpStream::connect(("127.0.0.1", port)).is_ok() {
            return Ok(child);
        }
        if let Ok(Some(status)) = child.try_wait() {
            return Err(format!("Angelus backend exited during startup: {status}"));
        }
        thread::sleep(Duration::from_millis(50));
    }
    let _ = child.kill();
    Err("timed out waiting for the Angelus backend".to_string())
}

/// Launch the loopback FastAPI UI in a native Tauri window.
fn run() -> Result<(), Box<dyn std::error::Error>> {
    tauri::Builder::default()
        .setup(|app| {
            let port = reserve_port().map_err(std::io::Error::other)?;
            let child = start_backend(app.handle(), port).map_err(std::io::Error::other)?;
            app.manage(BackendProcess(child));
            let url = format!("http://127.0.0.1:{port}/").parse()?;
            WebviewWindowBuilder::new(app, "main", WebviewUrl::External(url))
                .title("Angelus · Agent Workbench")
                .inner_size(1440.0, 920.0)
                .min_inner_size(1024.0, 700.0)
                .build()?;
            Ok(())
        })
        .run(tauri::generate_context!())?;
    Ok(())
}

fn main() {
    if let Err(error) = run() {
        eprintln!("{error}");
        std::process::exit(1);
    }
}
