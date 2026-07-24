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
    message: "本地量化服务已连接（P1 模拟数据）",
    updatedAtMs: Date.now(),
  }),
  onQuantServiceStatus: vi.fn().mockResolvedValue(() => undefined),
  getStockDiagnosis: vi.fn().mockResolvedValue({
    stock: { code: "001309", name: "示例股票" },
    compositeScore: 76,
    riskLevel: "medium",
    riskLabel: "中等",
    horizonTradingDays: 10,
    excessReturnRankPercentile: 82,
    upsideProbability: 0.63,
    expectedReturnPercent: 3.1,
    downsideRiskPercent: -6.2,
    dimensions: [
      {
        key: "trend",
        label: "趋势质量",
        score: 81,
        summary: "中短期趋势模拟信号相对积极",
      },
    ],
    explanations: ["趋势质量是当前模拟评分中最强的维度（81 分）。"],
    warnings: ["当前结果为模拟数据。"],
    modelVersion: "mock-p1-v1",
    dataVersion: "mock-deterministic-v1",
    generatedAt: new Date().toISOString(),
    simulated: true,
    disclaimer: "模拟结果，不构成投资建议。",
  }),
  restartQuantService: vi.fn(),
  refreshEastmoneyContext: vi.fn(),
  requestAccessibilityPermission: vi.fn(),
  setFollowEnabled: vi.fn(),
  setManualStock: vi.fn(),
}));

describe("App", () => {
  it("renders the detected stock and P1 mock diagnosis", async () => {
    const wrapper = mount(App);
    await vi.waitFor(() => {
      expect(wrapper.text()).toContain("示例股票");
      expect(wrapper.text()).toContain("量化综合评分");
    });
    expect(wrapper.text()).toContain("001309");
    expect(wrapper.text()).toContain("76");
    expect(wrapper.text()).toContain("趋势质量");
    expect(wrapper.text()).toContain("P1 使用模拟数据");
    expect(wrapper.find('[role="dialog"]').exists()).toBe(false);

    await wrapper.get('[aria-label="打开设置"]').trigger("click");
    expect(wrapper.get('[role="dialog"]').text()).toContain("实时贴靠并同步高度");
    expect(wrapper.get('[role="dialog"]').text()).toContain("手动降级");
    expect(wrapper.get('[role="dialog"]').text()).toContain("本地诊断服务");
    expect(wrapper.get('[role="dialog"]').text()).toContain("P1 数据边界");
  });
});
