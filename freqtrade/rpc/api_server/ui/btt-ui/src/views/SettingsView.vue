<script setup lang="ts">
import { ref } from "vue";
import { ApiError, loadApiConfig, login } from "@/api/client";
import Icon from "@/components/Icon.vue";

const emit = defineEmits<{ connected: [] }>();
const saved = loadApiConfig();
const baseUrl = ref(saved.baseUrl);
const username = ref("");
const password = ref("");
const state = ref<"idle" | "loading" | "success" | "error">(saved.accessToken ? "success" : "idle");
const message = ref(saved.accessToken ? "当前会话已保存访问令牌" : "尚未登录");

async function connect() {
  state.value = "loading";
  message.value = "正在验证 API 凭据…";
  try {
    await login(baseUrl.value.trim(), username.value, password.value);
    password.value = "";
    state.value = "success";
    message.value = "连接成功，访问令牌仅保存在当前浏览器会话中";
    emit("connected");
  } catch (error) {
    state.value = "error";
    message.value = error instanceof ApiError ? `${error.status} · ${error.message}` : "无法连接 API";
  }
}
</script>

<template>
  <section class="view settings-view">
    <header class="view-header"><div><div class="header-kicker">SYSTEM</div><h1>系统设置</h1><p>配置当前终端的 API 连接与会话认证</p></div></header>
    <div class="settings-layout">
      <article class="panel settings-card">
        <div class="panel-head"><div><span class="section-label">CONNECTION</span><h2>Freqtrade API</h2></div><span class="status-pill" :class="{ ok: state === 'success', warn: state === 'error' }">{{ state === "success" ? "已连接" : state === "loading" ? "连接中" : "未连接" }}</span></div>
        <form @submit.prevent="connect">
          <label><span>API 地址</span><input v-model="baseUrl" type="url" placeholder="同源部署请留空" autocomplete="url" /><small>内置部署使用同源 `/api/v1`；独立开发时可填完整服务地址。</small></label>
          <div class="form-row">
            <label><span>用户名</span><input v-model="username" required autocomplete="username" /></label>
            <label><span>密码</span><input v-model="password" required type="password" autocomplete="current-password" /></label>
          </div>
          <div class="connection-message" :class="state"><Icon :name="state === 'error' ? 'alert' : 'server'" /><span>{{ message }}</span></div>
          <button class="primary-button" type="submit" :disabled="state === 'loading'">{{ state === "loading" ? "正在连接…" : "验证并连接" }}</button>
        </form>
      </article>
      <aside class="panel security-note">
        <span class="section-label">SECURITY</span>
        <h2>会话安全</h2>
        <p>用户名和密码只用于换取 Freqtrade JWT，不会被保存。访问令牌存储于 <code>sessionStorage</code>，关闭标签页后由浏览器清理。</p>
        <ul><li>生产环境建议启用 HTTPS</li><li>不要在共享设备保存会话</li><li>API 错误不会被伪装为正常状态</li></ul>
      </aside>
    </div>
  </section>
</template>
