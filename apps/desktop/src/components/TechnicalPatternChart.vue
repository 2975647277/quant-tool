<script setup lang="ts">
import { computed, ref, watch } from "vue";
import type {
  KlinePoint,
  StockChartView,
  TechnicalPattern,
  TechnicalPatternAnchor,
  TechnicalPatternLine,
} from "@quant-tool/contracts";

const props = defineProps<{
  chart: StockChartView;
}>();

const period = ref<30 | 60 | 120>(60);
const selectedPatternIndex = ref(0);
const hoverIndex = ref<number | null>(null);

const width = 360;
const left = 10;
const right = 45;
const priceTop = 42;
const priceBottom = 264;
const volumeTop = 284;
const volumeBottom = 326;
const macdTop = 350;
const macdBottom = 390;
const plotWidth = width - left - right;

watch(
  () => props.chart.dataVersion + props.chart.stock.code,
  () => {
    selectedPatternIndex.value = 0;
    hoverIndex.value = null;
  },
);

const points = computed(() => props.chart.points.slice(-period.value));
const activePattern = computed<TechnicalPattern | null>(
  () => props.chart.patterns[selectedPatternIndex.value] ?? null,
);
const dateIndex = computed(
  () =>
    new Map(
      points.value.map((point, index) => [point.tradeDate, index] as const),
    ),
);
const displayedPoint = computed(
  () =>
    points.value[hoverIndex.value ?? points.value.length - 1] ??
    props.chart.points.at(-1),
);
const latestPoint = computed(() => props.chart.points.at(-1));
const structureItems = computed(() => {
  if (activePattern.value?.anchors.length) {
    return activePattern.value.anchors.map((anchor) => ({
      label: anchor.label,
      value: anchor.price,
      date: anchor.tradeDate,
    }));
  }
  return (activePattern.value?.lines ?? []).map((line) => ({
    label: line.label,
    value: line.endPrice,
    date: line.endDate,
  }));
});

const priceBounds = computed(() => {
  const values = points.value.flatMap((point) => [
    point.lowPrice,
    point.highPrice,
    point.ma5 ?? point.closePrice,
    point.ma20 ?? point.closePrice,
    point.ma60 ?? point.closePrice,
  ]);
  for (const line of activePattern.value?.lines ?? []) {
    values.push(line.startPrice, line.endPrice);
  }
  for (const anchor of activePattern.value?.anchors ?? []) {
    values.push(anchor.price);
  }
  const minimum = Math.min(...values);
  const maximum = Math.max(...values);
  const padding = Math.max((maximum - minimum) * 0.08, maximum * 0.005);
  return { minimum: minimum - padding, maximum: maximum + padding };
});

const maxVolume = computed(() =>
  Math.max(...points.value.map((point) => point.volumeShares), 1),
);
const maxMacd = computed(() =>
  Math.max(
    ...points.value.map((point) => Math.abs(point.macdHistogram ?? 0)),
    0.001,
  ),
);
const candleWidth = computed(() =>
  Math.max(1.4, Math.min(5.2, (plotWidth / points.value.length) * 0.62)),
);
const gridPrices = computed(() => {
  const { minimum, maximum } = priceBounds.value;
  return [0, 0.25, 0.5, 0.75, 1].map(
    (ratio) => maximum - (maximum - minimum) * ratio,
  );
});

function x(index: number) {
  return left + ((index + 0.5) / points.value.length) * plotWidth;
}

function priceY(value: number) {
  const { minimum, maximum } = priceBounds.value;
  return (
    priceTop +
    ((maximum - value) / Math.max(maximum - minimum, 1e-9)) *
      (priceBottom - priceTop)
  );
}

function volumeY(value: number) {
  return (
    volumeBottom -
    (value / maxVolume.value) * (volumeBottom - volumeTop)
  );
}

function macdY(value: number) {
  const center = (macdTop + macdBottom) / 2;
  return center - (value / maxMacd.value) * ((macdBottom - macdTop) / 2);
}

