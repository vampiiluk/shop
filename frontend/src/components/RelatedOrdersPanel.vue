<template>
	<div class="rounded-lg border border-outline-gray-1 p-4 mt-6">
		<h2 class="text-base font-medium text-ink-gray-8">Related Orders</h2>
		<p class="text-sm text-ink-gray-5 mb-4">Cross-referenced by fingerprint, email, phone, and address.</p>
		
		<div v-if="related.loading" class="flex justify-center"><Spinner class="size-4" /></div>
		
		<div v-else-if="related.data" class="space-y-4">
			<div v-if="related.data.related?.length" class="space-y-2">
				<router-link
					v-for="o in related.data.related"
					:key="o.name"
					:to="`/orders/${o.name}`"
					class="block border border-outline-gray-2 rounded p-3 hover:bg-surface-gray-2"
				>
					<div class="flex justify-between items-center mb-1">
						<span class="font-medium text-ink-gray-8">{{ o.name }}</span>
						<div class="flex items-center gap-2">
							<UiStatusBadge :label="o.display_status" :theme="statusTheme(o.display_status)" />
							<UiStatusBadge v-if="o.custom_fraud_verdict" :label="`${o.custom_fraud_verdict} (${o.custom_fraud_score})`" :theme="verdictTheme(o.custom_fraud_verdict)" />
						</div>
					</div>
					<div class="text-sm text-ink-gray-8">{{ o.customer }}</div>
					<div class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-ink-gray-5">
						<span v-if="o.transaction_date">Ordered {{ o.transaction_date }}</span>
						<span v-if="o.delivered_on" class="text-green-600">Delivered {{ o.delivered_on }}</span>
					</div>
					<div class="mt-2 flex flex-wrap gap-1">
						<span v-for="reason in o.match_reasons" :key="reason" class="text-xs bg-surface-gray-3 text-ink-gray-6 px-2 py-0.5 rounded">
							Matched {{ reason }}
						</span>
					</div>
				</router-link>
			</div>
			<div v-else class="text-sm text-ink-gray-5">
				No related orders found.
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { Spinner, createResource } from "frappe-ui"
import UiStatusBadge from "@/components/UiStatusBadge.vue"
import { verdictTheme } from "@/utils/verdict"

const props = defineProps<{ order: string }>()

const related = createResource({
	url: "shop.api.fraud.get_related_orders",
	makeParams: () => ({ order: props.order }),
	auto: true,
})

function statusTheme(status: string): string {
	switch (status) {
		case "Delivered": return "green"
		case "Returned": return "orange"
		case "Cancelled": return "red"
		case "Active": return "blue"
		case "Draft": return "gray"
		default: return "gray"
	}
}
</script>
