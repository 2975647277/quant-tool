// @vitest-environment jsdom

import { mount } from "@vue/test-utils";
import { describe, expect, it, vi } from "vitest";
import App from "./App.vue";

vi.mock("./bridge", () => ({
  clearManualStock: vi.fn(),
  getEastmoneyContext: vi.fn().mockResolvedValue({
    running: true,
    permissionGranted: true,
    mode: "accessibility",
    stock: { code: "001309", name: "示例股票" },
    frame: { x: 0, y: 0, width: 1200, height: 800 },
    followEnabled: true,
    observerActive: true,
    updatedAtMs: Date.now(),
    message: "已通过只读无障碍接口识别",
  }),
  onEastmoneyContext: vi.fn().mockResolvedValue(() => undefined),
  refreshEastmoneyContext: vi.fn(),
  requestAccessibilityPermission: vi.fn(),
  setFollowEnabled: vi.fn(),
  setManualStock: vi.fn(),
}));

describe("App", () => {
  it("renders the detected stock and P0 boundary", async () => {
    const wrapper = mount(App);
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain("示例股票");
    });
    expect(wrapper.text()).toContain("001309");
    expect(wrapper.text()).toContain("本阶段不采集行情");
  });
});