function movingAveragePath(key: "ma5" | "ma20" | "ma60") {
  let path = "";
  let drawing = false;
  points.value.forEach((point, index) => {
    const value = point[key];
    if (value == null) {
      drawing = false;
      return;
    }
    path += `${drawing ? "L" : "M"}${x(index).toFixed(2)},${priceY(value).toFixed(2)} `;
    drawing = true;
  });
  return path.trim();
}

function patternX(tradeDate: string) {
  const exact = dateIndex.value.get(tradeDate);
  if (exact != null) return x(exact);
  if (tradeDate < points.value[0].tradeDate) return left;
  return left + plotWidth;
}

function patternLineCoordinates(line: TechnicalPatternLine) {
  return {
    x1: patternX(line.startDate),
    y1: priceY(line.startPrice),
    x2: patternX(line.endDate),
    y2: priceY(line.endPrice),
  };
}

function anchorCoordinates(anchor: TechnicalPatternAnchor) {
  return {
    x: patternX(anchor.tradeDate),
    y: priceY(anchor.price),
  };
}

function candleTone(point: KlinePoint) {
  return point.closePrice >= point.openPrice ? "up" : "down";
}

function money(value: number | null | undefined) {
  return value == null ? "--" : value.toFixed(2);
}

function indicator(value: number | null | undefined, digits = 2) {
  return value == null ? "--" : value.toFixed(digits);
}

function shortDate(value: string) {
  return value.slice(5).replace("-", "/");
}

function directionLabel(pattern: TechnicalPattern) {
  switch (pattern.direction) {
    case "bullish":
      return "偏多结构";
    case "bearish":
      return "偏空结构";
    default:
      return "整理结构";
  }
}

function confirmationLabel(pattern: TechnicalPattern) {
  switch (pattern.kind) {
    case "double_bottom":
      return pattern.status === "已确认"
        ? "收盘已站上颈线，W形态获得确认"
        : "仍需收盘突破颈线，当前只属于形成阶段";
    case "double_top":
      return pattern.status === "已确认"
        ? "收盘已跌破颈线，M形态获得确认"
        : "仍需收盘跌破颈线，当前只属于形成阶段";
    case "bullish_breakout":
      return "收盘突破20日压力，继续观察能否回踩不破";
    case "bearish_breakdown":
      return "收盘跌破20日支撑，继续观察能否快速收复";
    case "ascending_channel":
      return "高低点同步抬升，跌破趋势支撑后结构失效";
    case "descending_channel":
      return "高低点同步下移，突破趋势压力后结构失效";
    default:
      return "价格仍在箱体内，等待放量突破支撑或压力";
  }
}

function handlePointerMove(event: PointerEvent) {
  const target = event.currentTarget as SVGElement;
  const rect = target.getBoundingClientRect();
  if (!rect.width) return;
  const localX = ((event.clientX - rect.left) / rect.width) * width;
  const ratio = Math.min(1, Math.max(0, (localX - left) / plotWidth));
  hoverIndex.value = Math.min(
    points.value.length - 1,
    Math.max(0, Math.floor(ratio * points.value.length)),
  );
}
</script>

