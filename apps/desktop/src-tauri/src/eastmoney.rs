use regex::Regex;
use serde::Serialize;
use std::{
    process::Command,
    sync::{
        Arc, Mutex,
        atomic::{AtomicBool, AtomicI32, Ordering},
    },
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};
use tauri::{AppHandle, Emitter, LogicalPosition, LogicalSize, Manager, Position, Size, State};

#[cfg(target_os = "macos")]
use axuielement::{
    AXObserver, AXUIElement,
    ax_notification::{
        AX_APPLICATION_ACTIVATED_NOTIFICATION, AX_APPLICATION_DEACTIVATED_NOTIFICATION,
        AX_FOCUSED_UI_ELEMENT_CHANGED_NOTIFICATION, AX_FOCUSED_WINDOW_CHANGED_NOTIFICATION,
        AX_LAYOUT_CHANGED_NOTIFICATION, AX_MAIN_WINDOW_CHANGED_NOTIFICATION,
        AX_TITLE_CHANGED_NOTIFICATION, AX_VALUE_CHANGED_NOTIFICATION, AX_WINDOW_MOVED_NOTIFICATION,
        AX_WINDOW_RESIZED_NOTIFICATION,
    },
    is_process_trusted, is_process_trusted_with_prompt, run_current_run_loop,
};

const EASTMONEY_PROCESS_PATH: &str = "/Applications/东方财富.app/Contents/MacOS/东方财富";
const CONTEXT_EVENT: &str = "eastmoney-context";
const PANEL_GAP: f64 = 8.0;
const CONTEXT_POLL_INTERVAL: Duration = Duration::from_millis(650);
const FRAME_SYNC_INTERVAL: Duration = Duration::from_millis(16);
const FRAME_IDLE_INTERVAL: Duration = Duration::from_millis(100);
const EVENT_DEBOUNCE_INTERVAL: Duration = Duration::from_millis(80);
const MIN_PANEL_INNER_HEIGHT: f64 = 240.0;

#[derive(Debug, Clone, Serialize, PartialEq, Eq)]
#[serde(rename_all = "camelCase")]
pub struct StockContext {
    code: String,
    name: String,
}

#[derive(Debug, Clone, Copy, Serialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct WindowFrame {
    x: f64,
    y: f64,
    width: f64,
    height: f64,
}

#[derive(Debug, Clone, Serialize, PartialEq)]
#[serde(rename_all = "camelCase")]
pub struct EastmoneyContext {
    running: bool,
    permission_granted: bool,
    mode: &'static str,
    stock: Option<StockContext>,
    frame: Option<WindowFrame>,
    follow_enabled: bool,
    observer_active: bool,
    updated_at_ms: u128,
    message: String,
}

impl Default for EastmoneyContext {
    fn default() -> Self {
        Self {
            running: false,
            permission_granted: false,
            mode: "app_not_running",
            stock: None,
            frame: None,
            follow_enabled: true,
            observer_active: false,
            updated_at_ms: now_ms(),
            message: "正在检查东方财富…".into(),
        }
    }
}

#[derive(Default)]
pub struct CompanionState {
    context: Arc<Mutex<EastmoneyContext>>,
    manual_stock: Arc<Mutex<Option<StockContext>>>,
    observer_active: Arc<AtomicBool>,
    refresh_pending: Arc<AtomicBool>,
    target_pid: Arc<AtomicI32>,
}

#[tauri::command]
pub fn get_eastmoney_context(state: State<'_, CompanionState>) -> EastmoneyContext {
    state.context.lock().expect("context lock poisoned").clone()
}

#[tauri::command]
pub fn refresh_eastmoney_context(
    app: AppHandle,
    state: State<'_, CompanionState>,
) -> EastmoneyContext {
    refresh_and_publish(&app, &state);
    get_eastmoney_context(state)
}

#[tauri::command]
pub fn request_accessibility_permission(
    app: AppHandle,
    state: State<'_, CompanionState>,
) -> EastmoneyContext {
    #[cfg(target_os = "macos")]
    {
        let _ = is_process_trusted_with_prompt();
    }
    refresh_and_publish(&app, &state);
    get_eastmoney_context(state)
}

#[tauri::command]
pub fn set_follow_enabled(
    enabled: bool,
    app: AppHandle,
    state: State<'_, CompanionState>,
) -> EastmoneyContext {
    {
        let mut context = state.context.lock().expect("context lock poisoned");
        context.follow_enabled = enabled;
    }
    refresh_and_publish(&app, &state);
    let context = get_eastmoney_context(state);
    if enabled {
        if let Some(frame) = context.frame {
            follow_eastmoney_window(&app, frame);
        }
    }
    context
}

