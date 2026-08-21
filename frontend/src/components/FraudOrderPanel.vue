<template>
	<div class="rounded-lg border border-outline-gray-1 p-4">
		
		<div class="flex justify-between items-center">
			<h2 class="text-base font-medium text-ink-gray-8">Fraud Intelligence</h2>
			<div v-if="fraud.data" class="flex items-center gap-2">
				<div class="flex flex-col gap-1 min-w-32 mr-2">
					<div class="flex justify-between text-xs font-semibold">
						<span :class="{ 'text-green-600': fraud.data.score < 40, 'text-orange-500': fraud.data.score >= 40 && fraud.data.score < 70, 'text-red-600': fraud.data.score >= 70 }">{{ fraud.data.verdict }}</span>
					</div>
					<div class="h-2 w-32 bg-surface-gray-3 rounded-full overflow-hidden flex">
						<div class="h-full transition-all duration-500 rounded-full"
							:class="{ 'bg-green-500': fraud.data.score < 40, 'bg-orange-500': fraud.data.score >= 40 && fraud.data.score < 70, 'bg-red-500': fraud.data.score >= 70 }"
							:style="{ width: `${Math.min(100, Math.max(5, fraud.data.score))}%` }">
						</div>
					</div>
				</div>
			</div>
		</div>

		
		<div v-if="fraud.loading" class="mt-4 flex justify-center"><Spinner class="size-4" /></div>
		
		<div v-else-if="fraud.data" class="mt-4 space-y-4">
			
			
			<div v-if="fraud.data.signals" class="mt-2">
				<div class="text-sm text-ink-gray-5 mb-2">Signal Matrix</div>
				
				<div class="grid grid-cols-2 gap-2">
					<div v-for="(val, key) in Object.fromEntries(Object.entries(JSON.parse(fraud.data.signals || '{}')).filter(([k,v]) => typeof v !== 'object' || v === null))" :key="key" class="flex justify-between items-center bg-surface-gray-2 rounded px-3 py-2 text-sm border border-outline-gray-2">
						<span class="text-ink-gray-6 font-medium capitalize">{{ key.replace(/_/g, " ") }}</span>
						<span v-if="typeof val === 'boolean'">
							<UiStatusBadge :label="val ? 'Yes' : 'No'" :theme="val ? 'red' : 'gray'" />
						</span>
						<span v-else class="text-ink-gray-8 font-semibold">{{ val }}</span>
					</div>
				</div>

				<div v-for="(val, key) in Object.fromEntries(Object.entries(JSON.parse(fraud.data.signals || '{}')).filter(([k,v]) => typeof v === 'object' && v !== null))" :key="key" class="mt-4">
					<div class="text-sm text-ink-gray-5 mb-2 capitalize">{{ key.replace(/_/g, " ") }}</div>
					<div class="grid grid-cols-2 gap-2">
						<div v-for="(v, k) in val" :key="k" class="flex justify-between items-center bg-surface-gray-2 rounded px-3 py-2 text-sm border border-outline-gray-2">
							<span class="text-ink-gray-6 font-medium capitalize">{{ String(k).replace(/_/g, " ") }}</span>
							<span v-if="typeof v === 'boolean'">
								<UiStatusBadge :label="v ? 'Yes' : 'No'" :theme="v ? 'red' : 'gray'" />
							</span>
							<span v-else class="text-ink-gray-8 font-semibold">{{ v }}</span>
						</div>
					</div>
				</div>
			</div>



			
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed } from "vue"

import { Spinner, createResource } from "frappe-ui"
import UiStatusBadge from "@/components/UiStatusBadge.vue"

const props = defineProps<{ order: string }>()

const fraud = createResource({
	url: "shop.api.fraud.get_order_fraud_profile",
	makeParams: () => ({ order: props.order }),
	auto: true,
})

</script>
