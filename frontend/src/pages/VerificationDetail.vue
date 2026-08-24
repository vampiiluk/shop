<template>
	<div class="mx-auto max-w-5xl px-6 py-8">
		<CatalogListState
			:loading="detail.loading && !detail.data"
			:error="detail.error"
			empty-title=""
			@retry="detail.reload()"
		/>

		<div v-if="ver">
			<UiPageHeader :title="ver.address_line1 || ver.name" back-to="/verifications" back-label="Verifications">
				<template #badges>
					<UiStatusBadge :theme="statusTheme(ver.status)" :label="`Risk ${ver.address_risk_score ?? 0}/80 · ${ver.address_risk_status || '—'}`" />
					<UiStatusBadge :theme="statusTheme(ver.ors_status)" :label="`ORS ${ver.ors_status}`" />
					<UiStatusBadge :theme="statusTheme(ver.gms_status)" :label="`GMS ${ver.gms_status}`" />
				</template>
			</UiPageHeader>

			<div class="mt-6 grid gap-6 lg:grid-cols-3">
				<!-- Address + ORS -->
				<section class="rounded-lg border border-outline-gray-1 p-4 lg:col-span-2">
					<h2 class="text-base font-medium text-ink-gray-8">Address</h2>
					<div class="mt-3 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
						<div><span class="text-ink-gray-5">Line 1:</span> {{ ver.address_line1 }}</div>
						<div><span class="text-ink-gray-5">City:</span> {{ ver.city }}</div>
						<div><span class="text-ink-gray-5">Landmark:</span> {{ ver.landmark || '—' }}</div>
						<div><span class="text-ink-gray-5">Country:</span> {{ ver.country }}</div>
						<div><span class="text-ink-gray-5">Pincode:</span> {{ ver.pincode }}</div>
						<div><span class="text-ink-gray-5">Source:</span> {{ ver.source }}</div>
					</div>

					<div class="mt-4 border-t border-outline-gray-2 pt-3">
						<h3 class="text-sm font-medium text-ink-gray-7">ORS Geocoding</h3>
						<div v-if="orsResult" class="mt-2 grid grid-cols-2 gap-x-6 gap-y-2 text-sm">
							<div><span class="text-ink-gray-5">Label:</span> {{ orsResult.label || '—' }}</div>
							<div><span class="text-ink-gray-5">Confidence:</span> {{ orsResult.confidence ?? '—' }}</div>
							<div><span class="text-ink-gray-5">Match type:</span> {{ orsResult.match_type || '—' }}</div>
							<div>
								<span class="text-ink-gray-5">Coordinates:</span>
								<span v-if="ver.latitude != null">{{ ver.latitude }}, {{ ver.longitude }}</span>
								<span v-else>—</span>
							</div>
							<div><span class="text-ink-gray-5">Local area:</span> {{ orsResult.local_area || '—' }}</div>
							<div><span class="text-ink-gray-5">Admin area:</span> {{ orsResult.admin_area || '—' }}</div>
						</div>
						<p v-else-if="ver.ors_result_json" class="mt-2 text-sm text-ink-gray-5">Address not found by geocoder.</p>
						<p v-else class="mt-2 text-sm text-ink-gray-4">No ORS result yet.</p>
					</div>

					<div class="mt-4 border-t border-outline-gray-2 pt-3">
						<h3 class="text-sm font-medium text-ink-gray-7">
							Google Maps Results ({{ ver.gms_result_count || 0 }})
						</h3>
						<div v-if="gmsResults.length" class="mt-2 grid grid-cols-2 gap-2">
							<div
								v-for="(result, idx) in gmsResults"
								:key="idx"
								class="rounded border border-outline-gray-2 bg-surface-gray-2 p-2 text-xs"
							>
								<div class="font-medium text-ink-gray-8">{{ idx + 1 }}. {{ result.name }}</div>
								<div class="mt-0.5 text-ink-gray-6">{{ result.address }}</div>
								<div v-if="result.lat && result.lng" class="mt-0.5 text-ink-gray-5">
									{{ result.lat }}, {{ result.lng }}
									<a
										:href="`https://www.google.com/maps?q=${result.lat},${result.lng}`"
										target="_blank"
										class="ml-1 text-brand-blue hover:underline"
									>map</a>
								</div>
							</div>
						</div>
						<p v-else class="mt-2 text-sm text-ink-gray-4">No maps results recorded.</p>
					</div>

					<div v-if="riskSignals.length" class="mt-4 border-t border-outline-gray-2 pt-3">
						<h3 class="text-sm font-medium text-ink-gray-7">Risk Signals</h3>
						<table class="mt-2 w-full text-xs">
							<tbody>
								<tr
									v-for="signal in riskSignals"
									:key="signal.label"
									class="border-b border-outline-gray-2 last:border-b-0"
								>
									<td class="py-1.5 pr-3 font-medium" :class="signal.bad ? 'text-red-600' : 'text-ink-gray-6'">{{ signal.label }}</td>
									<td class="py-1.5 text-right text-ink-gray-7">{{ signal.value }}</td>
								</tr>
							</tbody>
						</table>
					</div>

					<details v-if="ver.ors_result_json || ver.gms_result_json || ver.address_risk_json" class="mt-4 border-t border-outline-gray-2 pt-3">
						<summary class="cursor-pointer text-sm font-medium text-ink-gray-7">Raw JSON</summary>
						<pre v-if="ver.address_risk_json" class="mt-2 max-h-48 overflow-auto rounded bg-surface-gray-2 p-2 text-xs text-ink-gray-7">risk: {{ formatJson(ver.address_risk_json) }}</pre>
						<pre v-if="ver.ors_result_json" class="mt-2 max-h-48 overflow-auto rounded bg-surface-gray-2 p-2 text-xs text-ink-gray-7">ors: {{ formatJson(ver.ors_result_json) }}</pre>
						<pre v-if="ver.gms_result_json" class="mt-2 max-h-48 overflow-auto rounded bg-surface-gray-2 p-2 text-xs text-ink-gray-7">gms: {{ formatJson(ver.gms_result_json) }}</pre>
					</details>
				</section>

				<!-- Side column -->
				<div class="space-y-6">
					<section class="rounded-lg border border-outline-gray-1 p-4">
						<h2 class="text-base font-medium text-ink-gray-8">Verification</h2>
						<div class="mt-3 space-y-2 text-sm">
							<div class="flex justify-between"><span class="text-ink-gray-5">Last verified</span><span>{{ fmtDate(ver.last_verified_on) }}</span></div>
							<div class="flex justify-between"><span class="text-ink-gray-5">Maps results</span><span>{{ ver.gms_result_count || 0 }}</span></div>
							<div class="flex items-center justify-between gap-2">
								<span class="shrink-0 text-ink-gray-5">Record</span>
								<a :href="`/app/shop-address-verification/${ver.name}`" target="_blank" class="truncate text-brand-blue hover:underline">{{ ver.name }}</a>
							</div>
						</div>
						<Button
							class="mt-4 w-full"
							variant="subtle"
							theme="amber"
							:disabled="ver.status === 'Queued'"
							:label="ver.status === 'Queued' ? 'Queued — waiting for Process Queue' : 'Add to verification queue'"
							:loading="reverifying"
							@click="reverify"
						/>
					</section>

					<section v-if="linkedOrders.length" class="rounded-lg border border-outline-gray-1 p-4">
						<h2 class="text-base font-medium text-ink-gray-8">Linked Orders</h2>
						<div class="mt-3 space-y-1">
							<router-link
								v-for="o in linkedOrders"
								:key="o.name"
								:to="`/orders/${o.name}`"
								class="flex items-center justify-between rounded bg-surface-gray-2 px-2.5 py-1.5 text-xs hover:bg-surface-gray-3"
							>
								<span class="font-medium text-ink-gray-8">{{ o.name }}</span>
								<span class="text-ink-gray-5">{{ o.customer }} &middot; {{ o.grand_total }}</span>
							</router-link>
						</div>
					</section>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { Button, createResource, toast } from 'frappe-ui'
