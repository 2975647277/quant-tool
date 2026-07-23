import { listen, type UnlistenFn } from "@tauri-apps/api/event";
import { invoke } from "@tauri-apps/api/core";
import type { EastmoneyContext } from "./types";

const CONTEXT_EVENT = "eastmoney-context";

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
