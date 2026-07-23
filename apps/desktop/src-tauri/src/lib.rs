mod eastmoney;

use eastmoney::{
    CompanionState, clear_manual_stock, get_eastmoney_context, refresh_eastmoney_context,
    request_accessibility_permission, set_follow_enabled, set_manual_stock,
};

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(CompanionState::default())
        .invoke_handler(tauri::generate_handler![
            get_eastmoney_context,
            refresh_eastmoney_context,
            request_accessibility_permission,
            set_follow_enabled,
            set_manual_stock,
            clear_manual_stock
        ])
        .setup(|app| {
            eastmoney::start_monitor(app.handle().clone());
            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("failed to run quant companion");
}