import CatalogListState from '@/components/CatalogListState.vue'
import UiPageHeader from '@/components/UiPageHeader.vue'
import UiStatusBadge from '@/components/UiStatusBadge.vue'

const props = defineProps<{ name: string }>()

const detail = createResource({
	url: 'shop.api.verification.get_verification_detail',
	params: { name: props.name },
	auto: true,
})

const reverifying = ref(false)

const ver = computed(() => detail.data?.verification)
const linkedOrders = computed(() => detail.data?.linked_orders || [])

const orsResult = computed(() => parseJson(ver.value?.ors_result_json))
const gmsResults = computed<any[]>(() => {
	const parsed = parseJson(ver.value?.gms_result_json)
	return Array.isArray(parsed) ? parsed : []
})
const riskDetails = computed<Record<string, any>>(() => parseJson(ver.value?.address_risk_json) || {})

const SIGNAL_LABELS: Record<string, string> = {
	user_country_mismatch: 'Country mismatch (IP vs stated)',
	province_mismatch: 'Province mismatch',
	wrong_country: 'Wrong country',
	city_mismatch: 'City mismatch',
	geo_not_found: 'Geocoder found nothing',
	geo_unavailable: 'Geocoder unavailable',
	missing_landmark: 'Landmark missing',
	gms_landmark: 'Landmark confirmed on maps',
}