<template>
  <section class="technical-chart">
    <div class="chart-heading">
      <div>
        <div class="card-label">真实日线结构分析</div>
        <div class="trend-title">
          <h2>K线技术形态</h2>
          <span class="trend-badge" :class="chart.trend">
            {{ chart.trendLabel }}
          </span>
        </div>
      </div>
      <div class="period-switch" aria-label="K线显示周期">
        <button :class="{ active: period === 30 }" @click="period = 30">
          30
        </button>
        <button :class="{ active: period === 60 }" @click="period = 60">
          60
        </button>
        <button :class="{ active: period === 120 }" @click="period = 120">
          120日
        </button>
      </div>
    </div>

    <p class="trend-summary">{{ chart.trendSummary }}</p>

    <div class="structure-overview">
      <div>
        <span>当前收盘</span>
        <strong>{{ money(latestPoint?.closePrice) }}</strong>
      </div>
      <div>
        <span>主要形态</span>
        <strong>{{ activePattern?.label ?? "暂未识别" }}</strong>
      </div>
      <div>
        <span>20日支撑</span>
        <strong>{{ money(chart.supportPrice) }}</strong>
      </div>
      <div>
        <span>20日压力</span>
        <strong>{{ money(chart.resistancePrice) }}</strong>
      </div>
    </div>

    <div v-if="chart.patterns.length" class="pattern-tabs">
      <button
        v-for="(pattern, index) in chart.patterns"
        :key="`${pattern.kind}-${index}`"
        :class="[
          pattern.direction,
          { active: selectedPatternIndex === index },
        ]"
        @click="selectedPatternIndex = index"
      >
        <span>{{ pattern.label }}</span>
        <small>{{ pattern.status }}</small>
      </button>
    </div>

    <div v-if="activePattern" class="pattern-callout">
      <div class="pattern-callout-title">
        <div>
          <span>当前查看</span>
          <strong>{{ activePattern.label }}</strong>
        </div>
        <b :class="activePattern.direction">
          {{ directionLabel(activePattern) }}
        </b>
      </div>
      <p>{{ activePattern.summary }}</p>
      <div class="confirmation-row">
        <span>{{ activePattern.status }}</span>
        <strong>{{ confirmationLabel(activePattern) }}</strong>
      </div>
    </div>

    <div v-if="activePattern && structureItems.length" class="structure-detail">
      <div class="structure-detail-heading">
        <div>
          <span>形态结构路径</span>
          <strong>关键节点与价格</strong>
        </div>
        <b>{{ Math.round(activePattern.confidence * 100) }}% 规则匹配</b>
      </div>
      <div class="structure-steps">
        <template v-for="(item, index) in structureItems" :key="`${item.label}-${item.date}`">
          <div class="structure-step">
            <i>{{ index + 1 }}</i>
            <div>
              <span>{{ item.label }}</span>
              <strong>{{ money(item.value) }}</strong>
              <small>{{ shortDate(item.date) }}</small>
            </div>
          </div>
          <span v-if="index < structureItems.length - 1" class="step-arrow">→</span>
        </template>
      </div>
    </div>

    <div class="chart-readout">
      <strong>{{
        displayedPoint ? shortDate(displayedPoint.tradeDate) : "--"
      }}</strong>
      <span>开 {{ money(displayedPoint?.openPrice) }}</span>
      <span>高 {{ money(displayedPoint?.highPrice) }}</span>
      <span>低 {{ money(displayedPoint?.lowPrice) }}</span>
      <span>收 {{ money(displayedPoint?.closePrice) }}</span>
    </div>
    <div class="average-legend">
      <span class="ma5">MA5 {{ money(displayedPoint?.ma5) }}</span>
      <span class="ma20">MA20 {{ money(displayedPoint?.ma20) }}</span>
      <span class="ma60">MA60 {{ money(displayedPoint?.ma60) }}</span>
    </div>

    <svg
      class="kline-svg"
      :viewBox="`0 0 ${width} 402`"
      role="img"
      :aria-label="`${chart.stock.name} K线和${activePattern?.label ?? '技术形态'}`"
      @pointermove="handlePointerMove"
      @pointerleave="hoverIndex = null"
    >
      <defs>
        <linearGradient id="price-fade" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#15304a" stop-opacity="0.28" />
          <stop offset="100%" stop-color="#071421" stop-opacity="0" />
        </linearGradient>
      </defs>

      <rect
        :x="left"
        :y="priceTop"
        :width="plotWidth"
        :height="priceBottom - priceTop"
        fill="url(#price-fade)"
      />

      <g class="price-grid">
        <template v-for="price in gridPrices" :key="price">
          <line
            :x1="left"
            :x2="left + plotWidth"
            :y1="priceY(price)"
            :y2="priceY(price)"
          />
          <text
            :x="left + plotWidth + 4"
            :y="priceY(price) + 3"
          >{{ price.toFixed(1) }}</text>
        </template>
      </g>

      <g class="candles">
        <g
          v-for="(point, index) in points"
          :key="point.tradeDate"
          :class="candleTone(point)"
        >
          <line
            :x1="x(index)"
            :x2="x(index)"
            :y1="priceY(point.highPrice)"
            :y2="priceY(point.lowPrice)"
          />
          <rect
            :x="x(index) - candleWidth / 2"
            :y="Math.min(priceY(point.openPrice), priceY(point.closePrice))"
            :width="candleWidth"
            :height="
              Math.max(
                1.2,
                Math.abs(priceY(point.openPrice) - priceY(point.closePrice)),
              )
            "
          />
          <rect
            class="volume-bar"
            :x="x(index) - candleWidth / 2"
            :y="volumeY(point.volumeShares)"
            :width="candleWidth"
            :height="volumeBottom - volumeY(point.volumeShares)"
          />
          <rect
            class="macd-bar"
            :x="x(index) - candleWidth / 2"
            :y="
              point.macdHistogram != null && point.macdHistogram >= 0
                ? macdY(point.macdHistogram)
                : macdY(0)
            "
            :width="candleWidth"
            :height="
              Math.max(
                0.7,
                Math.abs(macdY(point.macdHistogram ?? 0) - macdY(0)),
              )
            "
          />
        </g>
      </g>

      <path class="ma-line ma5-line" :d="movingAveragePath('ma5')" />
      <path class="ma-line ma20-line" :d="movingAveragePath('ma20')" />
      <path class="ma-line ma60-line" :d="movingAveragePath('ma60')" />

      <g
        v-if="activePattern"
        class="pattern-overlay"
        :class="activePattern.direction"
      >
        <g
          v-for="line in activePattern.lines"
          :key="`${line.label}-${line.startDate}`"
        >
          <line v-bind="patternLineCoordinates(line)" />
          <text
            :x="patternLineCoordinates(line).x2 - 3"
            :y="patternLineCoordinates(line).y2 - 5"
            text-anchor="end"
          >{{ line.label }}</text>
        </g>
        <g
          v-for="anchor in activePattern.anchors"
          :key="`${anchor.label}-${anchor.tradeDate}`"
          class="pattern-anchor"
        >
          <circle
            :cx="anchorCoordinates(anchor).x"
            :cy="anchorCoordinates(anchor).y"
            r="3.2"
          />
          <text
            :x="anchorCoordinates(anchor).x"
            :y="anchorCoordinates(anchor).y - 7"
            text-anchor="middle"
          >{{ anchor.label }}</text>
        </g>
      </g>

      <line
        class="panel-separator"
        :x1="left"
        :x2="left + plotWidth"
        :y1="volumeTop - 6"
        :y2="volumeTop - 6"
      />
      <text class="panel-label" :x="left" :y="volumeTop - 9">VOL</text>
      <line
        class="macd-zero"
        :x1="left"
        :x2="left + plotWidth"
        :y1="macdY(0)"
        :y2="macdY(0)"
      />
      <text class="panel-label" :x="left" :y="macdTop - 5">MACD</text>

      <g v-if="hoverIndex != null" class="crosshair">
        <line
          :x1="x(hoverIndex)"
          :x2="x(hoverIndex)"
          :y1="priceTop"
          :y2="macdBottom"
        />
        <circle
          :cx="x(hoverIndex)"
          :cy="priceY(points[hoverIndex].closePrice)"
          r="3"
        />
      </g>

      <g class="date-axis">
        <template
          v-for="index in [0, Math.floor((points.length - 1) / 2), points.length - 1]"
          :key="index"
        >
          <text :x="x(index)" y="400" text-anchor="middle">
            {{ shortDate(points[index].tradeDate) }}
          </text>
        </template>
      </g>
    </svg>

    <div class="indicator-strip">
      <div>
        <span>RSI14</span>
        <strong>{{ indicator(chart.latestRsi14, 1) }}</strong>
      </div>
      <div>
        <span>MACD柱</span>
        <strong
          :class="{
            positive: (chart.latestMacdHistogram ?? 0) >= 0,
            negative: (chart.latestMacdHistogram ?? 0) < 0,
          }"
        >
          {{ indicator(chart.latestMacdHistogram, 3) }}
        </strong>
      </div>
      <div>
        <span>20日支撑</span>
        <strong>{{ money(chart.supportPrice) }}</strong>
      </div>
      <div>
        <span>20日压力</span>
        <strong>{{ money(chart.resistancePrice) }}</strong>
      </div>
    </div>

    <p class="chart-disclaimer">{{ chart.disclaimer }}</p>
  </section>
