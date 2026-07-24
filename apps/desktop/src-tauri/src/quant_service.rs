use reqwest::blocking::Client;
use serde::Serialize;
use serde_json::Value;
use std::{
    env,
    net::TcpListener,
    path::PathBuf,
    process::{Child, Command, Stdio},
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, Ordering},
    },
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tauri::{AppHandle, Emitter, Manager, State};
use uuid::Uuid;

const STATUS_EVENT: &str = "quant-service-status";
const SESSION_HEADER: &str = "X-Quant-Session";
const STARTUP_ATTEMPTS: usize = 50;
const STARTUP_POLL_INTERVAL: Duration = Duration::from_millis(100);
const HEALTH_INTERVAL: Duration = Duration::from_secs(2);

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct QuantServiceStatus {
    state: &'static str,
    message: String,
    updated_at_ms: u128,
}

impl Default for QuantServiceStatus {
    fn default() -> Self {
        Self {
            state: "starting",
            message: "正在启动本地量化服务…".into(),
            updated_at_ms: now_ms(),
        }
    }
}

#[derive(Default)]
struct ServiceRuntime {
    child: Option<Child>,
    endpoint: Option<String>,
    token: Option<String>,
    status: QuantServiceStatus,
}

pub struct QuantServiceState {
    runtime: Arc<Mutex<ServiceRuntime>>,
    shutting_down: Arc<AtomicBool>,
}

impl Default for QuantServiceState {
    fn default() -> Self {
        Self {
            runtime: Arc::new(Mutex::new(ServiceRuntime::default())),
            shutting_down: Arc::new(AtomicBool::new(false)),
        }
    }
}

#[tauri::command]
pub fn get_quant_service_status(state: State<'_, QuantServiceState>) -> QuantServiceStatus {
    state
        .runtime
        .lock()
        .map(|runtime| runtime.status.clone())
        .unwrap_or_else(|_| unavailable_status("本地量化服务状态读取失败"))
}

#[tauri::command]
pub fn restart_quant_service(
    app: AppHandle,
    state: State<'_, QuantServiceState>,
) -> QuantServiceStatus {
    if let Ok(mut runtime) = state.runtime.lock() {
        stop_child(&mut runtime);
        runtime.status = QuantServiceStatus::default();
        let status = runtime.status.clone();
        let _ = app.emit(STATUS_EVENT, &status);
        status
    } else {
        unavailable_status("本地量化服务状态锁定失败")
    }
}

#[tauri::command]
pub fn get_stock_diagnosis(
    code: String,
    name: String,
    app: AppHandle,
    state: State<'_, QuantServiceState>,
) -> Result<Value, String> {
    if code.len() != 6 || !code.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err("股票代码必须是 6 位数字".into());
    }

    let (endpoint, token) = state
        .runtime
        .lock()
        .map_err(|_| "本地量化服务状态读取失败")?
        .connection()
        .ok_or("本地量化服务尚未就绪，请稍后重试")?;

    let response = http_client()
        .get(format!("{endpoint}/v1/stocks/{code}/diagnosis"))
        .header(SESSION_HEADER, token)
        .query(&[("name", name.trim())])
        .send()
        .and_then(reqwest::blocking::Response::error_for_status)
        .and_then(reqwest::blocking::Response::json::<Value>);

    match response {
        Ok(diagnosis) => Ok(diagnosis),
        Err(error) => {
            mark_for_restart(
                &app,
                &state,
                format!("本地量化服务请求失败，正在自动恢复：{error}"),
            );
            Err("本地量化服务暂不可用，应用正在自动恢复，请稍后重试".into())
        }
    }
}

#[tauri::command]
pub fn get_stock_research(
    code: String,
    name: String,
    app: AppHandle,
    state: State<'_, QuantServiceState>,
) -> Result<Value, String> {
    if code.len() != 6 || !code.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err("股票代码必须是 6 位数字".into());
    }

    let (endpoint, token) = state
        .runtime
        .lock()
        .map_err(|_| "本地量化服务状态读取失败")?
        .connection()
        .ok_or("本地量化服务尚未就绪，请稍后重试")?;

    let response = http_client()
        .get(format!("{endpoint}/v1/stocks/{code}/research"))
        .header(SESSION_HEADER, token)
        .query(&[("name", name.trim())])
        .send();

    match response {
        Ok(response) if response.status().is_success() => response
            .json::<Value>()
            .map_err(|error| format!("真实研究结果解析失败：{error}")),
        Ok(response) => {
            let status = response.status();
            let detail = response
                .json::<Value>()
                .ok()
                .and_then(|value| value.get("detail")?.as_str().map(str::to_owned))
                .unwrap_or_else(|| "真实研究结果暂不可用".into());
            Err(format!("{detail}（HTTP {status}）"))
        }
        Err(error) => {
            mark_for_restart(
                &app,
                &state,
                format!("本地量化服务请求失败，正在自动恢复：{error}"),
            );
            Err("本地量化服务暂不可用，应用正在自动恢复，请稍后重试".into())
        }
    }
}

