<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from "vue";
import {
  clearManualStock,
  getEastmoneyContext,
  getQuantServiceStatus,
  getStockResearch,
  onEastmoneyContext,
  onQuantServiceStatus,
  refreshEastmoneyContext,
  requestAccessibilityPermission,
  restartQuantService,
  setFollowEnabled,
  setManualStock,
} from "./bridge";
import type {
  EastmoneyContext,
  QuantServiceStatus,
  StockResearchView,
} from "./types";

const context = ref<EastmoneyContext | null>(null);
const quantStatus = ref<QuantServiceStatus | null>(null);
const research = ref<StockResearchView | null>(null);
const actionLoading = ref(false);
const researchLoading = ref(false);
const error = ref("");
const researchError = ref("");
const manualCode = ref("");
const manualName = ref("");
const settingsOpen = ref(false);
let unlistenContext: (() => void) | undefined;
let unlistenQuantStatus: (() => void) | undefined;
let researchRequestId = 0;

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
      return "研究服务已连接";
    case "unavailable":
      return "研究服务恢复中";
    default:
      return "研究服务启动中";
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
  "--score": `${Math.round(
    (research.value?.topGroupDailyPositiveExcessRate ?? 0) * 100,
  )}%`,
}));

const coverageTone = computed(() => {
  switch (research.value?.coverage) {
    case "selected_top20":
      return "low";
    case "covered_not_selected":
      return "medium";
    default:
      return "high";
  }
});

const signalDateLabel = computed(() => {
  if (!research.value?.signalDate) return "未知日期";
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date(`${research.value.signalDate}T00:00:00+08:00`));
});

function percent(value: number, digits = 1) {
  return `${(value * 100).toFixed(digits)}%`;
}

const admissionLabels: Record<string, string> = {
  "rank_ic_below_0.02": "Rank IC 低于内部门槛",
  "icir_below_0.8": "ICIR 低于内部门槛",
  top_group_excess_not_positive: "Top 组平均超额收益未转正",
  max_drawdown_above_15_percent: "Top 组最大回撤超过 15%",
  current_constituent_universe_has_survivorship_bias:
    "当前成分股回测存在幸存者偏差",
  historical_financial_revision_chain_unavailable: "缺少完整财务历史修订链",
  broad_index_excess_label_used_until_historical_industry_membership_is_available:
    "缺少历史行业成员，暂用沪深300基准",
};

function admissionLabel(reason: string) {
  return admissionLabels[reason] ?? reason;
}

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

async function loadResearch() {
  const stock = context.value?.stock;
  const requestId = ++researchRequestId;
  research.value = null;
  researchError.value = "";
  researchLoading.value = false;
  if (!stock || quantStatus.value?.state !== "ready") return;

  researchLoading.value = true;
  try {
    const result = await getStockResearch(stock.code, stock.name);
    if (requestId === researchRequestId) research.value = result;
  } catch (cause) {
    if (requestId === researchRequestId) {
      researchError.value = String(cause);
    }
  } finally {
    if (requestId === researchRequestId) researchLoading.value = false;
  }
}

async function restartService() {
  researchError.value = "";
  research.value = null;
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
    const stockKey = stock ? `${stock.code}:${stock.name}` : "";
    return `${stockKey}:${quantStatus.value?.state ?? ""}`;
  },
  () => void loadResearch(),
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
      quantStatus.value = nextStatus;
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
        <p class="eyebrow">QUANT · P2/P3</p>
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

    <section v-if="research" class="card diagnosis-card">
      <div class="diagnosis-heading">
        <div>
          <div class="card-label">真实样本外研究 · 非实时信号</div>
          <h2>LightGBM 验证快照</h2>
        </div>
        <div class="score-ring" :style="scoreStyle">
          <strong>{{
            Math.round(research.topGroupDailyPositiveExcessRate * 100)
          }}</strong>
          <span>跑赢率%</span>
        </div>
      </div>

      <div class="metric-grid">
        <div>
          <span>当前股票覆盖</span>
          <strong>{{ research.coverageLabel }}</strong>
        </div>
        <div>
          <span>样本外 Rank IC</span>
          <strong>{{ research.rankIc.toFixed(3) }}</strong>
        </div>
        <div>
          <span>Top组平均超额</span>
          <strong
            :class="{ positive: research.topGroupMeanExcessReturn >= 0 }"
          >
            {{ research.topGroupMeanExcessReturn >= 0 ? "+" : ""
            }}{{ percent(research.topGroupMeanExcessReturn, 2) }}
          </strong>
        </div>
        <div>
          <span>Top组最大回撤</span>
          <strong class="negative">
            -{{ percent(research.topGroupMaxDrawdown, 2) }}
          </strong>
        </div>
      </div>

      <div class="risk-row">
        <span>模型准入</span>
        <strong
          class="risk-badge"
          :class="research.eligibleForDefault ? 'low' : 'high'"
        >
          {{ research.eligibleForDefault ? "已通过" : "未通过" }}
        </strong>
      </div>

      <div class="research-coverage">
        <div class="card-label">当前股票</div>
        <div class="coverage-title">
          <strong>{{ research.coverageLabel }}</strong>
          <span class="risk-badge" :class="coverageTone">
            {{
              research.coverage === "selected_top20"
                ? `第 ${research.top20Rank} 名`
                : research.coverage === "covered_not_selected"
                  ? "已覆盖"
                  : "未覆盖"
            }}
          </span>
        </div>
        <p v-if="research.coverage === 'selected_top20'">
          该股票出现在 {{ signalDateLabel }} 的历史末期 Top 20
          快照中；这不是今天的推荐。
        </p>
        <p v-else-if="research.coverage === 'covered_not_selected'">
          该股票属于30只研究样本，但未进入 {{ signalDateLabel }} 的历史 Top 20。
        </p>
        <p v-else>
          当前股票不在这次30只研究样本内，因此不生成个股分数或上涨概率。
        </p>
      </div>

      <div class="explanation-panel">
        <div class="card-label">为什么还不能用于实盘</div>
        <p
          v-for="reason in research.admissionReasons.slice(0, 3)"
          :key="reason"
        >
          {{ admissionLabel(reason) }}
        </p>
      </div>

      <div class="diagnosis-meta">
        <span>{{ research.modelVersion }}</span>
        <span>{{ research.dataVersion }}</span>
      </div>
    </section>

    <section
      v-else-if="researchLoading"
      class="card diagnosis-card diagnosis-loading"
      aria-label="真实研究加载中"
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
        <strong>真实研究快照加载失败</strong>
        <p>{{ researchError || "未能取得 P2/P3 真实研究结果" }}</p>
      </div>
      <button class="secondary-button" @click="loadResearch">重新加载</button>
    </section>

    <section v-else-if="!context?.stock" class="card diagnosis-placeholder">
      <div class="placeholder-icon">↗</div>
      <strong>切换一只股票查看研究覆盖</strong>
      <p>识别后会显示该股票是否在 P2/P3 真实研究样本中。</p>
    </section>

    <p v-if="error && !settingsOpen" class="error-message">{{ error }}</p>

    <footer>P2/P3 真实历史研究已连接；非实时信号，不构成任何投资建议</footer>

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
                <div class="card-label">本地研究服务</div>
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
            <div class="card-label">P2/P3 数据边界</div>
            <p class="muted">
              当前展示真实历史样本外验证结果，不是当日预测；研究池只有30只样本，未通过准入的模型不生成个股概率，也不执行任何交易。
            </p>
          </section>

          <p v-if="error" class="error-message">{{ error }}</p>
        </aside>
      </div>
    </Transition>
  </main>
</template>
