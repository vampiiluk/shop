<template>
	<div class="grid grid-cols-2 gap-2">
		<div
			v-for="(value, key) in scalars"
			:key="key"
			class="flex justify-between items-center bg-surface-gray-2 rounded px-3 py-2 text-sm border border-outline-gray-2"
		>
			<span class="text-ink-gray-6 font-medium capitalize">{{ String(key).replace(/_/g, ' ') }}</span>
			<span v-if="typeof value === 'boolean'">
				<UiStatusBadge :label="value ? 'Yes' : 'No'" :theme="value ? 'red' : 'gray'" />
			</span>
			<span v-else class="text-ink-gray-8 font-semibold text-right">{{ formatScalar(value) }}</span>
		</div>
	</div>
	<div v-for="(entries, group) in groups" :key="group" class="mt-3">
		<div class="text-sm text-ink-gray-5 mb-2 capitalize">{{ String(group).replace(/_/g, ' ') }}</div>
		<div class="grid grid-cols-2 gap-2">
			<div
				v-for="(v, k) in entries"
				:key="k"
				class="flex justify-between items-center bg-surface-gray-2 rounded px-3 py-2 text-sm border border-outline-gray-2"
			>
				<span class="text-ink-gray-6 font-medium capitalize">{{ String(k).replace(/_/g, ' ') }}</span>
					<span v-if="typeof v === 'boolean'">
						<UiStatusBadge :label="v ? 'Yes' : 'No'" :theme="v ? 'red' : 'gray'" />
					</span>
					<span v-else class="text-ink-gray-8 font-semibold text-right">{{ formatScalar(v) }}</span>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import UiStatusBadge from '@/components/UiStatusBadge.vue'

const props = defineProps<{ signals: Record<string, unknown> | null }>()

const entries = computed(() => Object.entries(props.signals || {}))

const scalars = computed(() =>
	Object.fromEntries(entries.value.filter(([, v]) => typeof v !== 'object' || v === null)),
)

const groups = computed(() => {
	const out: Record<string, Record<string, unknown>> = {}
	for (const [k, v] of entries.value) {
		if (v && typeof v === 'object' && !Array.isArray(v)) out[k] = v as Record<string, unknown>
	}
	return out
})

function formatScalar(value: unknown): string {
	if (value === null || value === undefined || value === '') return '—'
	if (typeof value === 'number') {
		return Number.isInteger(value) ? String(value) : value.toFixed(2)
	}
	return String(value)
}
</script>