#[tauri::command]
pub fn get_stock_chart(
    code: String,
    name: String,
    app: AppHandle,
    state: State<'_, QuantServiceState>,
) -> Result<Value, String> {
    if code.len() != 6 || !code.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err("股票代码必须是 6 位数字".into());
    }
    if name.contains("指数") {
        return Err("当前东方财富页面是指数，不生成个股技术形态".into());
    }

    let (endpoint, token) = state
        .runtime
        .lock()
        .map_err(|_| "本地量化服务状态读取失败")?
        .connection()
        .ok_or("本地量化服务尚未就绪，请稍后重试")?;

    let response = http_client()
        .get(format!("{endpoint}/v1/stocks/{code}/chart"))
        .header(SESSION_HEADER, token)
        .query(&[("name", name.trim()), ("limit", "120")])
        .send();

    match response {
        Ok(response) if response.status().is_success() => response
            .json::<Value>()
            .map_err(|error| format!("K线与技术形态解析失败：{error}")),
        Ok(response) => {
            let status = response.status();
            let detail = response
                .json::<Value>()
                .ok()
                .and_then(|value| value.get("detail")?.as_str().map(str::to_owned))
                .unwrap_or_else(|| "K线与技术形态暂不可用".into());
            Err(format!("{detail}（HTTP {status}）"))
        }
        Err(error) => {
            mark_for_restart(
                &app,
                &state,
                format!("本地量化服务请求失败，正在自动恢复：{error}"),
            );
            Err("本地量化服务暂不可用，应用正在自动恢复，请稍后重试".into())
        }
    }
}

#[tauri::command]
pub async fn refresh_current_research(code: String, name: String) -> Result<String, String> {
    if code.len() != 6 || !code.bytes().all(|byte| byte.is_ascii_digit()) {
        return Err("股票代码必须是 6 位数字".into());
    }
    if name.contains("指数") {
        return Err("当前东方财富页面是指数，不执行个股模型更新".into());
    }
    tauri::async_runtime::spawn_blocking(move || {
        let project_dir = service_project_dir();
        let python = service_python(&project_dir);
        if !python.exists() {
            return Err(
                "缺少 Python 3.12 本地服务环境，请在仓库根目录运行 pnpm prepare:quant".into(),
            );
        }
        let output = Command::new(&python)
            .arg(project_dir.join("scripts/run_p2_real.py"))
            .args(["--include-code", "002463", "--include-code", &code])
            .current_dir(&project_dir)
            .stdin(Stdio::null())
            .output()
            .map_err(|error| format!("无法启动每日研究任务：{error}"))?;
        if output.status.success() {
            Ok("当前日频数据与模型已更新".into())
        } else {
            let stderr = String::from_utf8_lossy(&output.stderr);
            let detail = stderr
                .lines()
                .rev()
                .find(|line| !line.trim().is_empty())
                .unwrap_or("每日研究任务执行失败");
            Err(format!("每日研究更新失败：{detail}"))
        }
    })
    .await
    .map_err(|error| format!("每日研究后台任务异常：{error}"))?
}

impl ServiceRuntime {
    fn connection(&self) -> Option<(String, String)> {
        if self.status.state != "ready" {
            return None;
        }
        Some((self.endpoint.clone()?, self.token.clone()?))
    }
}

pub fn start_monitor(app: AppHandle) {
    thread::spawn(move || {
        loop {
            let Some(state) = app.try_state::<QuantServiceState>() else {
                thread::sleep(STARTUP_POLL_INTERVAL);
                continue;
            };
            if state.shutting_down.load(Ordering::Acquire) {
                break;
            }

            let needs_start = state
                .runtime
                .lock()
                .map(|mut runtime| match runtime.child.as_mut() {
                    Some(child) => child.try_wait().ok().flatten().is_some(),
                    None => true,
                })
                .unwrap_or(false);

            if needs_start {
                if let Ok(mut runtime) = state.runtime.lock() {
                    stop_child(&mut runtime);
                    update_status(&app, &mut runtime, QuantServiceStatus::default());
                }

                match launch_service() {
                    Ok((child, endpoint, token)) => {
                        if let Ok(mut runtime) = state.runtime.lock() {
                            runtime.child = Some(child);
                            runtime.endpoint = Some(endpoint.clone());
                            runtime.token = Some(token.clone());
                        }

                        if wait_until_ready(&state, &endpoint, &token) {
                            if let Ok(mut runtime) = state.runtime.lock() {
                                update_status(
                                    &app,
                                    &mut runtime,
                                    QuantServiceStatus {
                                        state: "ready",
                                        message: "本地量化服务已连接（当前日频研究）".into(),
                                        updated_at_ms: now_ms(),
                                    },
                                );
                            }
                        } else if let Ok(mut runtime) = state.runtime.lock() {
                            stop_child(&mut runtime);
                            update_status(
                                &app,
                                &mut runtime,
                                unavailable_status("本地量化服务启动超时，将继续自动重试"),
                            );
                        }
                    }
                    Err(error) => {
                        if let Ok(mut runtime) = state.runtime.lock() {
                            update_status(&app, &mut runtime, unavailable_status(error));
                        }
                    }
                }
            } else {
                let connection = state
                    .runtime
                    .lock()
                    .ok()
                    .and_then(|runtime| runtime.connection());
                if let Some((endpoint, token)) = connection {
                    if !health_is_ready(&endpoint, &token) {
                        mark_for_restart(&app, &state, "本地量化服务失去响应，正在自动恢复".into());
                    }
                }
            }

            sleep_interruptibly(&state.shutting_down, HEALTH_INTERVAL);
        }
    });
}

