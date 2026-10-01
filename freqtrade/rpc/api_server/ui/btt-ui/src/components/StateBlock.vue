<script setup lang="ts">
import Icon from "./Icon.vue";

defineProps<{
  state: "loading" | "empty" | "error";
  title?: string;
  detail?: string;
}>();
</script>

<template>
  <div class="state-block" :class="`state-${state}`" role="status">
    <span v-if="state === 'loading'" class="spinner" aria-hidden="true"></span>
    <Icon v-else :name="state === 'error' ? 'alert' : 'overview'" :size="20" />
    <div>
      <strong>{{ title ?? (state === "loading" ? "正在同步数据" : state === "error" ? "数据暂不可用" : "暂无数据") }}</strong>
      <p v-if="detail">{{ detail }}</p>
    </div>
  </div>
</template>
