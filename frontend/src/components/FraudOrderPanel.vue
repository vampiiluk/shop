<template>
	<div class="rounded-lg border border-outline-gray-1 p-4">
		<div class="flex justify-between items-start">
			<h2 class="text-base font-medium text-ink-gray-8">Fraud Intelligence</h2>
			<div v-if="fraud.data" class="flex items-center gap-2">
				<div class="flex flex-col gap-1 min-w-32 mr-2">
					<div class="flex justify-between text-xs font-semibold text-ink-gray-5">
						<span>At checkout</span>
						<span
							:class="{ 'text-green-600': fraud.data.score < 40, 'text-orange-500': fraud.data.score >= 40 && fraud.data.score < 70, 'text-red-600': fraud.data.score >= 70 }"
						>{{ fraud.data.verdict }} {{ fraud.data.score }}</span>
					</div>
					<div class="h-1.5 w-32 bg-surface-gray-3 rounded-full overflow-hidden flex">
						<div class="h-full transition-all duration-500 rounded-full"
							:class="{ 'bg-green-500': fraud.data.score < 40, 'bg-orange-500': fraud.data.score >= 40 && fraud.data.score < 70, 'bg-red-500': fraud.data.score >= 70 }"
							:style="{ width: `${Math.min(100, Math.max(5, fraud.data.score))}%` }"
						/>
					</div>
				</div>
			</div>
		</div>

		<div v-if="fraud.loading" class="mt-3 flex justify-center"><Spinner class="size-4" /></div>

		<div v-else-if="fraud.data" class="mt-3 space-y-2.5">
			<!-- Key snapshot signals (curated — full matrix on detail page) -->
			<div class="grid grid-cols-2 gap-1.5 text-sm">
				<div
					v-for="row in keyRows"
					:key="row.label"
					class="flex justify-between items-center bg-surface-gray-2 rounded px-2.5 py-1.5 border border-outline-gray-2"
				>
					<span class="text-xs text-ink-gray-6">{{ row.label }}</span>
					<UiStatusBadge v-if="row.badge !== undefined" :label="row.badge ? 'Yes' : 'No'" :theme="row.badge ? 'red' : 'gray'" />
					<span v-else class="text-ink-gray-8 font-semibold">{{ row.value }}</span>
				</div>
			</div>

			<!-- Live check -->
			<div v-if="live.data" class="space-y-1">
				<div class="text-xs text-ink-gray-5">Live check <span class="text-xs">(now)</span></div>
				<div class="grid grid-cols-2 gap-1.5 text-sm">
					<div class="flex justify-between items-center bg-surface-gray-2 rounded px-2.5 py-1.5 border border-outline-gray-2">
						<span class="text-xs text-ink-gray-6">Blacklisted now</span>
						<UiStatusBadge :label="live.data.blacklisted_now ? 'Yes' : 'No'" :theme="live.data.blacklisted_now ? 'red' : 'green'" />
					</div>
					<div class="flex justify-between items-center bg-surface-gray-2 rounded px-2.5 py-1.5 border border-outline-gray-2">
						<span class="text-xs text-ink-gray-6">Failed deliveries</span>
						<span class="text-ink-gray-8 font-semibold">{{ live.data.customer_failed_deliveries }}</span>
					</div>
					<div class="flex justify-between items-center bg-surface-gray-2 rounded px-2.5 py-1.5 border border-outline-gray-2">
						<span class="text-xs text-ink-gray-6">City RTO now</span>
						<span class="text-ink-gray-8 font-semibold">{{ live.data.city_rto_rate.toFixed(0) }}%</span>
					</div>
					<div class="flex justify-between items-center bg-surface-gray-2 rounded px-2.5 py-1.5 border border-outline-gray-2">
						<span class="text-xs text-ink-gray-6">Device orders since</span>
						<span class="text-ink-gray-8 font-semibold">{{ live.data.velocity_window.same_device_orders_after }}</span>
					</div>
				</div>
			</div>

			<router-link
				:to="`/fraud/${order}`"
				class="inline-flex items-center gap-1 text-xs text-ink-gray-5 underline hover:text-ink-gray-8"
			>
				Full report & raw fingerprint event
			</router-link>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { Spinner, createResource } from 'frappe-ui'

import UiStatusBadge from '@/components/UiStatusBadge.vue'

const props = defineProps<{ order: string }>()

const fraud = createResource({
	url: 'shop.api.fraud.get_order_fraud_profile',
	makeParams: () => ({ order: props.order }),
	auto: true,
})

const live = createResource({
	url: 'shop.api.fraud.get_live_check',
	makeParams: () => ({ order: props.order }),
	auto: true,
})

interface Row {
	label: string
	value?: string
	badge?: boolean
}

const keyRows = computed<Row[]>(() => {
	let signals: Record<string, any> = {}
	try {
		signals = JSON.parse(fraud.data?.signals || '{}')
	} catch {
		signals = {}
	}

	const rows: Row[] = []

	if (typeof signals.fp_suspect_score === 'number') {
		rows.push({ label: 'Suspect score', value: `${Math.round(signals.fp_suspect_score * 100)}/100` })
	}
	if (signals.repeat_history) {
		const h = signals.repeat_history
		rows.push({ label: 'History (90d)', value: `${h.total ?? 0} orders · ${(h.failed ?? 0) + (h.rto ?? 0)} bad` })
	}
	if (signals.blacklisted) {
		rows.push({ label: 'Blacklist hit', badge: true })
	}
	if (signals.orders_last_60m !== undefined) {
		rows.push({ label: 'Orders ±60m', value: String(signals.orders_last_60m) })
	}
	if (signals.velocity_block !== undefined) {
		rows.push({ label: 'Velocity block', badge: !!signals.velocity_block })
	}
	if (signals.address_score !== undefined) {
		rows.push({ label: 'Address risk', value: `${signals.address_score}/60` })
	}
	if (signals.city_rto_rate !== undefined) {
		rows.push({ label: 'City RTO', value: `${Number(signals.city_rto_rate).toFixed(0)}%` })
	}
	if (signals.risky_hour !== undefined) {
		rows.push({ label: 'Risky hour', badge: !!signals.risky_hour })
	}

	return rows.slice(0, 8)
})
</script>