#[tauri::command]
pub fn set_manual_stock(
    code: String,
    name: String,
    app: AppHandle,
    state: State<'_, CompanionState>,
) -> Result<EastmoneyContext, String> {
    if !is_valid_stock_code(&code) {
        return Err("股票代码必须是 6 位数字".into());
    }
    *state
        .manual_stock
        .lock()
        .map_err(|_| "manual stock lock poisoned")? = Some(StockContext {
        code,
        name: name.trim().to_string(),
    });
    refresh_and_publish(&app, &state);
    Ok(get_eastmoney_context(state))
}

#[tauri::command]
pub fn clear_manual_stock(app: AppHandle, state: State<'_, CompanionState>) -> EastmoneyContext {
    *state
        .manual_stock
        .lock()
        .expect("manual stock lock poisoned") = None;
    refresh_and_publish(&app, &state);
    get_eastmoney_context(state)
}

pub fn start_monitor(app: AppHandle) {
    start_frame_tracker(app.clone());
    let monitor_app = app.clone();
    thread::spawn(move || {
        let mut observed_pid = None;
        loop {
            let current_pid = find_eastmoney_pid();
            let state = app.try_state::<CompanionState>();
            if let Some(state) = state.as_ref() {
                state
                    .target_pid
                    .store(current_pid.unwrap_or_default(), Ordering::Release);
            }

            if current_pid != observed_pid {
                observed_pid = current_pid;
                if let Some(state) = state.as_ref() {
                    state.observer_active.store(false, Ordering::Release);
                }
                if current_pid.is_none() {
                    set_panel_layer(&app, false);
                }
            }

            if let (Some(pid), Some(state)) = (current_pid, state.as_ref()) {
                ensure_ax_observer(&app, state, pid);
            }

            if let Some(state) = monitor_app.try_state::<CompanionState>() {
                refresh_and_publish(&monitor_app, &state);
            }
            thread::sleep(CONTEXT_POLL_INTERVAL);
        }
    });
}

fn refresh_and_publish(app: &AppHandle, state: &CompanionState) {
    let follow_enabled = state
        .context
        .lock()
        .map(|context| context.follow_enabled)
        .unwrap_or(true);
    let manual_stock = state
        .manual_stock
        .lock()
        .map(|stock| stock.clone())
        .unwrap_or_default();

    let observer_active = state.observer_active.load(Ordering::Acquire);
    let mut next = inspect_eastmoney(follow_enabled, observer_active);
    if let Some(stock) = manual_stock {
        next.mode = "manual";
        next.stock = Some(stock);
        next.message = "当前使用手动股票代码；可随时恢复自动识别。".into();
    }

    let changed = state
        .context
        .lock()
        .map(|mut current| {
            if same_visible_state(&current, &next) {
                false
            } else {
                *current = next.clone();
                true
            }
        })
        .unwrap_or(false);

    if changed {
        let _ = app.emit(CONTEXT_EVENT, &next);
    }
}

fn same_visible_state(left: &EastmoneyContext, right: &EastmoneyContext) -> bool {
    left.running == right.running
        && left.permission_granted == right.permission_granted
        && left.mode == right.mode
        && left.stock == right.stock
        && left.frame == right.frame
        && left.follow_enabled == right.follow_enabled
        && left.observer_active == right.observer_active
        && left.message == right.message
}

fn inspect_eastmoney(follow_enabled: bool, observer_active: bool) -> EastmoneyContext {
    let Some(pid) = find_eastmoney_pid() else {
        return EastmoneyContext {
            follow_enabled,
            ..EastmoneyContext::default()
        };
    };

    #[cfg(target_os = "macos")]
    {
        let permission_granted = is_process_trusted();
        if !permission_granted {
            return EastmoneyContext {
                running: true,
                permission_granted: false,
                mode: "permission_required",
                stock: None,
                frame: None,
                follow_enabled,
                observer_active: false,
                updated_at_ms: now_ms(),
                message: "请授权无障碍权限，以只读识别当前股票和窗口位置。".into(),
            };
        }

        let Some(application) = AXUIElement::from_pid(pid) else {
            return inaccessible_context(follow_enabled);
        };
        let stock = detect_stock(&application);
        let frame = read_window_frame(&application);
        let mode = if stock.is_some() {
            "accessibility"
        } else {
            "not_detected"
        };
        let message = if stock.is_some() {
            "已通过只读无障碍接口识别；未执行任何界面操作。"
        } else {
            "东方财富已连接，但当前页面未找到股票代码，可使用手动模式。"
        };

        return EastmoneyContext {
            running: true,
            permission_granted,
            mode,
            stock,
            frame,
            follow_enabled,
            observer_active,
            updated_at_ms: now_ms(),
            message: message.into(),
        };
    }

    #[allow(unreachable_code)]
    inaccessible_context(follow_enabled)
}