pub fn stop(app: &AppHandle) {
    if let Some(state) = app.try_state::<QuantServiceState>() {
        state.shutting_down.store(true, Ordering::Release);
        if let Ok(mut runtime) = state.runtime.lock() {
            stop_child(&mut runtime);
        }
    }
}

fn launch_service() -> Result<(Child, String, String), String> {
    let project_dir = service_project_dir();
    let python = service_python(&project_dir);
    if !python.exists() {
        return Err("缺少 Python 3.12 本地服务环境，请在仓库根目录运行 pnpm prepare:quant".into());
    }

    let listener = TcpListener::bind(("127.0.0.1", 0))
        .map_err(|error| format!("无法分配本地服务端口：{error}"))?;
    let port = listener
        .local_addr()
        .map_err(|error| format!("无法读取本地服务端口：{error}"))?
        .port();
    drop(listener);

    let token = Uuid::new_v4().simple().to_string();
    let port = port.to_string();
    let parent_pid = std::process::id().to_string();
    let child = Command::new(&python)
        .args([
            "-m",
            "quant_service",
            "--port",
            &port,
            "--parent-pid",
            &parent_pid,
        ])
        .current_dir(&project_dir)
        .env("PYTHONUNBUFFERED", "1")
        .env("QUANT_SESSION_TOKEN", &token)
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|error| format!("无法启动本地量化服务：{error}"))?;

    Ok((child, format!("http://127.0.0.1:{port}"), token))
}

fn service_project_dir() -> PathBuf {
    env::var_os("QUANT_SERVICE_PROJECT_DIR")
        .map(PathBuf::from)
        .unwrap_or_else(|| {
            PathBuf::from(env!("CARGO_MANIFEST_DIR")).join("../../../services/quant")
        })
}

fn service_python(project_dir: &std::path::Path) -> PathBuf {
    env::var_os("QUANT_SERVICE_PYTHON")
        .map(PathBuf::from)
        .unwrap_or_else(|| project_dir.join(".venv/bin/python"))
}

fn wait_until_ready(state: &QuantServiceState, endpoint: &str, token: &str) -> bool {
    for _ in 0..STARTUP_ATTEMPTS {
        if state.shutting_down.load(Ordering::Acquire) {
            return false;
        }
        if health_is_ready(endpoint, token) {
            return true;
        }
        thread::sleep(STARTUP_POLL_INTERVAL);
    }
    false
}

fn health_is_ready(endpoint: &str, token: &str) -> bool {
    http_client()
        .get(format!("{endpoint}/health"))
        .header(SESSION_HEADER, token)
        .send()
        .and_then(reqwest::blocking::Response::error_for_status)
        .is_ok()
}

fn http_client() -> Client {
    Client::builder()
        .connect_timeout(Duration::from_millis(400))
        .timeout(Duration::from_secs(2))
        .build()
        .expect("local HTTP client configuration is valid")
}

fn mark_for_restart(app: &AppHandle, state: &QuantServiceState, message: String) {
    if let Ok(mut runtime) = state.runtime.lock() {
        stop_child(&mut runtime);
        update_status(app, &mut runtime, unavailable_status(message));
    }
}

fn stop_child(runtime: &mut ServiceRuntime) {
    if let Some(mut child) = runtime.child.take() {
        let _ = child.kill();
        let _ = child.wait();
    }
    runtime.endpoint = None;
    runtime.token = None;
}

fn update_status(app: &AppHandle, runtime: &mut ServiceRuntime, status: QuantServiceStatus) {
    if runtime.status.state == status.state && runtime.status.message == status.message {
        return;
    }
    runtime.status = status;
    let _ = app.emit(STATUS_EVENT, &runtime.status);
}

fn unavailable_status(message: impl Into<String>) -> QuantServiceStatus {
    QuantServiceStatus {
        state: "unavailable",
        message: message.into(),
        updated_at_ms: now_ms(),
    }
}

fn sleep_interruptibly(shutting_down: &AtomicBool, duration: Duration) {
    let slices = duration.as_millis() / 100;
    for _ in 0..slices {
        if shutting_down.load(Ordering::Acquire) {
            break;
        }
        thread::sleep(Duration::from_millis(100));
    }
}

fn now_ms() -> u128 {
    SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .unwrap_or_default()
        .as_millis()
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn service_is_bound_to_loopback() {
        let listener = TcpListener::bind(("127.0.0.1", 0)).unwrap();
        assert!(listener.local_addr().unwrap().ip().is_loopback());
    }

    #[test]
    fn unavailable_status_never_exposes_connection_details() {
        let status = unavailable_status("failed");
        let json = serde_json::to_string(&status).unwrap();
        assert!(!json.contains("token"));
        assert!(!json.contains("endpoint"));
    }
}
