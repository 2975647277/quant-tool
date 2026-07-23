<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import {
  clearManualStock,
  getEastmoneyContext,
  onEastmoneyContext,
  refreshEastmoneyContext,
  requestAccessibilityPermission,
  setFollowEnabled,
  setManualStock,
} from "./bridge";
import type { EastmoneyContext } from "./types";

const context = ref<EastmoneyContext | null>(null);
const loading = ref(false);
const error = ref("");
const manualCode = ref("");
const manualName = ref("");
const settingsOpen = ref(false);
let unlisten: (() => void) | undefined;

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

const formattedTime = computed(() => {
  if (!context.value?.updatedAtMs) return "尚未刷新";
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
  }).format(new Date(context.value.updatedAtMs));
});

async function runAction(action: () => Promise<EastmoneyContext>) {
  loading.value = true;
  error.value = "";
  try {
    context.value = await action();
  } catch (cause) {
    error.value = String(cause);
  } finally {
    loading.value = false;
  }
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

onMounted(async () => {
  context.value = await getEastmoneyContext();
  unlisten = await onEastmoneyContext((nextContext) => {
    context.value = nextContext;
  });
});

onBeforeUnmount(() => unlisten?.());
</script>

<template>
  <main class="shell">
    <header class="hero">
      <div>
        <p class="eyebrow">QUANT COMPANION · P0</p>
        <h1>东方财富联动</h1>
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
      <div class="card-label">当前股票</div>
      <template v-if="context?.stock">
        <div class="stock-heading">
          <strong>{{ context.stock.name || "未命名股票" }}</strong>
          <span>{{ context.stock.code }}</span>
        </div>
      </template>
      <div v-else class="empty-stock">等待东方财富中的股票变化</div>
      <p class="context-message">{{ context?.message || "正在初始化…" }}</p>
      <div class="meta-row">
        <span>更新于 {{ formattedTime }}</span>
        <span>观察器 {{ context?.observerActive ? "已启用" : "轮询兜底" }}</span>
      </div>
    </section>

    <section
      v-if="context && !context.permissionGranted"
      class="notice permission-notice"
    >
      <div>
        <strong>需要无障碍权限</strong>
        <p>权限只用于读取当前股票和窗口位置，不执行点击或交易。</p>
      </div>
      <button
        class="primary-button"
        :disabled="loading"
        @click="runAction(requestAccessibilityPermission)"
      >
        请求权限
      </button>
    </section>

    <section class="validation-card">
      <div class="validation-title">
        <span>P0 验证范围</span>
        <button
          class="refresh-button"
          :disabled="loading"
          @click="runAction(refreshEastmoneyContext)"
        >
          {{ loading ? "刷新中" : "立即刷新" }}
        </button>
      </div>
      <ul>
        <li :class="{ done: context?.running }">检测东方财富进程</li>
        <li :class="{ done: context?.permissionGranted }">只读无障碍访问</li>
        <li :class="{ done: context?.stock }">识别股票代码</li>
        <li :class="{ done: context?.frame }">获取窗口位置</li>
      </ul>
    </section>

    <p v-if="error && !settingsOpen" class="error-message">{{ error }}</p>

    <footer>
      本阶段不采集行情、不训练模型、不读取账户、不执行交易
    </footer>

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
                :disabled="loading"
                @click="
                  runAction(() => setFollowEnabled(!context?.followEnabled))
                "
              >
                <span />
              </button>
            </div>
            <p class="muted">
              以 60Hz 跟随东方财富窗口；窗口层级随东方财富前后台状态变化。
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
                :disabled="loading"
                @click="submitManualStock"
              >
                使用手动代码
              </button>
              <button
                v-if="context?.mode === 'manual'"
                class="text-button"
                :disabled="loading"
                @click="runAction(clearManualStock)"
              >
                恢复自动
              </button>
            </div>
          </section>

          <p v-if="error" class="error-message">{{ error }}</p>
        </aside>
      </div>
    </Transition>
  </main>
</template>
