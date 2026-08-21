<template>
	<div class="mx-auto max-w-5xl px-6 py-8">
		<CatalogListState
			:loading="profile.loading && !profile.data"
			:error="profile.error"
			empty-title=""
			@retry="profile.reload()"
		/>

		<div v-if="profile.data">
			<UiPageHeader :title="name" back-to="/fraud" back-label="Fraud Overview">
				<template #badges>
					<UiStatusBadge :theme="verdictTheme" :label="`${profile.data.verdict} (${profile.data.score})`" />
					<UiStatusBadge
						v-if="fp && fp.suspect_score !== undefined"
						:theme="fp.suspect_score >= 0.8 ? 'red' : fp.suspect_score >= 0.5 ? 'orange' : 'green'"
						:label="`suspect ${Math.round(fp.suspect_score_raw ?? fp.suspect_score * 100)}/100`"
					/>
				</template>
			</UiPageHeader>

			<div class="mt-6 grid gap-6 lg:grid-cols-3">
				<!-- Main column -->
				<div class="space-y-6 lg:col-span-2">
					<section class="rounded-lg border border-outline-gray-1 p-4">
						<h2 class="text-base font-medium text-ink-gray-8">Snapshot — signals at placement</h2>
						<p class="mt-1 text-xs text-ink-gray-4">Frozen {{ profile.data.creation }}. This is what the engine knew when the order was placed.</p>
						<div class="mt-3">
							<SignalMatrix :signals="parsedSignals" />
						</div>
					</section>

					<section class="rounded-lg border border-outline-gray-1 p-4">
						<div class="flex items-center justify-between">
							<h2 class="text-base font-medium text-ink-gray-8">Fingerprint Identification event</h2>
							<Button size="sm" @click="showRaw = !showRaw">{{ showRaw ? 'Hide raw JSON' : 'Show raw JSON' }}</Button>
						</div>

						<div v-if="event.loading" class="mt-4 flex justify-center"><Spinner class="size-4" /></div>
						<template v-else>
							<div v-if="event.data?.event" class="mt-3">
								<p class="mb-3 text-xs text-ink-gray-4">
									Captured server-side from Fingerprint at checkout. Expand a group to inspect every field.
								</p>
								<JsonTree :data="event.data.event" :depth="0" />
							</div>
							<p v-else class="mt-3 text-sm text-ink-gray-5">
								No stored event (order placed before event capture was enabled).
							</p>
						</template>
					</section>
				</div>

				<!-- Side column -->
				<div class="space-y-6">
					<section class="rounded-lg border border-outline-gray-1 p-4">
						<h2 class="text-base font-medium text-ink-gray-8">Customer</h2>
						<router-link
							v-if="profile.data.customer"
							:to="`/customers/${profile.data.customer}`"
							class="mt-2 block text-base text-ink-gray-8 hover:underline"
						>
							{{ profile.data.customer }}
						</router-link>
						<div v-if="profile.data.phone" class="text-sm text-ink-gray-6">{{ profile.data.phone }}</div>
						<div v-if="profile.data.email" class="text-sm text-ink-gray-6">{{ profile.data.email }}</div>
						<div v-if="profile.data.fingerprint" class="mt-2 break-all font-mono text-xs text-ink-gray-7 bg-surface-gray-2 p-2 rounded border border-outline-gray-2">
							{{ profile.data.fingerprint }}
						</div>
					</section>

					<section v-if="live.data" class="rounded-lg border border-outline-gray-1 p-4">
						<h2 class="text-base font-medium text-ink-gray-8">Live check <span class="text-xs font-normal text-ink-gray-4">(now)</span></h2>
						<ul class="mt-3 space-y-2 text-sm">
							<li class="flex justify-between">
								<span class="text-ink-gray-6">Blacklisted now</span>
								<UiStatusBadge :label="live.data.blacklisted_now ? 'Yes' : 'No'" :theme="live.data.blacklisted_now ? 'red' : 'green'" />
							</li>
							<li class="flex justify-between">
								<span class="text-ink-gray-6">Failed deliveries</span>
								<span class="font-semibold text-ink-gray-8">{{ live.data.customer_failed_deliveries }}</span>
							</li>
							<li class="flex justify-between">
								<span class="text-ink-gray-6">Same phone ±60m of placement</span>
								<span class="font-semibold text-ink-gray-8">{{ live.data.velocity_window.phone_orders_within_60m_of_placement }}</span>
							</li>
							<li class="flex justify-between">
								<span class="text-ink-gray-6">Same device ±60m</span>
								<span class="font-semibold text-ink-gray-8">{{ live.data.velocity_window.device_orders_within_60m_of_placement }}</span>
							</li>
							<li class="flex justify-between">
								<span class="text-ink-gray-6">Orders on device since</span>
								<span class="font-semibold text-ink-gray-8">{{ live.data.velocity_window.same_device_orders_after }}</span>
							</li>
							<li class="flex justify-between">
								<span class="text-ink-gray-6">City RTO now ({{ live.data.city || '—' }})</span>
								<span class="font-semibold text-ink-gray-8">{{ live.data.city_rto_rate.toFixed(1) }}%</span>
							</li>
						</ul>
					</section>

					<section v-if="profile.data.fp_matches?.length" class="rounded-lg border border-outline-gray-1 p-4">
						<h2 class="text-base font-medium text-ink-gray-8">Other orders on this device</h2>
						<div class="mt-3 space-y-2">
							<router-link
								v-for="o in profile.data.fp_matches"
								:key="o.name"
								:to="`/orders/${o.name}`"
								class="block rounded border border-outline-gray-2 p-2 hover:bg-surface-gray-2"
							>
								<div class="flex justify-between items-center">
									<span class="font-medium text-ink-gray-8">{{ o.name }}</span>
									<UiStatusBadge :label="`${o.custom_fraud_verdict} (${o.custom_fraud_score})`" />
								</div>
								<div class="mt-0.5 text-xs text-ink-gray-5">{{ o.customer }}</div>
							</router-link>
						</div>
					</section>

					<section v-if="profile.data.address_matches?.length" class="rounded-lg border border-outline-gray-1 p-4">
						<h2 class="text-base font-medium text-ink-gray-8">Other orders to this address</h2>
						<div class="mt-3 space-y-2">
							<router-link
								v-for="o in profile.data.address_matches"
								:key="o.name"
								:to="`/orders/${o.name}`"
								class="block rounded border border-outline-gray-2 p-2 hover:bg-surface-gray-2"
							>
								<div class="flex justify-between items-center">
									<span class="font-medium text-ink-gray-8">{{ o.name }}</span>
									<UiStatusBadge :label="`${o.custom_fraud_verdict} (${o.custom_fraud_score})`" />
								</div>
								<div class="mt-0.5 text-xs text-ink-gray-5">{{ o.customer }}</div>
							</router-link>
						</div>
					</section>
				</div>
			</div>
		</div>

		<div v-else-if="!profile.loading" class="flex justify-center py-20">
			<Spinner class="size-5" />
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Button, Spinner, createResource } from 'frappe-ui'

