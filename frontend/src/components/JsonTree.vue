<template>
	<div class="font-mono text-sm">
		<template v-if="depth === 0 && label === null"></template>
		<div v-for="(value, key) in data" :key="key" :class="depth ? 'ml-3 border-l border-outline-gray-2 pl-3' : ''">
			<div class="py-0.5">
				<button
					v-if="isBranch(value)"
					class="flex w-full items-center gap-1.5 text-left hover:text-ink-gray-6"
					@click="open[String(key)] = !open[String(key)]"
				>
					<span class="text-ink-gray-4 text-xs">{{ open[String(key)] ? '▾' : '▸' }}</span>
					<span class="text-ink-gray-6">{{ key }}:</span>
					<span class="text-ink-gray-4 text-xs">{{ summary(value) }}</span>
				</button>
				<div v-else class="flex justify-between gap-3">
					<span class="text-ink-gray-6">{{ key }}:</span>
					<span
						class="break-all text-right"
						:class="danger(value) ? 'text-red-600 font-semibold' : 'text-ink-gray-8'"
					>
						{{ display(value) }}
					</span>
				</div>
			</div>
			<JsonTree v-if="isBranch(value) && open[String(key)]" :data="value" :depth="depth + 1" />
		</div>
	</div>
</template>

<script setup lang="ts">
import { reactive, watch } from 'vue'

const props = defineProps<{ data: Record<string, unknown> | unknown[]; depth?: number; label?: string | null }>()

const open = reactive<Record<string, boolean>>({})

watch(
	() => props.data,
	() => {
		for (const [k, v] of Object.entries(props.data || {})) {
			if (isBranch(v) && props.depth === 0) open[k] = false
		}
	},
	{ immediate: true },
)

function isBranch(value: unknown): boolean {
	return !!value && typeof value === 'object' && Object.keys(value as object).length > 0
}

function summary(value: object): string {
	return `${Object.keys(value).length} fields`
}

function danger(value: unknown): boolean {
	if (value === true) return true
	if (typeof value === 'string') return ['bad', 'all'].includes(value.toLowerCase())
	return false
}

function display(value: unknown): string {
	if (value === null || value === undefined || value === '') return '—'
	if (typeof value === 'boolean') return value ? 'Yes' : 'No'
	if (Array.isArray(value)) return JSON.stringify(value)
	if (typeof value === 'object') return JSON.stringify(value)
	return String(value)
}
</script>
