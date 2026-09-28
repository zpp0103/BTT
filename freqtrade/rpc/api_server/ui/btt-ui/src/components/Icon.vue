<script setup lang="ts">
defineProps<{ name: string; size?: number }>();
</script>

<template>
  <svg
    class="icon"
    :width="size ?? 18"
    :height="size ?? 18"
    viewBox="0 0 24 24"
    fill="none"
    stroke="currentColor"
    stroke-width="1.7"
    stroke-linecap="round"
    stroke-linejoin="round"
    aria-hidden="true"
  >
    <template v-if="name === 'overview'"><rect x="3" y="3" width="7" height="7" rx="1" /><rect x="14" y="3" width="7" height="4" rx="1" /><rect x="14" y="11" width="7" height="10" rx="1" /><rect x="3" y="14" width="7" height="7" rx="1" /></template>
    <template v-else-if="name === 'live'"><path d="M3 12h4l2.2-6 4.1 12 2.1-6H21" /></template>
    <template v-else-if="name === 'strategy'"><path d="M4 6h16M7 6V3m10 3V3M6 10h12v10H6z" /><path d="m9 15 2 2 4-5" /></template>
    <template v-else-if="name === 'backtest'"><path d="M4 19V5m0 14h16" /><path d="m7 15 3-4 3 2 5-7" /></template>
    <template v-else-if="name === 'orders'"><path d="M5 4h14v16H5z" /><path d="M8 8h8M8 12h8M8 16h5" /></template>
    <template v-else-if="name === 'risk'"><path d="M12 3 4 6v5c0 5 3.4 8.3 8 10 4.6-1.7 8-5 8-10V6z" /><path d="M12 8v5m0 3h.01" /></template>
    <template v-else-if="name === 'settings'"><circle cx="12" cy="12" r="3" /><path d="M19 13.5v-3l-2-.7-.7-1.7.9-1.9-2.1-2.1-1.9.9-1.7-.7-.7-2h-3l-.7 2-1.7.7-1.9-.9-2.1 2.1.9 1.9-.7 1.7-2 .7v3l2 .7.7 1.7-.9 1.9 2.1 2.1 1.9-.9 1.7.7.7 2h3l.7-2 1.7-.7 1.9.9 2.1-2.1-.9-1.9.7-1.7z" /></template>
    <template v-else-if="name === 'refresh'"><path d="M20 6v5h-5M4 18v-5h5" /><path d="M6.1 9a7 7 0 0 1 11.6-2.6L20 9M4 15l2.3 2.6A7 7 0 0 0 17.9 15" /></template>
    <template v-else-if="name === 'clock'"><circle cx="12" cy="12" r="9" /><path d="M12 7v5l3 2" /></template>
    <template v-else-if="name === 'server'"><rect x="4" y="4" width="16" height="6" rx="1" /><rect x="4" y="14" width="16" height="6" rx="1" /><path d="M8 7h.01M8 17h.01" /></template>
    <template v-else-if="name === 'alert'"><path d="M12 3 2.8 20h18.4z" /><path d="M12 9v4m0 3h.01" /></template>
    <template v-else><circle cx="12" cy="12" r="8" /></template>
  </svg>
</template>
