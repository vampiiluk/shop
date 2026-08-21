<template>
	<div class="rounded-lg border border-outline-gray-1 p-4">
		<h2 class="text-base font-medium text-ink-gray-8">Device Fingerprints & Emails</h2>
		
		<div v-if="fraud.loading" class="mt-4 flex justify-center"><Spinner class="size-4" /></div>
		
		<div v-else-if="fraud.data" class="mt-4 space-y-4">
			<div>
				<div class="text-sm text-ink-gray-5 mb-2">Fingerprints linked to this customer</div>
				<div v-if="fraud.data.fingerprints?.length" class="space-y-1">
					<div v-for="fp in fraud.data.fingerprints" :key="fp" class="text-base text-ink-gray-8 break-all font-mono text-xs bg-surface-gray-2 p-2 rounded border border-outline-gray-2">
						{{ fp }}
					</div>
				</div>
				<div v-else class="text-xs text-ink-gray-5">No fingerprints recorded</div>
			</div>

			<div>
				<div class="text-sm text-ink-gray-5 mb-2">Emails linked to this customer</div>
				<div v-if="fraud.data.emails?.length" class="space-y-1">
					<div v-for="em in fraud.data.emails" :key="em" class="text-sm text-ink-gray-8 bg-surface-gray-2 p-2 rounded border border-outline-gray-2">
						{{ em }}
					</div>
				</div>
				<div v-else class="text-xs text-ink-gray-5">No emails recorded</div>
			</div>

			<div>
				<div class="text-sm text-ink-gray-5 mb-2">Addresses linked to this customer</div>
				<div v-if="fraud.data.addresses?.length" class="space-y-1">
					<div v-for="ad in fraud.data.addresses" :key="ad" class="text-sm text-ink-gray-8 bg-surface-gray-2 p-2 rounded border border-outline-gray-2">
						{{ ad }}
					</div>
				</div>
				<div v-else class="text-xs text-ink-gray-5">No addresses recorded</div>
			</div>
			
			<div v-if="fraud.data.linked_orders?.length">
				<div class="text-sm text-ink-gray-5 mt-4 mb-2">Orders by these devices (different accounts)</div>
				<div class="space-y-2">
					<router-link
						v-for="o in fraud.data.linked_orders"
						:key="o.name"
						:to="`/orders/${o.name}`"
						class="block border border-outline-gray-2 rounded p-2 hover:bg-surface-gray-2"
					>
						<div class="flex justify-between items-center">
							<span class="font-medium text-ink-gray-8">{{ o.name }}</span>
							<UiStatusBadge :label="`${o.custom_fraud_verdict} (${o.custom_fraud_score})`" :theme="o.custom_fraud_verdict === 'Pass' ? 'green' : 'red'" />
						</div>
						<div class="text-xs text-ink-gray-5 mt-1">{{ o.customer }}</div>
					</router-link>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed } from "vue"
import { Spinner, createResource } from "frappe-ui"
import UiStatusBadge from "@/components/UiStatusBadge.vue"

const props = defineProps<{ customer: string }>()

const fraud = createResource({
	url: "shop.api.fraud.get_customer_fraud_profile",
	makeParams: () => ({ customer: props.customer }),
	auto: true,
})
</script>
