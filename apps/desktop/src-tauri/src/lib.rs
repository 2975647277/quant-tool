mod eastmoney;
mod quant_service;

use eastmoney::{
    CompanionState, clear_manual_stock, get_eastmoney_context, refresh_eastmoney_context,
    request_accessibility_permission, set_follow_enabled, set_manual_stock,
};
use quant_service::{
    QuantServiceState, get_quant_service_status, get_stock_chart, get_stock_diagnosis,
    get_stock_research, refresh_current_research, restart_quant_service,
};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    let app = tauri::Builder::default()
        .manage(CompanionState::default())
        .manage(QuantServiceState::default())
        .invoke_handler(tauri::generate_handler![
            get_eastmoney_context,
            refresh_eastmoney_context,
            request_accessibility_permission,
            set_follow_enabled,
            set_manual_stock,
            clear_manual_stock,
            get_quant_service_status,
            restart_quant_service,
            get_stock_diagnosis,
            get_stock_research,
            get_stock_chart,
            refresh_current_research
        ])
        .setup(|app| {
            eastmoney::start_monitor(app.handle().clone());
            quant_service::start_monitor(app.handle().clone());
            Ok(())
        })
        .build(tauri::generate_context!())
        .expect("failed to build quant companion");

    app.run(|app_handle, event| {
        if matches!(event, tauri::RunEvent::Exit) {
            quant_service::stop(app_handle);
        }
    });
}