const riskSignals = computed(() => {
	const rows: { label: string; value: string; bad?: boolean }[] = []
	const d = riskDetails.value
	for (const [key, label] of Object.entries(SIGNAL_LABELS)) {
		if (!(key in d)) continue
		const val = d[key]
		if (typeof val === 'object' && val !== null && key === 'gms_landmark') {
			rows.push({
				label,
				value: val.matched ? `matched (${val.hits}/${val.total_results})` : `not matched (${val.hits}/${val.total_results})`,
				bad: !val.matched,
			})
		} else if (typeof val === 'boolean') {
			rows.push({ label, value: val ? 'yes' : 'no', bad: val })
		}
	}
	if (d.geo && typeof d.geo === 'object') {
		rows.push({ label: 'Geocode confidence', value: String(d.geo.confidence ?? '—'), bad: (d.geo.confidence ?? 0) < 0.5 })
	}
	return rows
})

function parseJson(raw?: string | null): any {
	if (!raw) return null
	try {
		return JSON.parse(raw)
	} catch {
		return null
	}
}

function formatJson(raw?: string | null): string {
	const parsed = parseJson(raw)
	return parsed ? JSON.stringify(parsed, null, 2) : raw || ''
}

function statusTheme(status?: string): string {
	switch (status) {
		case 'Complete': return 'green'
		case 'Partial': return 'blue'
		case 'Pending':
		case 'Queued': return 'amber'
		case 'Failed': return 'red'
		default: return 'gray'
	}
}

function fmtDate(value?: string): string {
	if (!value) return '—'
	return new Date(value).toLocaleString('en-GB', { timeZone: 'Asia/Karachi' })
}

async function reverify() {
	reverifying.value = true
	try {
		await fetch('/api/method/shop.api.verification.reverify_address', {
			method: 'POST',
			headers: {
				'Content-Type': 'application/json',
				'X-Frappe-CSRF-Token': (window as any).csrf_token || '',
			},
			body: JSON.stringify({ name: props.name }),
		})
		toast.create({ title: 'Added to queue — runs on the next queue cycle or via Process Queue', icon: 'clock', iconClasses: 'text-amber-600' })
		detail.reload()
	} finally {
		reverifying.value = false
	}
}
</script>
