export type {
  DiagnosisResult,
  StockChartView,
  StockResearchView,
} from "@quant-tool/contracts";

export type ConnectionMode =
  | "accessibility"
  | "manual"
  | "permission_required"
  | "app_not_running"
  | "not_detected";

export interface StockContext {
  code: string;
  name: string;
}

export interface WindowFrame {
  x: number;
  y: number;
  width: number;
  height: number;
}

export interface EastmoneyContext {
  running: boolean;
  permissionGranted: boolean;
  mode: ConnectionMode;
  stock: StockContext | null;
  frame: WindowFrame | null;
  followEnabled: boolean;
  observerActive: boolean;
  updatedAtMs: number;
  message: string;
}

export type QuantServiceState = "starting" | "ready" | "unavailable";

export interface QuantServiceStatus {
  state: QuantServiceState;
  message: string;
  updatedAtMs: number;
}