</template>

<style scoped>
.technical-chart {
  overflow: hidden;
  border: 1px solid rgb(107 155 204 / 22%);
  border-radius: 17px;
  padding: 17px 14px 15px;
  background:
    radial-gradient(circle at 90% 0%, rgb(49 119 255 / 16%), transparent 32%),
    linear-gradient(165deg, rgb(12 31 52 / 96%), rgb(6 18 31 / 96%));
  box-shadow:
    0 16px 38px rgb(0 0 0 / 16%),
    inset 0 1px rgb(255 255 255 / 4%);
}

.chart-heading,
.trend-title,
.chart-readout {
  display: flex;
  align-items: center;
}

.chart-heading {
  justify-content: space-between;
  gap: 10px;
}

.card-label {
  margin: 0 0 7px;
  color: #7691ad;
  font-size: 10px;
  font-weight: 700;
  letter-spacing: 0.11em;
  text-transform: uppercase;
}

.trend-title {
  gap: 8px;
}

h2 {
  margin: 0;
  color: #edf6ff;
  font-size: 19px;
  letter-spacing: -0.035em;
}

.trend-badge {
  border-radius: 999px;
  padding: 4px 8px;
  font-size: 10px;
  font-weight: 700;
}

.trend-badge.bullish {
  background: rgb(255 91 112 / 12%);
  color: #ff8a9b;
}

