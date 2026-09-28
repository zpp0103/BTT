<script setup lang="ts">
import { computed } from "vue";
import type { EquityPoint } from "@/api/types";

const props = defineProps<{ points: EquityPoint[]; currency: string }>();

const width = 900;
const height = 260;
const pad = 16;
const values = computed(() => props.points.map((point) => point.value));
const min = computed(() => Math.min(...values.value));
const max = computed(() => Math.max(...values.value));
const range = computed(() => Math.max(max.value - min.value, 1));
const coords = computed(() =>
  props.points.map((point, index) => ({
    x: pad + (index / Math.max(props.points.length - 1, 1)) * (width - pad * 2),
    y: pad + ((max.value - point.value) / range.value) * (height - pad * 2),
  })),
);
const linePath = computed(() => coords.value.map((point, index) => `${index ? "L" : "M"} ${point.x.toFixed(1)} ${point.y.toFixed(1)}`).join(" "));
const areaPath = computed(() => `${linePath.value} L ${width - pad} ${height} L ${pad} ${height} Z`);
const change = computed(() => {
  if (props.points.length < 2) return 0;
  return ((props.points.at(-1)!.value / props.points[0].value) - 1) * 100;
});
const format = (value: number) => new Intl.NumberFormat("zh-CN", { maximumFractionDigits: 0 }).format(value);
</script>

<template>
  <div class="equity-chart">
    <div class="chart-summary">
      <div>
        <span class="eyebrow">组合权益</span>
        <strong>{{ format(points.at(-1)?.value ?? 0) }} <small>{{ currency }}</small></strong>
      </div>
      <span class="metric-delta" :class="{ negative: change < 0 }">{{ change >= 0 ? "+" : "" }}{{ change.toFixed(2) }}%</span>
    </div>
    <svg viewBox="0 0 900 260" role="img" aria-label="组合权益历史曲线" preserveAspectRatio="none">
      <defs>
        <linearGradient id="equity-fill" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stop-color="#35c7a1" stop-opacity=".28" />
          <stop offset="100%" stop-color="#35c7a1" stop-opacity="0" />
        </linearGradient>
      </defs>
      <line v-for="i in 5" :key="i" x1="0" x2="900" :y1="i * 43" :y2="i * 43" class="chart-grid" />
      <path :d="areaPath" fill="url(#equity-fill)" />
      <path :d="linePath" class="chart-line" />
      <circle v-if="coords.length" :cx="coords.at(-1)?.x" :cy="coords.at(-1)?.y" r="4" class="chart-dot" />
    </svg>
    <div class="chart-range">
      <span>{{ points.length ? new Date(points[0].timestamp).toLocaleDateString("zh-CN", { month: "short", day: "numeric" }) : "—" }}</span>
      <span>{{ points.length ? new Date(points.at(-1)!.timestamp).toLocaleDateString("zh-CN", { month: "short", day: "numeric" }) : "—" }}</span>
    </div>
  </div>
</template>
