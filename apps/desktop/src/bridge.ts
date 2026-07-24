import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { invoke } from "@tauri-apps/api/core";
import type {
  DiagnosisResult,
  EastmoneyContext,
  QuantServiceStatus,
  StockChartView,
  StockResearchView,
} from "./types";

const CONTEXT_EVENT = "eastmoney-context";
const QUANT_STATUS_EVENT = "quant-service-status";

export function getEastmoneyContext(): Promise<EastmoneyContext> {
  return invoke("get_eastmoney_context");
}

export function refreshEastmoneyContext(): Promise<EastmoneyContext> {
  return invoke("refresh_eastmoney_context");
}

export function requestAccessibilityPermission(): Promise<EastmoneyContext> {
  return invoke("request_accessibility_permission");
}

export function setFollowEnabled(enabled: boolean): Promise<EastmoneyContext> {
  return invoke("set_follow_enabled", { enabled });
}

export function setManualStock(
  code: string,
  name: string,
): Promise<EastmoneyContext> {
  return invoke("set_manual_stock", { code, name });
}

export function clearManualStock(): Promise<EastmoneyContext> {
  return invoke("clear_manual_stock");
}

export function onEastmoneyContext(
  callback: (context: EastmoneyContext) => void,
): Promise<UnlistenFn> {
  return listen<EastmoneyContext>(CONTEXT_EVENT, (event) =>
    callback(event.payload),
  );
}

export function getQuantServiceStatus(): Promise<QuantServiceStatus> {
  return invoke("get_quant_service_status");
}

export function restartQuantService(): Promise<QuantServiceStatus> {
  return invoke("restart_quant_service");
}

export function getStockDiagnosis(
  code: string,
  name: string,
): Promise<DiagnosisResult> {
  return invoke("get_stock_diagnosis", { code, name });
}

export function getStockResearch(
  code: string,
  name: string,
): Promise<StockResearchView> {
  return invoke("get_stock_research", { code, name });
}

export function getStockChart(
  code: string,
  name: string,
): Promise<StockChartView> {
  return invoke("get_stock_chart", { code, name });
}

export function refreshCurrentResearch(
  code: string,
  name: string,
): Promise<string> {
  return invoke("refresh_current_research", { code, name });
}

export function onQuantServiceStatus(
  callback: (status: QuantServiceStatus) => void,
): Promise<UnlistenFn> {
  return listen<QuantServiceStatus>(QUANT_STATUS_EVENT, (event) =>
    callback(event.payload),
  );
}