fn inaccessible_context(follow_enabled: bool) -> EastmoneyContext {
    EastmoneyContext {
        running: true,
        permission_granted: false,
        mode: "permission_required",
        stock: None,
        frame: None,
        follow_enabled,
        observer_active: false,
        updated_at_ms: now_ms(),
        message: "当前系统不支持东方财富 macOS 联动。".into(),
    }
}

#[cfg(target_os = "macos")]
fn detect_stock(application: &AXUIElement) -> Option<StockContext> {
    let mut texts = Vec::new();
    collect_texts(application, 0, &mut 0_usize, &mut texts);
    detect_stock_from_texts(&texts)
}

#[cfg(target_os = "macos")]
fn collect_texts(
    element: &AXUIElement,
    depth: usize,
    visited: &mut usize,
    texts: &mut Vec<String>,
) {
    if depth > 10 || *visited >= 1_200 {
        return;
    }
    *visited += 1;

    for attribute in ["AXTitle", "AXValue", "AXDescription"] {
        if let Ok(Some(value)) = element.string_attribute(attribute) {
            let value = value.trim();
            if !value.is_empty() && value.len() <= 500 {
                texts.push(value.to_string());
            }
        }
    }

    if let Ok(children) = element.children() {
        for child in children {
            collect_texts(&child, depth + 1, visited, texts);
        }
    }
}

fn detect_stock_from_texts(texts: &[String]) -> Option<StockContext> {
    let primary =
        Regex::new(r"(?P<name>[\p{Han}A-Za-z*ＳＴST·]{2,20})\s*[（(](?P<code>\d{6})[)）]")
            .expect("primary stock regex is valid");

    if let Some(stock) = texts.iter().find_map(|text| {
        primary.captures(text).and_then(|captures| {
            let code = captures.name("code")?.as_str();
            if !is_valid_stock_code(code) {
                return None;
            }
            Some(StockContext {
                code: code.to_string(),
                name: captures.name("name")?.as_str().trim().to_string(),
            })
        })
    }) {
        return Some(stock);
    }

    // 东方财富会把名称和 "(代码)" 暴露成相邻的两个无障碍节点。
    let code_only =
        Regex::new(r"^[（(](?P<code>\d{6})[)）]$").expect("code-only stock regex is valid");
    let name_only =
        Regex::new(r"^[\p{Han}A-Za-z*ＳＴ·]{2,20}$").expect("name-only stock regex is valid");

    texts.windows(2).find_map(|pair| {
        let captures = code_only.captures(pair[1].trim())?;
        let name = pair[0].trim();
        let code = captures.name("code")?.as_str();
        if !name_only.is_match(name) || !is_valid_stock_code(code) {
            return None;
        }
        Some(StockContext {
            code: code.to_string(),
            name: name.to_string(),
        })
    })
}

fn is_valid_stock_code(code: &str) -> bool {
    code.len() == 6 && code.bytes().all(|byte| byte.is_ascii_digit())
}

#[cfg(target_os = "macos")]
fn read_window_frame(application: &AXUIElement) -> Option<WindowFrame> {
    let window = application
        .element_attribute("AXFocusedWindow")
        .ok()
        .flatten()
        .or_else(|| {
            application
                .element_array_attribute("AXWindows")
                .ok()?
                .into_iter()
                .next()
        })?;
    read_frame_from_window(&window)
}

#[cfg(target_os = "macos")]
fn read_frame_from_window(window: &AXUIElement) -> Option<WindowFrame> {
    let position = window.point_attribute("AXPosition").ok().flatten()?;
    let size = window.size_attribute("AXSize").ok().flatten()?;

    Some(WindowFrame {
        x: position.x,
        y: position.y,
        width: size.width,
        height: size.height,
    })
}

