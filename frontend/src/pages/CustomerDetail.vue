<template>
	<div class="mx-auto max-w-5xl px-6 py-8">
		<div v-if="doc">
			<UiPageHeader :title="doc.customer_name" back-to="/customers" back-label="Customers">
				<template #actions>
					<Button @click="$router.push({ name: 'Assistant', query: { message: `Analyze fraud risk for customer ${doc.name}` } })">
						AI Risk Score
					</Button>
					<Button :link="`/app/customer/${doc.name}`">Open in Desk</Button>
				</template>
			</UiPageHeader>

			<div class="mt-6 grid gap-6 lg:grid-cols-3">
				<div class="lg:col-span-2 space-y-6">
					<!-- Orders -->
					<div>
						<h2 class="mb-3 text-lg font-medium text-ink-gray-8">Orders</h2>
						<UiDataTable
							:columns="orderColumns"
							:rows="doc.orders"
							row-key="name"
							clickable
							@row-click="(row) => router.push(`/orders/${row.name}`)"
						>
							<template #cell-name="{ row }">
								<span class="font-medium text-ink-gray-8">{{ row.name }}</span>
							</template>
							<template #cell-status="{ row }">
								<UiStatusBadge :label="row.status" />
							</template>
							<template #empty>
								<UiEmptyState :icon="LucideShoppingCart" title="No orders yet" />
							</template>
						</UiDataTable>
					</div>

					<!-- Orders by these devices (different accounts) -->
					<div v-if="fraudProfile.data?.linked_orders?.length">
						<h2 class="mb-3 text-lg font-medium text-ink-gray-8">Orders by these devices <span class="text-sm font-normal text-ink-gray-5">(different accounts)</span></h2>
						<div class="space-y-2">
							<router-link
								v-for="o in fraudProfile.data.linked_orders"
								:key="o.name"
								:to="`/orders/${o.name}`"
								class="flex items-center justify-between border border-outline-gray-2 rounded-lg p-3 hover:bg-surface-gray-2 transition-colors"
							>
								<div>
									<span class="font-medium text-ink-gray-8">{{ o.name }}</span>
									<div class="text-xs text-ink-gray-5 mt-0.5">{{ o.customer }}</div>
								</div>
								<UiStatusBadge
									:label="`${o.custom_fraud_verdict} (${o.custom_fraud_score})`"
									:theme="verdictTheme(o.custom_fraud_verdict)"
								/>
							</router-link>
						</div>
					</div>
				</div>

				<div class="space-y-6">
					<!-- Profile -->
					<div class="rounded-lg border border-outline-gray-1 p-4">
						<h2 class="text-base font-medium text-ink-gray-8">Profile</h2>
						<div v-if="doc.email" class="mt-2 break-words text-p-base text-ink-gray-7">{{ doc.email }}</div>
						<div v-if="doc.all_emails?.length > 1" class="mt-2 space-y-1">
							<div v-for="em in doc.all_emails.slice(1)" :key="em" class="text-sm text-ink-gray-5">
								{{ em }}
							</div>
						</div>
						<div class="mt-1 text-sm text-ink-gray-5">Joined {{ formatDate(doc.joined) }}</div>
						<div class="mt-4 border-t border-outline-gray-1 pt-3">
							<div class="text-sm text-ink-gray-5">Lifetime spend</div>
							<div class="mt-0.5 text-xl font-semibold text-ink-gray-9">
								{{ doc.formatted_spent }}
							</div>
						</div>
					</div>

					<!-- Addresses -->
					<div class="rounded-lg border border-outline-gray-1 p-4">
						<h2 class="text-base font-medium text-ink-gray-8">Addresses &amp; Verification</h2>
						<div v-if="!doc.addresses.length && !fraudProfile.data?.addresses?.length" class="mt-2 text-sm text-ink-gray-5">
							No addresses on file
						</div>
						<div
							v-for="address in doc.addresses"
							:key="address.name"
							class="mt-2 border-t border-outline-gray-1 pt-2 text-p-sm text-ink-gray-6 first:border-t-0 first:pt-0"
						>
							<div v-html="address.display" />
							<div v-if="address.landmark" class="mt-1 text-xs text-ink-gray-5">
								Landmark: {{ address.landmark }}
							</div>
							<div v-if="address.verification_status" class="mt-1.5 flex flex-wrap items-center gap-2">
								<UiStatusBadge :label="address.verification_status" :theme="verifTheme(address.verification_status)" />
								<span v-if="address.risk_score != null" class="text-xs font-medium" :class="riskClass(address.risk_score)">
									Risk {{ address.risk_score }}/80
								</span>
								<span v-if="address.last_verified_on" class="text-xs text-ink-gray-5">
									verified {{ formatDate(address.last_verified_on) }}
								</span>
							</div>
						</div>
						<div v-if="fraudProfile.data?.addresses?.length" class="mt-3 border-t border-outline-gray-1 pt-3">
							<div class="text-xs font-medium text-ink-gray-5 mb-2">Additional addresses from device history</div>
							<div
								v-for="ad in fraudProfile.data.addresses"
								:key="ad"
								class="text-sm text-ink-gray-6 bg-surface-gray-2 p-2 rounded border border-outline-gray-2 mb-1"
							>
								{{ ad }}
							</div>
						</div>
					</div>

					<!-- Device Fingerprints -->
					<FraudCustomerPanel :customer="doc.name" />

					<!-- Reviews -->
					<div class="rounded-lg border border-outline-gray-1 p-4">
						<h2 class="text-base font-medium text-ink-gray-8">Reviews</h2>
						<div v-if="!doc.reviews.length" class="mt-2 text-sm text-ink-gray-5">
							No reviews yet
						</div>
						<div
							v-for="review in doc.reviews"
							:key="`${review.product}-${review.creation}`"
							class="mt-3 border-t border-outline-gray-1 pt-3 first:mt-2 first:border-t-0 first:pt-0"
						>
							<div class="flex items-center gap-0.5">
								<LucideStar
									v-for="starIndex in 5"
									:key="starIndex"
									class="size-3.5"
									:class="
										starIndex <= review.rating
											? 'fill-surface-gray-7 text-ink-gray-7'
											: 'text-ink-gray-3'
									"
								/>
							</div>
							<div v-if="review.title" class="mt-1 text-base text-ink-gray-8">
								{{ review.title }}
							</div>
							<div class="mt-0.5 text-sm text-ink-gray-5">
								{{ review.product }} &middot; {{ formatDate(review.creation) }}
							</div>
						</div>
					</div>
				</div>
			</div>
		</div>

		<div v-else class="flex justify-center py-20">
			<Spinner class="size-5" />
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Spinner, createResource, toast } from 'frappe-ui'
import { useRouter } from 'vue-router'

