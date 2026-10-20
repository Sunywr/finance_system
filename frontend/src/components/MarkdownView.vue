<template>
  <div class="markdown-body" v-html="html"></div>
</template>

<script setup lang="ts">
import DOMPurify from 'dompurify'
import { marked } from 'marked'
import { computed } from 'vue'

const props = defineProps<{
  content?: string | null
}>()

marked.use({ gfm: true, breaks: true })

const html = computed(() => {
  const source = props.content || ''
  if (!source.trim()) return ''
  const raw = marked.parse(source, { async: false }) as string
  return DOMPurify.sanitize(raw, {
    USE_PROFILES: { html: true },
    FORBID_TAGS: ['script', 'iframe', 'object', 'embed', 'style', 'form', 'input', 'img'],
    FORBID_ATTR: ['style', 'onerror', 'onload', 'onclick'],
  })
})
</script>

<style scoped>
.markdown-body {
  line-height: 1.8;
  font-size: 14px;
  color: #1f2937;
  max-height: 560px;
  overflow: auto;
  padding: 4px 2px;
  word-break: break-word;
}

.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4) {
  margin: 18px 0 10px;
  line-height: 1.4;
  color: #111827;
}

.markdown-body :deep(h1) {
  font-size: 22px;
  border-bottom: 1px solid #e5e7eb;
  padding-bottom: 8px;
}

.markdown-body :deep(h2) {
  font-size: 18px;
  border-bottom: 1px solid #f1f5f9;
  padding-bottom: 6px;
}

.markdown-body :deep(h3) {
  font-size: 16px;
}

.markdown-body :deep(p) {
  margin: 0 0 10px;
}

.markdown-body :deep(ul),
.markdown-body :deep(ol) {
  margin: 0 0 12px;
  padding-left: 24px;
}

.markdown-body :deep(li) {
  margin: 4px 0;
}

.markdown-body :deep(blockquote) {
  margin: 12px 0;
  padding: 8px 14px;
  border-left: 3px solid #93c5fd;
  background: #eff6ff;
  color: #1e3a8a;
}

.markdown-body :deep(code) {
  background: #f1f5f9;
  border-radius: 4px;
  padding: 2px 5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 13px;
}

.markdown-body :deep(pre) {
  margin: 12px 0;
  padding: 12px 14px;
  background: #0f172a;
  color: #e2e8f0;
  border-radius: 8px;
  overflow-x: auto;
  line-height: 1.6;
}

.markdown-body :deep(pre code) {
  background: transparent;
  color: inherit;
  padding: 0;
  font-size: 13px;
}

.markdown-body :deep(table) {
  border-collapse: collapse;
  width: 100%;
  margin: 12px 0;
  font-size: 13px;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
  border: 1px solid #e5e7eb;
  padding: 7px 10px;
  text-align: left;
  vertical-align: top;
}

.markdown-body :deep(th) {
  background: #f8fafc;
  font-weight: 700;
}

.markdown-body :deep(a) {
  color: #2563eb;
  text-decoration: underline;
  text-underline-offset: 2px;
}

.markdown-body :deep(hr) {
  border: none;
  border-top: 1px solid #e5e7eb;
  margin: 18px 0;
}

.markdown-body :deep(strong) {
  color: #111827;
}
</style>
