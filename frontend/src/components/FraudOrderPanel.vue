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
						>{{ fraud.data.verdict }}</span>
					</div>
					<div class="h-2 w-32 bg-surface-gray-3 rounded-full overflow-hidden flex">
						<div class="h-full transition-all duration-500 rounded-full"
							:class="{ 'bg-green-500': fraud.data.score < 40, 'bg-orange-500': fraud.data.score >= 40 && fraud.data.score < 70, 'bg-red-500': fraud.data.score >= 70 }"
							:style="{ width: `${Math.min(100, Math.max(5, fraud.data.score))}%` }"
						/>
					</div>
				</div>
			</div>
		</div>

		<div v-if="fraud.loading" class="mt-4 flex justify-center"><Spinner class="size-4" /></div>

		<div v-else-if="fraud.data" class="mt-4 space-y-4">
			<!-- Suspect score highlight -->
			<div v-if="suspectScore !== null" class="flex justify-between items-center bg-surface-gray-1 rounded px-3 py-2 border border-outline-gray-2">
				<span class="text-sm text-ink-gray-6 font-medium">Suspect score (verified)</span>
				<span class="font-semibold" :class="suspectScore >= 0.8 ? 'text-red-600' : suspectScore >= 0.5 ? 'text-orange-500' : 'text-green-600'">
					{{ Math.round(suspectRaw ?? suspectScore * 100) }} / 100
				</span>
			</div>

			<!-- Live check -->
			<div v-if="live.data" class="space-y-1.5">
				<div class="text-sm text-ink-gray-5">Live check <span class="text-xs">(now)</span></div>
				<div class="grid grid-cols-2 gap-2">
					<div class="flex justify-between items-center bg-surface-gray-2 rounded px-3 py-2 text-sm border border-outline-gray-2">
						<span class="text-ink-gray-6">Blacklisted now</span>
						<UiStatusBadge :label="live.data.blacklisted_now ? 'Yes' : 'No'" :theme="live.data.blacklisted_now ? 'red' : 'green'" />
					</div>
					<div class="flex justify-between items-center bg-surface-gray-2 rounded px-3 py-2 text-sm border border-outline-gray-2">
						<span class="text-ink-gray-6">Failed deliveries</span>
						<span class="text-ink-gray-8 font-semibold">{{ live.data.customer_failed_deliveries }}</span>
					</div>
					<div class="flex justify-between items-center bg-surface-gray-2 rounded px-3 py-2 text-sm border border-outline-gray-2">
						<span class="text-ink-gray-6">Same phone ±60m</span>
						<span class="text-ink-gray-8 font-semibold">{{ live.data.velocity_window.phone_orders_within_60m_of_placement }}</span>
					</div>
					<div class="flex justify-between items-center bg-surface-gray-2 rounded px-3 py-2 text-sm border border-outline-gray-2">
						<span class="text-ink-gray-6">City RTO now</span>
						<span class="text-ink-gray-8 font-semibold">{{ live.data.city_rto_rate.toFixed(1) }}%</span>
					</div>
				</div>
			</div>

			<!-- Snapshot signal matrix -->
			<div v-if="parsedSignals">
				<div class="text-sm text-ink-gray-5 mb-2">Signals at placement</div>
				<SignalMatrix :signals="parsedSignals" />
			</div>

			<router-link
				:to="`/fraud/${order}`"
				class="inline-flex items-center gap-1 text-sm text-ink-gray-6 underline hover:text-ink-gray-8"
			>
				More detail
			</router-link>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { Spinner, createResource } from 'frappe-ui'

import SignalMatrix from '@/components/SignalMatrix.vue'
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

const parsedSignals = computed(() => {
	try {
		return JSON.parse(fraud.data?.signals || '{}')
	} catch {
		return null
	}
})

const suspectScore = computed(() => {
	const value = fraud.data?.fp_highlights?.suspect_score
	return typeof value === 'number' ? value : null
})

const suspectRaw = computed(() => {
	const value = fraud.data?.fp_highlights?.suspect_score_raw
	return typeof value === 'number' ? value : null
})
</script>