fn follow_eastmoney_window(app: &AppHandle, frame: WindowFrame) {
    let Some(panel) = app.get_webview_window("main") else {
        return;
    };
    let (Ok(panel_outer_size), Ok(panel_inner_size)) = (panel.outer_size(), panel.inner_size())
    else {
        return;
    };
    let scale = panel.scale_factor().unwrap_or(1.0);
    let panel_outer_width = f64::from(panel_outer_size.width) / scale;
    let panel_outer_height = f64::from(panel_outer_size.height) / scale;
    let panel_inner_width = f64::from(panel_inner_size.width) / scale;
    let panel_inner_height = f64::from(panel_inner_size.height) / scale;
    let target_inner_height =
        matched_panel_inner_height(frame.height, panel_outer_height, panel_inner_height);
    let right_x = frame.x + frame.width + PANEL_GAP;
    let left_x = (frame.x - panel_outer_width - PANEL_GAP).max(0.0);
    let target_x = panel
        .current_monitor()
        .ok()
        .flatten()
        .map(|monitor| {
            let monitor_position = monitor.position();
            let monitor_size = monitor.size();
            let monitor_scale = monitor.scale_factor();
            let max_x =
                f64::from(monitor_position.x) + f64::from(monitor_size.width) / monitor_scale;
            if right_x + panel_outer_width <= max_x {
                right_x
            } else {
                left_x
            }
        })
        .unwrap_or(right_x);

    let _ = panel.set_size(Size::Logical(LogicalSize::new(
        panel_inner_width,
        target_inner_height,
    )));
    let _ = panel.set_position(Position::Logical(LogicalPosition::new(
        target_x,
        frame.y.max(0.0),
    )));
}

fn set_panel_layer(app: &AppHandle, follows_eastmoney_layer: bool) {
    if let Some(panel) = app.get_webview_window("main") {
        let _ = panel.set_always_on_top(follows_eastmoney_layer);
    }
}

fn matched_panel_inner_height(
    target_outer_height: f64,
    panel_outer_height: f64,
    panel_inner_height: f64,
) -> f64 {
    let decoration_height = (panel_outer_height - panel_inner_height).max(0.0);
    (target_outer_height - decoration_height).max(MIN_PANEL_INNER_HEIGHT)
}

fn find_eastmoney_pid() -> Option<i32> {
    let output = Command::new("pgrep")
        .args(["-f", EASTMONEY_PROCESS_PATH])
        .output()
        .ok()?;
    if !output.status.success() {
        return None;
    }
    String::from_utf8(output.stdout)
        .ok()?
        .lines()
        .find_map(|line| line.trim().parse::<i32>().ok())
}

#[cfg(target_os = "macos")]
fn start_frame_tracker(app: AppHandle) {
    thread::spawn(move || {
        let mut cached_pid = 0;
        let mut application = None;
        let mut last_frame = None;

        loop {
            let Some(state) = app.try_state::<CompanionState>() else {
                thread::sleep(FRAME_IDLE_INTERVAL);
                continue;
            };
            let pid = state.target_pid.load(Ordering::Acquire);
            if pid <= 0 || !is_process_trusted() {
                cached_pid = 0;
                application = None;
                last_frame = None;
                thread::sleep(FRAME_IDLE_INTERVAL);
                continue;
            }

            if cached_pid != pid {
                cached_pid = pid;
                application = AXUIElement::from_pid(pid);
                last_frame = None;
            }

            if let Some(frame) = application.as_ref().and_then(read_window_frame) {
                if last_frame != Some(frame) {
                    sync_window_frame(&app, &state, frame);
                    last_frame = Some(frame);
                }
            } else {
                last_frame = None;
            }

            thread::sleep(FRAME_SYNC_INTERVAL);
        }
    });
}

#[cfg(not(target_os = "macos"))]
fn start_frame_tracker(_app: AppHandle) {}

fn sync_window_frame(app: &AppHandle, state: &CompanionState, frame: WindowFrame) {
    let (follow_enabled, payload) = state
        .context
        .lock()
        .map(|mut context| {
            let should_emit = context.frame.is_none();
            context.frame = Some(frame);
            (context.follow_enabled, should_emit.then(|| context.clone()))
        })
        .unwrap_or((false, None));

    if follow_enabled {
        follow_eastmoney_window(app, frame);
    }
    if let Some(context) = payload {
        let _ = app.emit(CONTEXT_EVENT, context);
    }
}

#[cfg(target_os = "macos")]
fn ensure_ax_observer(app: &AppHandle, state: &CompanionState, pid: i32) {
    if !is_process_trusted()
        || state
            .observer_active
            .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
            .is_err()
    {
        return;
    }
    start_ax_observer(app.clone(), pid);
}

#[cfg(not(target_os = "macos"))]
fn ensure_ax_observer(_app: &AppHandle, _state: &CompanionState, _pid: i32) {}

fn queue_context_refresh(app: &AppHandle, state: &CompanionState) {
    if state
        .refresh_pending
        .compare_exchange(false, true, Ordering::AcqRel, Ordering::Acquire)
        .is_err()
    {
        return;
    }

    let refresh_app = app.clone();
    thread::spawn(move || {
        thread::sleep(EVENT_DEBOUNCE_INTERVAL);
        if let Some(state) = refresh_app.try_state::<CompanionState>() {
            refresh_and_publish(&refresh_app, &state);
            thread::sleep(EVENT_DEBOUNCE_INTERVAL);
            state.refresh_pending.store(false, Ordering::Release);
        }
    });
}