import LucideShoppingCart from '~icons/lucide/shopping-cart'
import LucideStar from '~icons/lucide/star'

import UiDataTable from '@/components/UiDataTable.vue'
import UiEmptyState from '@/components/UiEmptyState.vue'
import UiPageHeader from '@/components/UiPageHeader.vue'
import UiStatusBadge from '@/components/UiStatusBadge.vue'
import FraudCustomerPanel from '@/components/FraudCustomerPanel.vue'
import { formatDate } from '@/utils/format'
import { verdictTheme } from '@/utils/verdict'

const props = defineProps<{ name: string }>()

const router = useRouter()

const customer = createResource({
	url: 'shop.api.customers.get_customer',
	makeParams: () => ({ name: props.name }),
	auto: true,
	onError: () => toast.error('Could not load customer'),
})

const fraudProfile = createResource({
	url: 'shop.api.fraud.get_customer_fraud_profile',
	makeParams: () => ({ customer: props.name }),
	auto: true,
})

const doc = computed(() => customer.data)

const orderColumns = [
	{ key: 'name', label: 'Order' },
	{ key: 'transaction_date', label: 'Date', format: formatDate },
	{ key: 'status', label: 'Status' },
	{ key: 'formatted_total', label: 'Total', align: 'right' as const },
]

function verifTheme(status: string) {
	if (status === 'Complete') return 'green'
	if (status === 'Partial') return 'blue'
	if (status === 'Pending') return 'amber'
	return 'gray'
}

function riskClass(score: number) {
	if (score >= 50) return 'text-red-600'
	if (score >= 25) return 'text-amber-600'
	return 'text-green-700'
}
</script>