.trend-badge.bearish {
  background: rgb(49 214 160 / 12%);
  color: #63ddb6;
}

.trend-badge.sideways {
  background: rgb(245 175 66 / 12%);
  color: #efbe6c;
}

.period-switch {
  display: flex;
  border: 1px solid #223b54;
  border-radius: 8px;
  padding: 3px;
  background: #071522;
}

.period-switch button,
.pattern-tabs button {
  border: 0;
  color: #66809a;
  font: inherit;
  cursor: pointer;
}

.period-switch button {
  border-radius: 6px;
  padding: 6px 7px;
  background: transparent;
  font-size: 10px;
  font-weight: 650;
}

.period-switch button.active {
  background: #205487;
  color: #f0f7ff;
}

.trend-summary {
  margin: 10px 0 0;
  color: #879eb5;
  font-size: 11px;
  line-height: 1.6;
}

.structure-overview {
  display: grid;
  margin-top: 13px;
  border: 1px solid rgb(105 151 194 / 18%);
  border-radius: 12px;
  grid-template-columns: 1fr 1fr;
  overflow: hidden;
}

.structure-overview > div {
  min-width: 0;
  padding: 11px 12px;
  background: rgb(6 19 33 / 48%);
}

.structure-overview > div:nth-child(odd) {
  border-right: 1px solid rgb(105 151 194 / 15%);
}

.structure-overview > div:nth-child(-n + 2) {
  border-bottom: 1px solid rgb(105 151 194 / 15%);
}

.structure-overview span,
.structure-overview strong {
  display: block;
}

.structure-overview span {
  color: #678099;
  font-size: 9px;
}