import CatalogListState from '@/components/CatalogListState.vue'
import JsonTree from '@/components/JsonTree.vue'
import SignalMatrix from '@/components/SignalMatrix.vue'
import UiPageHeader from '@/components/UiPageHeader.vue'
import UiStatusBadge from '@/components/UiStatusBadge.vue'

const props = defineProps<{ name: string }>()

const showRaw = ref(false)

const profile = createResource({
	url: 'shop.api.fraud.get_order_fraud_profile',
	makeParams: () => ({ order: props.name }),
	auto: true,
})

const live = createResource({
	url: 'shop.api.fraud.get_live_check',
	makeParams: () => ({ order: props.name }),
	auto: true,
})

const event = createResource({
	url: 'shop.api.fraud.get_full_fp_event',
	makeParams: () => ({ order: props.name }),
	auto: true,
})

const parsedSignals = computed(() => {
	try {
		return JSON.parse(profile.data?.signals || '{}')
	} catch {
		return null
	}
})

const fp = computed(() => profile.data?.fp_highlights)

const verdictTheme = computed(() => {
	const verdict = profile.data?.verdict
	if (verdict === 'Block') return 'red'
	if (verdict === 'Advance Required') return 'orange'
	if (verdict === 'Flag') return 'gray'
	return 'green'
})
</script>
