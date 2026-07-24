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
  getQuantServiceStatus: vi.fn().mockResolvedValue({
    state: "ready",
    message: "本地量化服务已连接（P2/P3 真实研究）",
    updatedAtMs: Date.now(),
  }),
  onQuantServiceStatus: vi.fn().mockResolvedValue(() => undefined),
  getStockResearch: vi.fn().mockResolvedValue({
    stock: { code: "001309", name: "示例股票" },
    coverage: "not_covered",
    coverageLabel: "当前30只研究样本未覆盖",
    isCurrentSignal: false,
    signalDate: "2025-12-17",
    top20Rank: null,
    top20Score: null,
    top20Weight: null,
    modelVersion: "lightgbm-lambdarank-v1",
    dataVersion: "p2-real-test",
    dataStartDate: "2020-01-01",
    dataEndDate: "2025-12-31",
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
    disclaimer: "真实历史样本外研究，不是当前交易信号。",
  }),
  restartQuantService: vi.fn(),
  refreshEastmoneyContext: vi.fn(),
  requestAccessibilityPermission: vi.fn(),
  setFollowEnabled: vi.fn(),
  setManualStock: vi.fn(),
}));

describe("App", () => {
  it("renders real P2/P3 research coverage without a fabricated stock score", async () => {
    const wrapper = mount(App);
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain("示例股票");
      expect(wrapper.text()).toContain("LightGBM 验证快照");
    });
    expect(wrapper.text()).toContain("001309");
    expect(wrapper.text()).toContain("53");
    expect(wrapper.text()).toContain("当前30只研究样本未覆盖");
    expect(wrapper.text()).toContain("不生成个股分数或上涨概率");
    expect(wrapper.text()).toContain("P2/P3 真实历史研究已连接");
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false);

    await wrapper.get('[aria-label="打开设置"]').trigger("click");
    expect(wrapper.get('[role="dialog"]').text()).toContain("实时贴靠并同步高度");
    expect(wrapper.get('[role="dialog"]').text()).toContain("手动降级");
    expect(wrapper.get('[role="dialog"]').text()).toContain("本地研究服务");
    expect(wrapper.get('[role="dialog"]').text()).toContain("P2/P3 数据边界");
  });
});