#[cfg(target_os = "macos")]
fn start_ax_observer(app: AppHandle, pid: i32) {
    thread::spawn(move || {
        if !is_process_trusted() {
            mark_observer_inactive(&app);
            return;
        }
        let Some(application) = AXUIElement::from_pid(pid) else {
            mark_observer_inactive(&app);
            return;
        };
        let event_app = app.clone();
        let Ok(mut observer) = AXObserver::new(pid, move |event| {
            if let Some(state) = event_app.try_state::<CompanionState>() {
                match event.notification.as_str() {
                    AX_APPLICATION_ACTIVATED_NOTIFICATION => {
                        set_panel_layer(&event_app, true);
                    }
                    AX_APPLICATION_DEACTIVATED_NOTIFICATION => {
                        set_panel_layer(&event_app, false);
                    }
                    AX_WINDOW_MOVED_NOTIFICATION | AX_WINDOW_RESIZED_NOTIFICATION => {
                        if let Some(frame) = read_frame_from_window(&event.element) {
                            sync_window_frame(&event_app, &state, frame);
                        }
                    }
                    _ => queue_context_refresh(&event_app, &state),
                }
            }
        }) else {
            mark_observer_inactive(&app);
            return;
        };

        for notification in [
            AX_APPLICATION_ACTIVATED_NOTIFICATION,
            AX_APPLICATION_DEACTIVATED_NOTIFICATION,
            AX_FOCUSED_UI_ELEMENT_CHANGED_NOTIFICATION,
            AX_FOCUSED_WINDOW_CHANGED_NOTIFICATION,
            AX_MAIN_WINDOW_CHANGED_NOTIFICATION,
            AX_VALUE_CHANGED_NOTIFICATION,
            AX_TITLE_CHANGED_NOTIFICATION,
            AX_LAYOUT_CHANGED_NOTIFICATION,
        ] {
            let _ = observer.add_notification(&application, notification);
        }

        if let Ok(Some(window)) = application.element_attribute("AXFocusedWindow") {
            for notification in [
                AX_WINDOW_MOVED_NOTIFICATION,
                AX_WINDOW_RESIZED_NOTIFICATION,
                AX_TITLE_CHANGED_NOTIFICATION,
            ] {
                let _ = observer.add_notification(&window, notification);
            }
        }

        observer.schedule_on_current_run_loop();
        set_panel_layer(&app, false);
        if let Some(state) = app.try_state::<CompanionState>() {
            refresh_and_publish(&app, &state);
        }
        run_current_run_loop();
        mark_observer_inactive(&app);
    });
}

#[cfg(not(target_os = "macos"))]
fn start_ax_observer(_app: AppHandle, _pid: i32) {}

fn mark_observer_inactive(app: &AppHandle) {
    set_panel_layer(app, false);
    if let Some(state) = app.try_state::<CompanionState>() {
        state.observer_active.store(false, Ordering::Release);
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
    fn detects_parenthesized_eastmoney_stock() {
        let texts = vec![
            "无关内容".to_string(),
            "德明利 (001309) 435.00 -22.20 -4.86%".to_string(),
        ];
        assert_eq!(
            detect_stock_from_texts(&texts),
            Some(StockContext {
                code: "001309".into(),
                name: "德明利".into(),
            })
        );
    }

    #[test]
    fn supports_full_width_parentheses() {
        let texts = vec!["贵州茅台（600519）".to_string()];
        assert_eq!(
            detect_stock_from_texts(&texts),
            Some(StockContext {
                code: "600519".into(),
                name: "贵州茅台".into(),
            })
        );
    }

    #[test]
    fn detects_split_eastmoney_accessibility_nodes() {
        let texts = vec![
            "盘口".to_string(),
            "德明利".to_string(),
            "(001309)".to_string(),
            "435.00".to_string(),
        ];
        assert_eq!(
            detect_stock_from_texts(&texts),
            Some(StockContext {
                code: "001309".into(),
                name: "德明利".into(),
            })
        );
    }

    #[test]
    fn rejects_non_six_digit_codes() {
        assert!(!is_valid_stock_code("12345"));
        assert!(!is_valid_stock_code("ABC519"));
    }

    #[test]
    fn matches_panel_outer_height_to_eastmoney() {
        assert_eq!(matched_panel_inner_height(800.0, 720.0, 692.0), 772.0);
    }
}