.structure-overview strong {
  margin-top: 5px;
  overflow: hidden;
  color: #dce9f6;
  font-size: 12px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.pattern-tabs {
  display: flex;
  gap: 7px;
  margin-top: 13px;
  overflow-x: auto;
  scrollbar-width: none;
}

.pattern-tabs::-webkit-scrollbar {
  display: none;
}

.pattern-tabs button {
  display: grid;
  gap: 2px;
  flex: 0 0 auto;
  border: 1px solid #28445f;
  border-radius: 10px;
  padding: 7px 10px;
  background: rgb(8 21 34 / 78%);
  font-size: 10px;
  text-align: left;
}

.pattern-tabs button span {
  font-weight: 700;
}

.pattern-tabs button small {
  color: #647d95;
  font-size: 9px;
}

.pattern-tabs button.active.bullish {
  border-color: rgb(255 91 112 / 40%);
  background: rgb(255 91 112 / 12%);
  color: #ff9aaa;
}

.pattern-tabs button.active.bearish {
  border-color: rgb(49 214 160 / 40%);
  background: rgb(49 214 160 / 12%);
  color: #79e2bf;
}

.pattern-tabs button.active.sideways {
  border-color: rgb(245 175 66 / 40%);
  background: rgb(245 175 66 / 12%);
  color: #efbe6c;
}

.pattern-callout {
  margin-top: 10px;
  border: 1px solid rgb(80 136 194 / 24%);
  border-radius: 12px;
  padding: 12px;
  background: rgb(18 47 76 / 48%);
}

.pattern-callout-title {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.pattern-callout-title > div span,
.pattern-callout-title > div strong {
  display: block;
}

.pattern-callout-title > div span {
  color: #708aa3;
  font-size: 9px;
}

.pattern-callout-title > div strong {
  margin-top: 4px;
  color: #e1edf8;
  font-size: 13px;
}

.pattern-callout-title > b {
  border-radius: 999px;
  padding: 5px 8px;
  font-size: 9px;
}

.pattern-callout-title > b.bullish {
  background: rgb(255 91 112 / 12%);
  color: #ff9cac;
}

.pattern-callout-title > b.bearish {
  background: rgb(49 214 160 / 12%);
  color: #76dfbd;
}

.pattern-callout-title > b.sideways {
  background: rgb(245 175 66 / 12%);
  color: #efbe6c;
}

.pattern-callout p {
  margin: 9px 0 0;
  color: #93a9bd;
  font-size: 11px;
  line-height: 1.55;
}

.confirmation-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 10px;
  border-top: 1px solid rgb(107 150 190 / 15%);
  padding-top: 9px;
}

.confirmation-row span {
  flex: 0 0 auto;
  border-radius: 999px;
  padding: 3px 7px;
  background: #183b5c;
  color: #9cc4ea;
  font-size: 9px;
}

.confirmation-row strong {
  color: #a9bed2;
  font-size: 10px;
  font-weight: 550;
  line-height: 1.45;
}

.structure-detail {
  margin-top: 10px;
  border: 1px solid rgb(105 151 194 / 18%);
  border-radius: 12px;
  padding: 12px;
  background: rgb(5 17 30 / 55%);
}

.structure-detail-heading {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
}

.structure-detail-heading span,
.structure-detail-heading strong {
  display: block;
}

.structure-detail-heading span {
  color: #667f98;
  font-size: 9px;
}

.structure-detail-heading strong {
  margin-top: 3px;
  color: #c9d9e9;
  font-size: 11px;
}

.structure-detail-heading b {
  color: #7fa7cd;
  font-size: 9px;
  font-weight: 650;
}

.structure-steps {
  display: flex;
  align-items: center;
  gap: 5px;
  margin-top: 12px;
  overflow-x: auto;
  padding-bottom: 2px;
  scrollbar-width: none;
}

.structure-steps::-webkit-scrollbar {
  display: none;
}

.structure-step {
  display: flex;
  min-width: 80px;
  align-items: flex-start;
  gap: 7px;
}

.structure-step i {
  display: grid;
  width: 20px;
  height: 20px;
  flex: 0 0 auto;
  place-items: center;
  border: 1px solid #2c6599;
  border-radius: 50%;
  background: #113657;
  color: #a9d4f8;
  font-size: 9px;
  font-style: normal;
  font-weight: 700;
}

.structure-step div span,
.structure-step div strong,
.structure-step div small {
  display: block;
}

.structure-step div span {
  color: #8299af;
  font-size: 9px;
}

.structure-step div strong {
  margin-top: 3px;
  color: #e0ebf6;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
}

.structure-step div small {
  margin-top: 2px;
  color: #506a82;
  font-size: 9px;
}

.step-arrow {
  flex: 0 0 auto;
  color: #3e668b;
  font-size: 13px;
}

.chart-readout {
  display: grid;
  margin-top: 14px;
  color: #91a7bb;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
  grid-template-columns: 1.2fr repeat(4, 1fr);
}

.chart-readout strong {
  color: #d8e7f5;
}

.average-legend {
  display: flex;
  gap: 13px;
  margin-top: 7px;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9px;
}

.average-legend .ma5 {
  color: #f1bf58;
}

.average-legend .ma20 {
  color: #5aabff;
}

.average-legend .ma60 {
  color: #bd84ff;
}

.kline-svg {
  display: block;
  width: 100%;
  margin-top: 5px;
  overflow: visible;
  touch-action: none;
}

.price-grid line,
.panel-separator,
.macd-zero {
  stroke: rgb(98 129 159 / 13%);
  stroke-width: 0.8;
  vector-effect: non-scaling-stroke;
}

.price-grid text,
.panel-label,
.date-axis text {
  fill: #6e879e;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 9.5px;
}

.candles line,
.candles rect {
  vector-effect: non-scaling-stroke;
}

.candles .up line,
.candles .up rect {
  fill: #ff657a;
  stroke: #ff657a;
}

.candles .down line,
.candles .down rect {
  fill: #31c99b;
  stroke: #31c99b;
}

.candles .volume-bar,
.candles .macd-bar {
  opacity: 0.48;
  stroke-width: 0;
}

.candles .macd-bar {
  opacity: 0.72;
}

.ma-line {
  fill: none;
  stroke-width: 1.25;
  vector-effect: non-scaling-stroke;
}

.ma5-line {
  stroke: #f1bf58;
}

.ma20-line {
  stroke: #5aabff;
}

.ma60-line {
  stroke: #bd84ff;
}

.pattern-overlay line {
  fill: none;
  stroke-width: 1.8;
  stroke-dasharray: 5 3;
  vector-effect: non-scaling-stroke;
}

.pattern-overlay text {
  font-size: 9px;
  font-weight: 700;
  paint-order: stroke;
  stroke: #091727;
  stroke-width: 2.8px;
  stroke-linejoin: round;
}

.pattern-overlay.bullish line,
.pattern-overlay.bullish circle {
  fill: #ff7d91;
  stroke: #ff7d91;
}

.pattern-overlay.bullish text {
  fill: #ff9cac;
}

.pattern-overlay.bearish line,
.pattern-overlay.bearish circle {
  fill: #5bdbb3;
  stroke: #5bdbb3;
}

.pattern-overlay.bearish text {
  fill: #80e5c4;
}

.pattern-overlay.sideways line,
.pattern-overlay.sideways circle {
  fill: #efbe6c;
  stroke: #efbe6c;
}

.pattern-overlay.sideways text {
  fill: #f4ce8e;
}

.pattern-anchor circle {
  stroke-width: 1.7;
  vector-effect: non-scaling-stroke;
}

.crosshair line {
  stroke: rgb(199 221 241 / 38%);
  stroke-width: 0.7;
  stroke-dasharray: 2 2;
  vector-effect: non-scaling-stroke;
}

.crosshair circle {
  fill: #d7e8f8;
  stroke: #0a1727;
  stroke-width: 1;
  vector-effect: non-scaling-stroke;
}

.indicator-strip {
  display: grid;
  margin-top: 5px;
  border: 1px solid rgb(105 142 182 / 16%);
  border-radius: 11px;
  grid-template-columns: repeat(2, 1fr);
  overflow: hidden;
}

.indicator-strip > div {
  padding: 10px 8px;
  background: rgb(7 20 34 / 42%);
  text-align: left;
}

.indicator-strip > div:nth-child(odd) {
  border-right: 1px solid rgb(105 142 182 / 13%);
}

.indicator-strip > div:nth-child(-n + 2) {
  border-bottom: 1px solid rgb(105 142 182 / 13%);
}

.indicator-strip span,
.indicator-strip strong {
  display: block;
}

.indicator-strip span {
  color: #6b849c;
  font-size: 9px;
}

.indicator-strip strong {
  margin-top: 5px;
  color: #d4e2ef;
  font-family: "SFMono-Regular", Consolas, monospace;
  font-size: 12px;
}

.indicator-strip strong.positive {
  color: #ff8798;
}

.indicator-strip strong.negative {
  color: #65d8b4;
}

.chart-disclaimer {
  margin: 10px 2px 0;
  color: #5a7289;
  font-size: 9px;
  line-height: 1.55;
}
</style>
