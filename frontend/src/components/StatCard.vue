<template>
  <div class="stat-card">
    <div class="stat-label">{{ label }}</div>
    <div class="stat-value" :class="tone">{{ value }}</div>
    <div v-if="extra" class="stat-extra">{{ extra }}</div>
  </div>
</template>

<script setup lang="ts">
withDefaults(
  defineProps<{
    label: string
    value: string
    extra?: string
    tone?: string
  }>(),
  { extra: '', tone: '' },
)
</script>
