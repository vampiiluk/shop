<template>
	<div class="mx-auto max-w-5xl px-6 py-8">
		<CatalogListState
			:loading="profile.loading && !profile.data"
			:error="profile.error"
			empty-title=""
			@retry="profile.reload()"
		/>

		<div v-if="profile.data">
			<UiPageHeader back-to="/fraud" back-label="Fraud Overview">
				<template #title>
					<router-link
						:to="`/orders/${name}`"
						class="text-xl font-semibold text-ink-gray-9 hover:text-brand-blue hover:underline"
						title="Open order detail"
					>
						{{ name }}
					</router-link>
				</template>
				<template #badges>
					<UiStatusBadge
						v-if="verificationPending"
						theme="amber"
						label="Detection in process"
					/>
					<UiStatusBadge
						v-else
						:theme="verdictTheme(profile.data.verdict)"
						:label="`${profile.data.verdict} (${profile.data.score})`"
					/>
					<UiStatusBadge
						v-if="fp && fp.suspect_score !== undefined"
						:theme="fp.suspect_score >= 0.8 ? 'red' : fp.suspect_score >= 0.5 ? 'orange' : 'green'"
						:label="`suspect ${Math.round(fp.suspect_score_raw ?? fp.suspect_score * 100)}/100`"
					/>
					<UiStatusBadge
						v-if="profile.data.ai_risk_score && verificationDone"
						:theme="profile.data.ai_risk_score >= 70 ? 'red' : profile.data.ai_risk_score >= 40 ? 'orange' : 'green'"
						:label="`AI ${profile.data.ai_risk_score}/100`"
					/>
					<UiStatusBadge
						v-if="verificationPending"
						theme="amber"
						label="Queued for verification"
					/>
					<UiStatusBadge
						v-else-if="verificationStatus === 'Partial'"
						theme="orange"
						label="Partial verification"
					/>
					<UiStatusBadge
						v-else-if="!verificationDone"
						theme="red"
						label="Verification failed"
					/>
				</template>
			</UiPageHeader>

			<div class="mt-6 grid gap-6 lg:grid-cols-3">
				<!-- Main column -->
				<div class="space-y-6 lg:col-span-2">
					<!-- AI Risk Score + Maps Verification -->
					<section v-if="verificationDone && profile.data.ai_risk_score" class="rounded-lg border border-outline-gray-1 p-4">
						<h2 class="text-base font-medium text-ink-gray-8">AI Risk Analysis</h2>
						<div class="mt-3 flex items-start gap-4">
							<div class="flex flex-col items-center">
								<span class="text-4xl font-bold" :class="aiScoreClass(profile.data.ai_risk_score)">
									{{ profile.data.ai_risk_score }}
								</span>
								<span class="text-xs text-ink-gray-5">/100</span>
								<span class="mt-1 text-xs text-ink-gray-5">{{ profile.data.ai_risk_confidence }} confidence</span>
							</div>
							<div v-if="domainScores" class="w-full max-w-xs space-y-1.5">
								<div v-for="(row, i) in domainRows" :key="i" class="flex items-center gap-2">
									<span class="w-32 shrink-0 text-xs capitalize text-ink-gray-6">{{ row.label }}</span>
									<div class="h-1.5 flex-1 overflow-hidden rounded-full bg-surface-gray-3">
										<div
											class="h-full rounded-full"
											:class="row.value >= 70 ? 'bg-red-500' : row.value >= 40 ? 'bg-amber-500' : 'bg-green-500'"
											:style="{ width: `${Math.min(100, row.value)}%` }"
										/>
									</div>
									<span class="w-7 text-right text-xs tabular-nums text-ink-gray-7">{{ row.value }}</span>
								</div>
							</div>
						</div>
						<p class="mt-3 text-sm text-ink-gray-7">{{ profile.data.ai_risk_reasoning }}</p>
						<div v-if="profile.data.ai_risk_analyzed_on" class="mt-2 text-xs text-ink-gray-4">
							Analyzed {{ profile.data.ai_risk_analyzed_on }}
						</div>

						<!-- Maps Verification Results -->
						<div v-if="mapsResults.length" class="mt-4 border-t border-outline-gray-2 pt-3">
							<h3 class="text-sm font-medium text-ink-gray-7">Google Maps Verification</h3>
							<div class="mt-2 grid grid-cols-2 gap-2">
								<div
									v-for="(result, idx) in mapsResults"
									:key="idx"
									class="rounded border border-outline-gray-2 p-2 bg-surface-gray-2"
								>
									<div class="text-xs font-medium text-ink-gray-8">{{ idx + 1 }}. {{ result.name }}</div>
									<div class="mt-0.5 text-xs text-ink-gray-6">{{ result.address }}</div>
									<div v-if="result.lat && result.lng" class="mt-0.5 text-xs text-ink-gray-5">
										{{ result.lat }}, {{ result.lng }}
										<a :href="`https://www.google.com/maps?q=${result.lat},${result.lng}`" target="_blank" class="text-brand-blue hover:underline ml-1">map</a>
									</div>
								</div>
							</div>
						</div>
					</section>
					<section v-else class="rounded-lg border border-dashed border-outline-gray-2 p-6 text-center">
						<div v-if="verificationPending" class="space-y-2">
							<span class="inline-block size-5 rounded-full bg-orange-100 text-orange-600 animate-pulse">...</span>
							<p class="text-sm text-ink-gray-6">Address verification in progress</p>
							<p class="text-xs text-ink-gray-4">AI Risk Score will appear once ORS and GMS complete.</p>
						</div>
						<div v-else-if="!profile.data.ai_risk_score" class="space-y-2">
							<p class="text-sm text-ink-gray-6">AI Risk Score not yet computed.</p>
							<p class="text-xs text-ink-gray-4">Use the Score Order Risk tool to analyze.</p>
						</div>
					</section>

					<!-- Score Calculation Breakdown -->
					<section class="rounded-lg border border-outline-gray-1 p-4">
						<h2 class="text-base font-medium text-ink-gray-8">Score Calculation</h2>
						<p class="mt-1 text-xs text-ink-gray-4">How the fraud score was computed from individual signals.</p>
						<div class="mt-3 space-y-1.5">
							<div
								v-for="row in scoreBreakdown"
								:key="row.label"
								class="flex items-center justify-between rounded bg-surface-gray-2 px-2.5 py-1.5 border border-outline-gray-2 text-sm"
							>
								<span class="text-xs text-ink-gray-6">{{ row.label }}</span>
								<div class="flex items-center gap-2">
									<span class="text-xs text-ink-gray-5">{{ row.weight }}</span>
									<span class="font-semibold" :class="row.value > 0 ? 'text-red-600' : 'text-green-600'">
										{{ row.value > 0 ? '+' : '' }}{{ row.value }}
									</span>
								</div>
							</div>
							<div class="flex items-center justify-between rounded bg-surface-gray-3 px-2.5 py-1.5 border border-outline-gray-2 text-sm font-medium">
								<span class="text-ink-gray-8">Total</span>
								<span class="text-ink-gray-9">{{ profile.data.score }}</span>
							</div>
						</div>
					</section>

					<!-- Snapshot — signals at placement -->
					<section class="rounded-lg border border-outline-gray-1 p-4">
						<h2 class="text-base font-medium text-ink-gray-8">Snapshot — signals at placement</h2>
						<p class="mt-1 text-xs text-ink-gray-4">Frozen {{ profile.data.creation }}. This is what the engine knew when the order was placed.</p>
						<div class="mt-3">
							<SignalMatrix :signals="parsedSignals" />
						</div>
					</section>

					<!-- Fingerprint Identification event -->
					<section class="rounded-lg border border-outline-gray-1 p-4">
						<div class="flex items-center justify-between">
							<h2 class="text-base font-medium text-ink-gray-8">Fingerprint Identification event</h2>
							<Button size="sm" @click="showRaw = !showRaw">{{ showRaw ? 'Show tree' : 'Show raw JSON' }}</Button>
						</div>

						<div v-if="event.loading" class="mt-4 flex justify-center"><Spinner class="size-4" /></div>
						<template v-else>
							<div v-if="event.data?.event" class="mt-3">
								<p v-if="!showRaw" class="mb-3 text-xs text-ink-gray-4">
									Captured server-side from Fingerprint at checkout. Expand a group to inspect every field.
								</p>
								<pre v-if="showRaw" class="max-h-96 overflow-auto rounded bg-surface-gray-2 p-3 text-xs text-ink-gray-8 border border-outline-gray-2">{{ JSON.stringify(event.data.event, null, 2) }}</pre>
								<JsonTree v-else :data="event.data.event" :depth="0" />
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
									<UiStatusBadge
										:theme="verdictTheme(o.custom_fraud_verdict)"
										:label="`${o.custom_fraud_verdict} (${o.custom_fraud_score})`"
									/>
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
									<UiStatusBadge
										:theme="verdictTheme(o.custom_fraud_verdict)"
										:label="`${o.custom_fraud_verdict} (${o.custom_fraud_score})`"
									/>
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
import { verdictTheme } from '@/utils/verdict'

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

