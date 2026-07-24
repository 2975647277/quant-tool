<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  clearManualStock,
  getEastmoneyContext,
  getQuantServiceStatus,
  getStockDiagnosis,
  onEastmoneyContext,
  onQuantServiceStatus,
  refreshEastmoneyContext,
  requestAccessibilityPermission,
  restartQuantService,
  setFollowEnabled,
  setManualStock,
} from "./bridge";
import type {
  DiagnosisResult,
  EastmoneyContext,
  QuantServiceStatus,
} from "./types";

const context = ref<EastmoneyContext | null>(null);
const quantStatus = ref<QuantServiceStatus | null>(null);
const diagnosis = ref<DiagnosisResult | null>(null);
const actionLoading = ref(false);
const diagnosisLoading = ref(false);
const error = ref("");
const diagnosisError = ref("");
const manualCode = ref("");
const manualName = ref("");
const settingsOpen = ref(false);
let unlistenContext: (() => void) | undefined;
let unlistenQuantStatus: (() => void) | undefined;
let diagnosisRequestId = 0;

const statusLabel = computed(() => {
  switch (context.value?.mode) {
    case "accessibility":
      return "自动联动";
    case "manual":
      return "手动模式";
    case "permission_required":
      return "等待授权";
    case "app_not_running":
      return "App 未运行";
    default:
      return "等待识别";
  }
});

const statusTone = computed(() => {
  if (context.value?.mode === "accessibility") return "connected";
  if (context.value?.mode === "manual") return "manual";
  return "waiting";
});

const serviceLabel = computed(() => {
  switch (quantStatus.value?.state) {
    case "ready":
      return "诊断服务已连接";
    case "unavailable":
      return "诊断服务恢复中";
    default:
      return "诊断服务启动中";
  }
});

const formattedTime = computed(() => {
  if (!context.value?.updatedAtMs) return "尚未刷新";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(context.value.updatedAtMs));
});

const scoreStyle = computed(() => ({
  "--score": `${diagnosis.value?.compositeScore ?? 0}%`,
}));

const riskTone = computed(() => diagnosis.value?.riskLevel ?? "medium");

async function runAction(action: () => Promise<EastmoneyContext>) {
  actionLoading.value = true;
  error.value = "";
  try {
    context.value = await action();
  } catch (cause) {
    error.value = String(cause);
  } finally {
    actionLoading.value = false;
  }
}

async function loadDiagnosis() {
  const stock = context.value?.stock;
  const requestId = ++diagnosisRequestId;
  diagnosis.value = null;
  diagnosisError.value = "";
  if (!stock || quantStatus.value?.state !== "ready") return;

  diagnosisLoading.value = true;
  try {
    const result = await getStockDiagnosis(stock.code, stock.name);
    if (requestId === diagnosisRequestId) diagnosis.value = result;
  } catch (cause) {
    if (requestId === diagnosisRequestId) {
      diagnosisError.value = String(cause);
    }
  } finally {
    if (requestId === diagnosisRequestId) diagnosisLoading.value = false;
  }
}

async function restartService() {
  diagnosisError.value = "";
  diagnosis.value = null;
  quantStatus.value = await restartQuantService();
}

function submitManualStock() {
  const code = manualCode.value.trim();
  const name = manualName.value.trim();
  if (!/^\d{6}$/.test(code)) {
    error.value = "请输入 6 位股票代码";
    return;
  }
  void runAction(() => setManualStock(code, name));
}

watch(
  () => {
    const stock = context.value?.stock;
    return stock ? `${stock.code}:${stock.name}` : "";
  },
  () => void loadDiagnosis(),
);

onMounted(async () => {
  try {
    [context.value, quantStatus.value] = await Promise.all([
      getEastmoneyContext(),
      getQuantServiceStatus(),
    ]);
    unlistenContext = await onEastmoneyContext((nextContext) => {
      context.value = nextContext;
    });
    unlistenQuantStatus = await onQuantServiceStatus((nextStatus) => {
      const becameReady =
        quantStatus.value?.state !== "ready" && nextStatus.state === "ready";
      quantStatus.value = nextStatus;
      if (becameReady) void loadDiagnosis();
    });
  } catch (cause) {
    error.value = String(cause);
  }
});

onBeforeUnmount(() => {
  unlistenContext?.();
  unlistenQuantStatus?.();
});
</script>

