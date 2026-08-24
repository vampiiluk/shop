<template>
	<div class="rounded-lg border border-outline-gray-1 p-4">
		<div class="flex justify-between items-start">
			<h2 class="text-base font-medium text-ink-gray-8">Fraud Intelligence</h2>
			<div v-if="fraud.data" class="flex items-center gap-2">
				<div class="flex flex-col gap-1 min-w-32 mr-2">
					<div class="flex justify-between text-xs font-semibold text-ink-gray-5">
						<span>At checkout</span>
						<span :class="verdictTextClass(fraud.data.verdict)">{{ fraud.data.verdict }} {{ fraud.data.score }}</span>
					</div>
					<div class="h-1.5 w-32 bg-surface-gray-3 rounded-full overflow-hidden flex">
						<div
							class="h-full transition-all duration-500 rounded-full"
							:class="verdictBarClass(fraud.data.verdict)"
							:style="{ width: `${Math.min(100, Math.max(5, fraud.data.score))}%` }"
						/>
					</div>
				</div>
			</div>
		</div>

		<div v-if="fraud.loading" class="mt-3 flex justify-center"><Spinner class="size-4" /></div>

		<div v-else-if="fraud.data" class="mt-3 space-y-2.5">
			<!-- Verification status — single check -->
			<div v-if="!verificationDone" class="flex items-center gap-2 text-xs">
				<span v-if="verificationPending" class="inline-flex items-center gap-1.5 rounded bg-orange-50 px-2 py-0.5 text-orange-700 border border-orange-200">
					<span class="inline-block size-1.5 rounded-full bg-orange-400 animate-pulse"></span>
					Address verification in progress
				</span>
				<span v-else class="inline-flex items-center gap-1.5 rounded bg-red-50 px-2 py-0.5 text-red-700 border border-red-200">
					Verification failed
				</span>
			</div>
			<div v-else-if="verificationStatus === 'Partial'" class="flex items-center gap-2 text-xs">
				<span class="inline-flex items-center gap-1.5 rounded bg-orange-50 px-2 py-0.5 text-orange-700 border border-orange-200">
					Address verification partial — score based on available data
				</span>
			</div>

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

			<!-- AI Risk Analysis (matches Fraud Detail page) -->
			<div v-if="verificationDone && fraud.data?.ai_risk_score" class="rounded-lg border border-outline-gray-1 p-4">
				<h2 class="text-base font-medium text-ink-gray-8">AI Risk Analysis</h2>
				<div class="mt-3 flex items-start gap-4">
					<div class="flex flex-col items-center">
						<span class="text-4xl font-bold" :class="aiScoreClass(fraud.data.ai_risk_score)">
							{{ fraud.data.ai_risk_score }}
						</span>
						<span class="text-xs text-ink-gray-5">/100</span>
						<span class="mt-1 text-xs text-ink-gray-5">{{ fraud.data.ai_risk_confidence }} confidence</span>
					</div>
					<div v-if="domainRows.length" class="w-full max-w-xs space-y-1.5">
						<div v-for="row in domainRows" :key="row.label" class="flex items-center gap-2">
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
				<p class="mt-3 text-sm text-ink-gray-7">{{ fraud.data.ai_risk_reasoning }}</p>
				<div v-if="fraud.data.ai_risk_analyzed_on" class="mt-2 text-xs text-ink-gray-4">
					Analyzed {{ formatDateTime(fraud.data.ai_risk_analyzed_on) }}
				</div>
			</div>
			<div v-else-if="verificationPending || !fraud.data?.ai_risk_score" class="rounded border border-dashed border-outline-gray-2 bg-surface-gray-2 px-3 py-3 text-center text-xs text-ink-gray-5">
				<span v-if="!verificationDone">Address verification in progress — Risk Score will appear once complete.</span>
				<span v-else>AI Risk Score not yet computed. Click Score Order Risk to analyze.</span>
			</div>

			<!-- Maps Verification Results -->
			<div v-if="mapsResults.length" class="space-y-1.5">
				<div class="text-xs text-ink-gray-5">Google Maps Verification</div>
				<div class="space-y-1">
					<div
						v-for="(result, idx) in mapsResults"
						:key="idx"
						class="bg-surface-gray-2 rounded px-2.5 py-1.5 border border-outline-gray-2 text-xs"
					>
						<div class="font-medium text-ink-gray-8">{{ idx + 1 }}. {{ result.name }}</div>
						<div class="text-ink-gray-6 mt-0.5">{{ result.address }}</div>
						<div class="flex gap-3 mt-0.5">
							<span v-if="result.category" class="text-ink-gray-5">{{ result.category }}</span>
							<span v-if="result.lat && result.lng" class="text-ink-gray-5">{{ result.lat }}, {{ result.lng }}</span>
						</div>
					</div>
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
import { verdictBarClass, verdictTextClass } from '@/utils/verdict'
import { formatDateTime } from '@/utils/format'

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

const aiRisk = createResource({
	url: 'frappe.client.get_value',
	makeParams: () => ({
		doctype: 'Sales Order',
		filters: { name: props.order },
		fieldname: ['custom_ai_maps_json', 'custom_ai_maps_status'],
	}),
	auto: true,
})

// Verification: single check — done or not
const verificationDone = computed(() => fraud.data?.verification_done || false)
const verificationStatus = computed(() => fraud.data?.verification_status || null)
const verificationPending = computed(() => !verificationDone.value && verificationStatus.value)

const domainRows = computed(() => {
	const labels: Record<string, string> = {
		address_consistency: 'Address consistency',
		device_trust: 'Device trust',
		behavioral: 'Behavioral',
		geographic: 'Geographic',
		payment: 'Payment',
	}
	const d = fraud.data?.ai_domain_scores
	if (!d || typeof d !== 'object') return []
	return Object.entries(d).map(([k, v]) => ({
		label: labels[k] || k.replace(/_/g, ' '),
		value: Math.round(Number(v) || 0),
	}))
})

interface MapsResult {
	name: string
	address: string
	category?: string
	lat?: string
	lng?: string
}

const mapsResults = computed<MapsResult[]>(() => {
	const raw = aiRisk.data?.custom_ai_maps_json
	if (!raw) return []
	try {
		const parsed = JSON.parse(raw)
		if (Array.isArray(parsed)) return parsed.slice(0, 4)
	} catch {}
	return []
})

function aiScoreClass(score: number): string {
	if (score >= 70) return 'text-red-600'
	if (score >= 40) return 'text-yellow-600'
	return 'text-green-600'
}

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
		rows.push({ label: 'Address risk', value: `${signals.address_score}/80` })
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