// Verification: single check — done or not
const verificationDone = computed(() => profile.data?.verification_done || false)
const verificationStatus = computed(() => profile.data?.verification_status || null)
const verificationPending = computed(() => !verificationDone.value && verificationStatus.value)

const domainScores = computed<Record<string, number> | null>(() => {
	const d = profile.data?.ai_domain_scores
	return d && typeof d === 'object' && Object.keys(d).length ? d : null
})

const domainRows = computed(() => {
	const labels: Record<string, string> = {
		address_consistency: 'Address consistency',
		device_trust: 'Device trust',
		behavioral: 'Behavioral',
		geographic: 'Geographic',
		payment: 'Payment',
	}
	return Object.entries(domainScores.value || {}).map(([k, v]) => ({
		label: labels[k] || k.replace(/_/g, ' '),
		value: Math.round(Number(v) || 0),
	}))
})

const parsedSignals = computed(() => {
	try {
		return JSON.parse(profile.data?.signals || '{}')
	} catch {
		return null
	}
})

const fp = computed(() => profile.data?.fp_highlights)

interface MapsResult {
	name: string
	address: string
	category?: string
	lat?: string
	lng?: string
}

const mapsResults = computed<MapsResult[]>(() => {
	const raw = profile.data?.ai_maps_json
	if (!raw) return []
	try {
		const parsed = JSON.parse(raw)
		if (Array.isArray(parsed)) return parsed.slice(0, 4)
	} catch {}
	return []
})

