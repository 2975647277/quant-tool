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
    stock: { code: "002463", name: "沪电股份" },
    frame: { x: 0, y: 0, width: 1200, height: 800 },
    followEnabled: true,
    observerActive: true,
    updatedAtMs: Date.now(),
    message: "已通过只读无障碍接口识别",
  }),
  onEastmoneyContext: vi.fn().mockResolvedValue(() => undefined),
  getQuantServiceStatus: vi.fn().mockResolvedValue({
    state: "ready",
    message: "本地量化服务已连接（当前日频研究）",
    updatedAtMs: Date.now(),
  }),
  onQuantServiceStatus: vi.fn().mockResolvedValue(() => undefined),
  getStockResearch: vi.fn().mockResolvedValue({
    stock: { code: "002463", name: "沪电股份" },
    coverage: "selected_top20",
    coverageLabel: "当前日频 Top 20 · 第 8 名",
    isCurrentSignal: true,
    signalAgeDays: 1,
    signalDate: "2026-07-23",
    trainingStartDate: "2023-06-01",
    trainingEndDate: "2026-07-09",
    currentRank: 8,
    currentScore: 0.37,
    rankPercentile: 8 / 30,
    top20Rank: 8,
    top20Score: 0.37,
    top20Weight: 0.05,
    modelVersion: "lightgbm-lambdarank-v1",
    dataVersion: "p2-real-test",
    dataStartDate: "2020-01-01",
    dataEndDate: "2026-07-23",
    universeCount: 30,
    factorDates: 1000,
    rankIc: 0.039,
    icir: 2.94,
    topGroupDailyPositiveExcessRate: 0.532,
    topGroupMeanExcessReturn: 0.009,
    topGroupMaxDrawdown: 0.175,
    eligibleForDefault: false,
    admissionReasons: ["max_drawdown_above_15_percent"],
    generatedAt: new Date().toISOString(),
    disclaimer: "使用最新完整日线生成的实验性研究信号。",
  }),
  refreshCurrentResearch: vi.fn().mockResolvedValue("当前日频数据与模型已更新"),
  restartQuantService: vi.fn(),
  refreshEastmoneyContext: vi.fn(),
  requestAccessibilityPermission: vi.fn(),
  setFollowEnabled: vi.fn(),
  setManualStock: vi.fn(),
}));

describe("App", () => {
  it("renders the current daily signal with explicit data timing", async () => {
    const wrapper = mount(App);
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain("沪电股份");
      expect(wrapper.text()).toContain("LightGBM 当前排名");
    });
    expect(wrapper.text()).toContain("002463");
    expect(wrapper.text()).toContain("第 8 / 30");
    expect(wrapper.text()).toContain("2026/07/23 收盘");
    expect(wrapper.text()).toContain("2026/07/09");
    expect(wrapper.text()).toContain("当前日频研究已连接");
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false);

    await wrapper.get('[aria-label="打开设置"]').trigger("click");
    expect(wrapper.get('[role="dialog"]').text()).toContain("实时贴靠并同步高度");
    expect(wrapper.get('[role="dialog"]').text()).toContain("手动降级");
    expect(wrapper.get('[role="dialog"]').text()).toContain("本地研究服务");
    expect(wrapper.get('[role="dialog"]').text()).toContain("更新当前日频数据");
    expect(wrapper.get('[role="dialog"]').text()).toContain("P2/P3 数据边界");
  });
});
