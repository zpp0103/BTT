<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from "vue";
import { loadDashboard } from "@/api/dashboard";
import type { DashboardData, LoadState } from "@/api/types";
import Icon from "@/components/Icon.vue";
import DashboardView from "@/views/DashboardView.vue";
import IntelligenceView from "@/views/IntelligenceView.vue";
import ModuleView from "@/views/ModuleView.vue";
import SettingsView from "@/views/SettingsView.vue";

const routes = [
  { path: "/", key: "overview", label: "总览", icon: "overview" },
  { path: "/live", key: "live", label: "实时交易", icon: "live" },
  { path: "/strategies", key: "strategies", label: "策略管理", icon: "strategy" },
  { path: "/backtest", key: "backtest", label: "回测分析", icon: "backtest" },
  { path: "/positions", key: "positions", label: "持仓与订单", icon: "orders" },
  { path: "/risk", key: "risk", label: "风险控制", icon: "risk" },
  { path: "/intelligence", key: "intelligence", label: "市场情报", icon: "intelligence" },
  { path: "/settings", key: "settings", label: "系统设置", icon: "settings" },
];

const currentPath = ref(normalizePath(location.pathname));
const currentRoute = computed(() => routes.find((route) => route.path === currentPath.value) ?? routes[0]);
const data = ref<DashboardData | null>(null);
const state = ref<LoadState>("idle");
const demo = ref(sessionStorage.getItem("btt-demo-mode") === "true");
const menuOpen = ref(false);
let refreshTimer: number | undefined;

function normalizePath(path: string): string {
  const normalized = `/${path.split("/").filter(Boolean).join("/")}`;
  return normalized === "/" || routes.some((route) => route.path === normalized) ? normalized : "/";
}

function navigate(path: string) {
  currentPath.value = path;
  menuOpen.value = false;
  history.pushState({}, "", path);
}

async function refresh() {
  state.value = "loading";
  try {
    data.value = await loadDashboard(demo.value);
    state.value = data.value.errors.length >= 9 ? "error" : "ready";
  } catch {
    state.value = "error";
  }
}

async function toggleDemo() {
  demo.value = !demo.value;
  sessionStorage.setItem("btt-demo-mode", String(demo.value));
  await refresh();
}

function handlePopState() {
  currentPath.value = normalizePath(location.pathname);
}

onMounted(() => {
  addEventListener("popstate", handlePopState);
  void refresh();
  refreshTimer = window.setInterval(() => {
    if (!demo.value && document.visibilityState === "visible") void refresh();
  }, 30_000);
});

onBeforeUnmount(() => {
  removeEventListener("popstate", handlePopState);
  if (refreshTimer) clearInterval(refreshTimer);
});
</script>

<template>
  <div class="app-shell">
    <button class="mobile-menu" type="button" aria-label="切换导航" :aria-expanded="menuOpen" aria-controls="primary-navigation" @click="menuOpen = !menuOpen"><span></span><span></span><span></span></button>
    <aside class="sidebar" :class="{ open: menuOpen }">
      <div class="brand">
        <div class="brand-mark"><span></span><span></span><span></span></div>
        <div><strong>BTT</strong><small>QUANT TERMINAL</small></div>
      </div>
      <nav id="primary-navigation" aria-label="主导航">
        <span class="nav-section">交易工作台</span>
        <a
          v-for="route in routes.slice(0, -1)"
          :key="route.path"
          :href="route.path"
          :class="{ active: currentRoute.key === route.key }"
          :aria-current="currentRoute.key === route.key ? 'page' : undefined"
          @click.prevent="navigate(route.path)"
        >
          <Icon :name="route.icon" /><span>{{ route.label }}</span>
        </a>
        <span class="nav-section nav-system">系统</span>
        <a href="/settings" :class="{ active: currentRoute.key === 'settings' }" :aria-current="currentRoute.key === 'settings' ? 'page' : undefined" @click.prevent="navigate('/settings')">
          <Icon name="settings" /><span>系统设置</span>
        </a>
      </nav>
      <div class="sidebar-status">
        <div class="bot-avatar">BT</div>
        <div><strong>{{ data?.config?.bot_name ?? "BTT Terminal" }}</strong><span><i :class="{ online: data?.ping }"></i>{{ data?.ping ? "服务在线" : "连接异常" }}</span></div>
      </div>
      <div class="version-line">BTT UI v0.1 · API {{ data?.config?.api_version ?? "—" }}</div>
    </aside>
    <div v-if="menuOpen" class="sidebar-backdrop" @click="menuOpen = false"></div>
    <main>
      <DashboardView
        v-if="currentRoute.key === 'overview'"
        :data="data"
        :state="state"
        :demo="demo"
        @refresh="refresh"
        @toggle-demo="toggleDemo"
        @navigate="navigate"
      />
      <SettingsView v-else-if="currentRoute.key === 'settings'" @connected="refresh" />
      <IntelligenceView v-else-if="currentRoute.key === 'intelligence'" :demo="demo" @toggle-demo="toggleDemo" />
      <ModuleView v-else :module="currentRoute.key" :data="data" />
    </main>
  </div>
</template>