interface ScoreRow {
	label: string
	weight: string
	value: number
}

const scoreBreakdown = computed<ScoreRow[]>(() => {
	const signals = parsedSignals.value
	if (!signals) return []

	const rows: ScoreRow[] = []

	const add = (label: string, weight: string, value: number) => {
		if (value !== undefined && value !== null) rows.push({ label, weight, value: Math.round(value) })
	}

	// Core signals
	add('Suspect score', '×100', Math.round((signals.fp_suspect_score || 0) * 100))
	add('Address risk', '/80', signals.address_score || 0)
	add('City RTO rate', '%', signals.city_rto_rate || 0)

	// Fingerprint signals
	add('Proxy detected', '', signals.fp_proxy ? 15 : 0)
	add('VPN detected', '', signals.fp_vpn ? 15 : 0)
	add('Bot detected', '', signals.fp_bot === 'detected' ? 25 : 0)
	add('Datacenter IP', '', signals.fp_datacenter ? 15 : 0)
	add('High activity device', '', signals.fp_high_activity_device ? 25 : 0)
	add('VM detected', '', signals.fp_virtual_machine ? 15 : 0)

	// Velocity
	add('Orders ±60m', '', signals.orders_last_60m || 0)
	add('Device orders ±60m', '', signals.fp_orders_last_60m || 0)

	// History
	if (signals.repeat_history) {
		const h = signals.repeat_history
		const bad = (h.failed || 0) + (h.rto || 0) + (h.cancelled || 0)
		add('Repeat failures', '', bad * 10)
	}

	// Multiple phones
	add('Multiple phones', '', signals.fp_multiple_phones ? 10 : 0)

	return rows
})

function aiScoreClass(score: number): string {
	if (score >= 70) return 'text-red-600'
	if (score >= 40) return 'text-yellow-600'
	return 'text-green-600'
}
</script>
