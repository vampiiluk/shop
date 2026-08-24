<template>
	<div class="rounded-lg border border-outline-gray-1 p-4">
		<h2 class="text-base font-medium text-ink-gray-8">Device Fingerprints</h2>

		<!-- Live check -->
		<div v-if="live.data" class="mt-3 rounded-lg border border-outline-gray-2 bg-surface-gray-1 p-3">
			<div class="mb-2 text-sm font-medium text-ink-gray-7">
				Live check <span class="text-xs font-normal text-ink-gray-4">(now)</span>
			</div>
			<div class="grid grid-cols-2 gap-2 text-sm">
				<div class="flex justify-between items-center bg-surface-gray-2 rounded px-3 py-2 border border-outline-gray-2">
					<span class="text-ink-gray-6">Blacklisted</span>
					<UiStatusBadge :label="live.data.blacklisted_now ? 'Yes' : 'No'" :theme="live.data.blacklisted_now ? 'red' : 'green'" />
				</div>
				<div class="flex justify-between items-center bg-surface-gray-2 rounded px-3 py-2 border border-outline-gray-2">
					<span class="text-ink-gray-6">Failed deliveries</span>
					<span class="text-ink-gray-8 font-semibold">{{ live.data.failed_deliveries }}</span>
				</div>
			</div>
			<div v-if="live.data.city_rates?.length" class="mt-2 space-y-1.5">
				<div v-for="c in live.data.city_rates" :key="c.city" class="flex items-center gap-2 text-sm">
					<span class="w-28 truncate text-ink-gray-6">{{ c.city }}</span>
					<div class="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-gray-3">
						<div
							class="h-full rounded-full"
							:class="c.rto_rate >= 40 ? 'bg-red-500' : c.rto_rate >= 20 ? 'bg-orange-500' : 'bg-green-500'"
							:style="{ width: `${Math.min(100, c.rto_rate)}%` }"
						/>
					</div>
					<span class="w-12 text-right text-xs text-ink-gray-5">{{ c.rto_rate.toFixed(0) }}%</span>
				</div>
			</div>
			<div v-if="live.data.last_order" class="mt-2 flex items-center justify-between text-sm">
				<router-link :to="`/orders/${live.data.last_order}`" class="text-ink-gray-7 hover:underline">
					Last order {{ live.data.last_order }}
				</router-link>
				<UiStatusBadge
					v-if="live.data.last_order_verdict"
					:label="live.data.last_order_verdict"
					:theme="verdictTheme(live.data.last_order_verdict)"
				/>
			</div>
		</div>

		<div v-if="fraud.loading" class="mt-4 flex justify-center"><Spinner class="size-4" /></div>

		<div v-else-if="fraud.data" class="mt-4">
			<div class="text-sm text-ink-gray-5 mb-2">Fingerprints linked to this customer</div>
			<div v-if="fraud.data.fingerprints?.length" class="space-y-1">
				<div v-for="fp in fraud.data.fingerprints" :key="fp" class="text-base text-ink-gray-8 break-all font-mono text-xs bg-surface-gray-2 p-2 rounded border border-outline-gray-2">
					{{ fp }}
				</div>
			</div>
			<div v-else class="text-xs text-ink-gray-5">No fingerprints recorded</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { Spinner, createResource } from "frappe-ui"
import UiStatusBadge from "@/components/UiStatusBadge.vue"
import { verdictTheme } from "@/utils/verdict"

const props = defineProps<{ customer: string }>()

const fraud = createResource({
	url: "shop.api.fraud.get_customer_fraud_profile",
	makeParams: () => ({ customer: props.customer }),
	auto: true,
})

const live = createResource({
	url: "shop.api.fraud.get_customer_live",
	makeParams: () => ({ customer: props.customer }),
	auto: true,
})
</script>