<template>
  <main class="shell">
    <header class="hero">
      <div>
        <p class="eyebrow">QUANT · P1</p>
        <h1>个股量化诊断</h1>
      </div>
      <div class="hero-actions">
        <span class="status-pill" :class="statusTone">
          <span class="status-dot" />
          {{ statusLabel }}
        </span>
        <button
          class="icon-button settings-trigger"
          aria-label="打开设置"
          aria-controls="settings-drawer"
          :aria-expanded="settingsOpen"
          @click="settingsOpen = true"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true">
            <path
              d="M12 8.7a3.3 3.3 0 1 0 0 6.6 3.3 3.3 0 0 0 0-6.6Zm8.1 4.2-1.7-1a6.8 6.8 0 0 0 0-1.8l1.7-1-1.8-3.2-1.8 1a7.8 7.8 0 0 0-1.6-.9V4h-3.7v2a7.8 7.8 0 0 0-1.6.9l-1.8-1L4 9.1l1.7 1a6.8 6.8 0 0 0 0 1.8l-1.7 1 1.8 3.2 1.8-1a7.8 7.8 0 0 0 1.6.9v2h3.7v-2a7.8 7.8 0 0 0 1.6-.9l1.8 1 1.8-3.2Z"
            />
          </svg>
        </button>
      </div>
    </header>

    <section class="card stock-card">
      <div class="stock-card-top">
        <div class="card-label">东方财富当前股票</div>
        <button
          class="refresh-button"
          :disabled="actionLoading"
          @click="runAction(refreshEastmoneyContext)"
        >
          {{ actionLoading ? "刷新中" : "刷新" }}
        </button>
      </div>
      <template v-if="context?.stock">
        <div class="stock-heading">
          <strong>{{ context.stock.name || "未命名股票" }}</strong>
          <span>{{ context.stock.code }}</span>
        </div>
      </template>
      <div v-else class="empty-stock">等待东方财富中的股票变化</div>
      <div class="meta-row">
        <span>更新于 {{ formattedTime }}</span>
        <span>观察器 {{ context?.observerActive ? "实时" : "轮询兜底" }}</span>
      </div>
    </section>

    <section
      v-if="context && !context.permissionGranted"
      class="notice permission-notice"
    >
      <div>
        <strong>需要无障碍权限</strong>
        <p>只读取当前股票和窗口位置，不执行点击或交易。</p>
      </div>
      <button
        class="primary-button"
        :disabled="actionLoading"
        @click="runAction(requestAccessibilityPermission)"
      >
        请求权限
      </button>
    </section>

    <section
      v-if="quantStatus?.state !== 'ready'"
      class="notice service-notice"
      :class="{ unavailable: quantStatus?.state === 'unavailable' }"
    >
      <div>
        <strong>{{ serviceLabel }}</strong>
        <p>{{ quantStatus?.message || "正在初始化本地服务…" }}</p>
      </div>
      <button
        v-if="quantStatus?.state === 'unavailable'"
        class="secondary-button"
        @click="restartService"
      >
        立即重试
      </button>
    </section>

    <section v-if="diagnosis" class="card diagnosis-card">
      <div class="diagnosis-heading">
        <div>
          <div class="card-label">未来 10 个交易日 · 模拟</div>
          <h2>量化综合评分</h2>
        </div>
        <div class="score-ring" :style="scoreStyle">
          <strong>{{ diagnosis.compositeScore }}</strong>
          <span>分</span>
        </div>
      </div>

      <div class="metric-grid">
        <div>
          <span>超额排名</span>
          <strong>前 {{ 100 - diagnosis.excessReturnRankPercentile }}%</strong>
        </div>
        <div>
          <span>上涨概率</span>
          <strong>{{ Math.round(diagnosis.upsideProbability * 100) }}%</strong>
        </div>
        <div>
          <span>预期收益</span>
          <strong :class="{ positive: diagnosis.expectedReturnPercent >= 0 }">
            {{ diagnosis.expectedReturnPercent >= 0 ? "+" : ""
            }}{{ diagnosis.expectedReturnPercent }}%
          </strong>
        </div>
        <div>
          <span>下行风险</span>
          <strong class="negative">{{ diagnosis.downsideRiskPercent }}%</strong>
        </div>
      </div>

      <div class="risk-row">
        <span>风险等级</span>
        <strong class="risk-badge" :class="riskTone">
          {{ diagnosis.riskLabel }}
        </strong>
      </div>

      <div class="dimension-list">
        <div
          v-for="dimension in diagnosis.dimensions"
          :key="dimension.key"
          class="dimension"
        >
          <div class="dimension-copy">
            <span>{{ dimension.label }}</span>
            <strong>{{ dimension.score }}</strong>
          </div>
          <div class="dimension-track">
            <span :style="{ width: `${dimension.score}%` }" />
          </div>
          <p>{{ dimension.summary }}</p>
        </div>
      </div>

      <div class="explanation-panel">
        <div class="card-label">为什么是这个分数</div>
        <p v-for="item in diagnosis.explanations.slice(0, 2)" :key="item">
          {{ item }}
        </p>
      </div>

      <div class="diagnosis-meta">
        <span>{{ diagnosis.modelVersion }}</span>
        <span>{{ diagnosis.dataVersion }}</span>
      </div>
    </section>

    <section
      v-else-if="diagnosisLoading"
      class="card diagnosis-card diagnosis-loading"
      aria-label="诊断加载中"
    >
      <div class="skeleton wide" />
      <div class="skeleton score" />
      <div class="skeleton" />
      <div class="skeleton" />
      <div class="skeleton short" />
    </section>

    <section
      v-else-if="context?.stock && quantStatus?.state === 'ready'"
      class="notice service-notice unavailable"
    >
      <div>
        <strong>评分卡加载失败</strong>
        <p>{{ diagnosisError || "未能取得模拟诊断结果" }}</p>
      </div>
      <button class="secondary-button" @click="loadDiagnosis">重新加载</button>
    </section>

    <section v-else-if="!context?.stock" class="card diagnosis-placeholder">
      <div class="placeholder-icon">↗</div>
      <strong>切换一只股票开始诊断</strong>
      <p>识别到东方财富当前股票后，评分卡会自动刷新。</p>
    </section>

    <p v-if="error && !settingsOpen" class="error-message">{{ error }}</p>

    <footer>P1 使用模拟数据验证产品闭环，不构成任何投资建议</footer>

    <Transition name="settings">
      <div
        v-if="settingsOpen"
        class="settings-layer"
        @click.self="settingsOpen = false"
      >
        <aside
          id="settings-drawer"
          class="settings-drawer"
          role="dialog"
          aria-modal="true"
          aria-label="联动设置"
        >
          <div class="settings-header">
            <div>
              <p class="eyebrow">COMPANION SETTINGS</p>
              <h2>联动设置</h2>
            </div>
            <button
              class="icon-button"
              aria-label="关闭设置"
              @click="settingsOpen = false"
            >
              <svg viewBox="0 0 24 24" aria-hidden="true">
                <path d="m6.8 5.4 11.8 11.8-1.4 1.4L5.4 6.8l1.4-1.4Z" />
                <path d="M17.2 5.4 5.4 17.2l1.4 1.4L18.6 6.8l-1.4-1.4Z" />
              </svg>
            </button>
          </div>

          <section class="settings-section">
            <div class="section-heading">
              <div>
                <div class="card-label">窗口跟随</div>
                <strong>实时贴靠并同步高度</strong>
              </div>
              <button
                class="switch"
                :class="{ enabled: context?.followEnabled }"
                :aria-pressed="context?.followEnabled"
                :disabled="actionLoading"
                @click="
                  runAction(() => setFollowEnabled(!context?.followEnabled))
                "
              >
                <span />
              </button>
            </div>
            <p class="muted">
              以约 60Hz 跟随东方财富窗口，窗口层级随前后台状态变化。
            </p>
          </section>

          <section class="settings-section">
            <div class="card-label">手动降级</div>
            <div class="manual-grid">
              <label>
                <span>股票代码</span>
                <input
                  v-model="manualCode"
                  maxlength="6"
                  inputmode="numeric"
                  placeholder="例如 600519"
                />
              </label>
              <label>
                <span>名称（可选）</span>
                <input
                  v-model="manualName"
                  maxlength="20"
                  placeholder="贵州茅台"
                />
              </label>
            </div>
            <div class="action-row">
              <button
                class="secondary-button"
                :disabled="actionLoading"
                @click="submitManualStock"
              >
                使用手动代码
              </button>
              <button
                v-if="context?.mode === 'manual'"
                class="text-button"
                :disabled="actionLoading"
                @click="runAction(clearManualStock)"
              >
                恢复自动
              </button>
            </div>
          </section>

          <section class="settings-section">
            <div class="section-heading">
              <div>
                <div class="card-label">本地诊断服务</div>
                <strong>{{ serviceLabel }}</strong>
              </div>
              <span
                class="service-dot"
                :class="quantStatus?.state || 'starting'"
              />
            </div>
            <p class="muted">{{ quantStatus?.message }}</p>
            <button
              class="secondary-button service-restart"
              @click="restartService"
            >
              重启本地服务
            </button>
          </section>

          <section class="settings-section boundary-section">
            <div class="card-label">P1 数据边界</div>
            <p class="muted">
              当前仅返回确定性的模拟评分，不采集东方财富行情、不读取账户、不训练模型，也不执行任何交易。
            </p>
          </section>

          <p v-if="error" class="error-message">{{ error }}</p>
        </aside>
      </div>
    </Transition>
  </main>
</template>
