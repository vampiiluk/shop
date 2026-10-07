<template>
	<div class="mx-auto max-w-5xl px-6 py-8">
		<UiPageHeader title="Verifications">
			<template #actions>
				<Button @click="showVImport = true" variant="subtle">
					<template #prefix><span class="lucide-upload size-4" /></template>
					Import CSV
				</Button>
				<Button @click="handleVExport" :loading="vExporting" variant="subtle">
					<template #prefix><span class="lucide-download size-4" /></template>
					Export CSV
				</Button>
				<Button @click="handleProcessQueue" :loading="queueStarting" :disabled="queueRunning" variant="subtle" theme="amber">
					<template #prefix><span class="lucide-refresh-cw size-4" /></template>
					{{ queueRunning ? 'Queue Running…' : 'Process Queue' }}
				</Button>
			</template>
		</UiPageHeader>

			<div class="mt-6">
				<ProviderHealthStrip @attention="showAttentionOnly" />
			</div>

			<div class="mb-6 mt-6 grid grid-cols-4 gap-4">
				<div class="rounded-lg border border-outline-gray-1 p-4">
					<div class="text-sm text-ink-gray-5">Total Addresses</div>
					<div class="mt-1 text-2xl font-bold text-ink-gray-9">{{ vStats.total }}</div>
				</div>
				<div class="rounded-lg border border-outline-gray-1 p-4">
					<div class="text-sm text-ink-gray-5">ORS Verified</div>
					<div class="mt-1 text-2xl font-bold text-green-600">{{ vStats.ors_complete }}</div>
				</div>
				<div class="rounded-lg border border-outline-gray-1 p-4">
					<div class="text-sm text-ink-gray-5">GMS Verified</div>
					<div class="mt-1 text-2xl font-bold text-green-600">{{ vStats.gms_complete }}</div>
				</div>
				<div class="rounded-lg border border-outline-gray-1 p-4">
					<div class="text-sm text-ink-gray-5">Pending / Failed</div>
					<div class="mt-1 text-2xl font-bold text-amber-600">{{ vStats.ors_pending + vStats.gms_pending }}</div>
				</div>
			</div>

			<div v-if="queueRunning || queuePending > 0" class="mb-4 flex items-center gap-3 rounded-lg border border-outline-gray-1 bg-surface-gray-2 px-4 py-2.5 text-sm text-ink-gray-7">
				<Spinner v-if="queueRunning" class="size-4" />
				<span>
					{{
						queueRunning
							? `Processing verification queue — ${queuePending} address${queuePending === 1 ? '' : 'es'} remaining`
							: `${queuePending} address${queuePending === 1 ? '' : 'es'} awaiting verification — press Process Queue to start`
					}}
				</span>
			</div>

			<div class="mb-4 flex flex-wrap items-center gap-3">
				<Input v-model="vFilters.search" placeholder="Search addresses..." class="w-64" @input="loadVerifications" />
				<Select v-model="vFilters.ors_status" :options="vOrsStatusOptions" placeholder="ORS Status" class="w-40" @change="loadVerifications" />
				<Select v-model="vFilters.gms_status" :options="vGmsStatusOptions" placeholder="GMS Status" class="w-40" @change="loadVerifications" />
				<Select v-model="vFilters.source" :options="vSourceOptions" placeholder="Source" class="w-40" @change="loadVerifications" />
				<Select v-model="vFilters.review_state" :options="vReviewOptions" placeholder="Review" class="w-40" @change="loadVerifications" />
				<button
					type="button"
					class="flex items-center gap-1.5 rounded-md border px-3 py-1.5 text-sm transition-colors"
					:class="vFilters.needs_attention
						? 'border-amber-300 bg-amber-50 text-amber-800'
						: 'border-outline-gray-2 text-ink-gray-6 hover:bg-surface-gray-2'"
					@click="toggleAttention"
				>
					<span class="lucide-triangle-alert size-4" />
					Needs attention
					<span v-if="vAttentionCount" class="rounded bg-amber-200/70 px-1.5 text-xs font-medium text-amber-900">
						{{ vAttentionCount }}
					</span>
				</button>
				<Button v-if="vHasFilters" variant="ghost" size="sm" @click="clearVFilters">Clear</Button>
			</div>

			<!-- overflow-x-auto so a wider cell scrolls instead of clipping. Nine
				columns at max-w-5xl leave ~20px of slack, and when the ORS cell
				grew to two lines the table went past it and the Re-verify button -
				the only action on the row - was cut off with no scrollbar to find it. -->
			<div class="overflow-x-auto rounded-lg border border-outline-gray-1">
				<div v-if="vLoading" class="flex justify-center py-12">
					<Spinner class="size-5" />
				</div>
				<table v-else class="w-full text-sm">
					<thead>
						<tr class="border-b border-outline-gray-1 bg-surface-gray-2">
							<th class="px-3 py-2 text-left font-medium text-ink-gray-6">Address</th>
							<th class="px-3 py-2 text-left font-medium text-ink-gray-6">City</th>
							<th class="px-3 py-2 text-left font-medium text-ink-gray-6">Landmark</th>
							<th class="px-3 py-2 text-center font-medium text-ink-gray-6">ORS</th>
							<th class="px-3 py-2 text-center font-medium text-ink-gray-6">GMS</th>
							<th class="px-3 py-2 text-center font-medium text-ink-gray-6">Review</th>
							<th class="px-3 py-2 text-center font-medium text-ink-gray-6">Results</th>
							<th class="px-3 py-2 text-left font-medium text-ink-gray-6">Source</th>
							<th class="px-3 py-2 text-left font-medium text-ink-gray-6">Linked Orders</th>
							<th class="px-3 py-2 text-left font-medium text-ink-gray-6">Actions</th>
						</tr>
					</thead>
					<tbody>
						<tr
							v-for="row in vRows"
							:key="row.name"
							class="border-b border-outline-gray-1 hover:bg-surface-gray-2 cursor-pointer"
							@click="$router.push(`/verifications/${row.name}`)"
						>
							<!-- max-w-[17rem] rather than max-w-xs (20rem): with nine columns the table
								wanted 996px inside a 974px card, and the extra 48px came straight
								out of this column. The address is already truncated with an
								ellipsis and the full text is on the detail page, so nothing is lost. -->
							<td class="max-w-[17rem] truncate px-3 py-2" :title="row.address_line1">{{ row.address_line1 }}</td>
							<td class="px-3 py-2">{{ row.city }}</td>
							<td class="px-3 py-2">{{ row.landmark }}</td>
							<td class="px-3 py-2 text-center">
								<!-- "Failed" is two different problems wearing one word: the call
									erroring, and the geocoder answering confidently with the wrong
									place. Only the second is a rejection, and it is the one worth
									spotting, because the score was written as if the customer were
									risky when the provider was simply wrong. -->
								<template v-if="row.ors_rejected">
									<UiStatusBadge theme="amber" label="Rejected" />
									<div class="mt-0.5 whitespace-nowrap text-[11px] text-ink-gray-4" :title="orsRejectionTitle(row)">no match</div>
								</template>
								<UiStatusBadge v-else :theme="statusTheme(row.ors_status)" :label="row.ors_status" />
							</td>
							<td class="px-3 py-2 text-center">
								<UiStatusBadge :theme="statusTheme(row.gms_status)" :label="row.gms_status" />
							</td>
							<td class="px-3 py-2 text-center">
								<UiStatusBadge :theme="reviewTheme(row.review_state)" :label="row.review_state" />
								<div v-if="row.reviewed_by" class="mt-0.5 text-[11px] text-ink-gray-4">{{ row.reviewed_by }}</div>
							</td>
							<td class="px-3 py-2 text-center text-ink-gray-6">{{ row.gms_result_count || 0 }}</td>
							<td class="px-3 py-2 text-ink-gray-6">{{ row.source }}</td>
							<td class="px-3 py-2 text-ink-gray-6">{{ countLinks(row.linked_orders) }}</td>
							<td class="px-3 py-2" @click.stop>
								<Button
									size="sm"
									variant="ghost"
									:disabled="row.status === 'Queued' || reverifyBusy === row.name"
									:label="row.status === 'Queued' ? 'Queued' : (reverifyBusy === row.name ? 'Adding…' : 'Re-verify')"
									@click="handleReverify(row.name)"
								/>
							</td>
						</tr>
						<tr v-if="!vRows.length">
							<td colspan="10" class="px-3 py-8 text-center text-ink-gray-4">No verification records found</td>
						</tr>
					</tbody>
				</table>
			</div>

			<div v-if="vTotal > vPageSize" class="mt-4 flex items-center justify-between">
				<span class="text-sm text-ink-gray-5">Showing {{ vOffset + 1 }}-{{ Math.min(vOffset + vPageSize, vTotal) }} of {{ vTotal }}</span>
				<div class="flex gap-2">
					<Button size="sm" :disabled="vOffset === 0" @click="vPrevPage">Previous</Button>
					<Button size="sm" :disabled="vOffset + vPageSize >= vTotal" @click="vNextPage">Next</Button>
				</div>
			</div>

		<Dialog v-model:show="showVImport" title="Import Verification CSV" size="lg">
			<div class="space-y-4">
				<p class="text-sm text-ink-gray-6">Upload a CSV exported from another instance. All data is pre-verified -- no background jobs needed.</p>
				<textarea
					v-model="importContent"
					class="w-full rounded border border-outline-gray-2 p-3 font-mono text-xs"
					rows="10"
					placeholder="Paste CSV content here..."
				/>
				<div v-if="importResult" class="rounded bg-surface-gray-2 p-3 text-sm">
					<div>Imported: {{ importResult.imported }}</div>
					<div>Updated: {{ importResult.updated }}</div>
					<div>Skipped: {{ importResult.skipped }}</div>
					<div v-if="importResult.errors?.length" class="mt-2 text-red-600">
						Errors: {{ importResult.errors.join(', ') }}
					</div>
				</div>
				<div class="flex justify-end gap-2">
					<Button variant="subtle" @click="showVImport = false">Cancel</Button>
					<Button :loading="importing" @click="handleVImport">Import</Button>
				</div>
			</div>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted } from 'vue'
import { Button, Dialog, Input, Select, Spinner, createResource, toast } from 'frappe-ui'
import UiPageHeader from '@/components/UiPageHeader.vue'
import UiStatusBadge from '@/components/UiStatusBadge.vue'
import ProviderHealthStrip from '@/components/ProviderHealthStrip.vue'

const csrfToken = computed(() => (window as any).csrf_token || '')

const headers = computed(() => ({
	'Content-Type': 'application/json',
	'X-Frappe-CSRF-Token': csrfToken.value,
}))

// ── Verifications ──

const vLoading = ref(true)
const vRows = ref<any[]>([])
const vTotal = ref(0)
const vOffset = ref(0)
const vPageSize = 50
const vFilters = ref({ search: '', ors_status: '', gms_status: '', source: '', review_state: '', needs_attention: '' })

const vHasFilters = computed(() =>
	!!(
		vFilters.value.search
		|| vFilters.value.ors_status
		|| vFilters.value.gms_status
		|| vFilters.value.source
		|| vFilters.value.review_state
		|| vFilters.value.needs_attention
	)
)

// Mirrors the count the health strip reports, so the filter chip can show what
// it would select without a second round trip.
const vAttentionCount = ref(0)

function toggleAttention() {
	vFilters.value.needs_attention = vFilters.value.needs_attention ? '' : '1'
	vOffset.value = 0
	loadVerifications()
}

function showAttentionOnly() {
	vFilters.value.needs_attention = '1'
	vOffset.value = 0
	loadVerifications()
}

const vOrsStatusOptions = [
	{ label: 'All', value: '' },
	{ label: 'Complete', value: 'Complete' },
	{ label: 'Pending', value: 'Pending' },
	{ label: 'Failed', value: 'Failed' },
	{ label: 'Skipped', value: 'Skipped' },
]
const vGmsStatusOptions = [
	{ label: 'All', value: '' },
	{ label: 'Complete', value: 'Complete' },
	{ label: 'Pending', value: 'Pending' },
	{ label: 'Failed', value: 'Failed' },
	{ label: 'Disabled', value: 'Disabled' },
]
const vReviewOptions = [
	{ label: 'All', value: '' },
	{ label: 'Unreviewed', value: 'Unreviewed' },
	{ label: 'Verified', value: 'Verified' },
	{ label: 'Rejected', value: 'Rejected' },
	{ label: 'Needs lookup', value: 'Needs Lookup' },
]
const vSourceOptions = [
	{ label: 'All', value: '' },
	{ label: 'Order Placement', value: 'Order Placement' },
	{ label: 'Manual', value: 'Manual' },
	{ label: 'Bulk Import', value: 'Bulk Import' },
]

const vStats = ref<Record<string, number>>({ total: 0, ors_complete: 0, gms_complete: 0, ors_pending: 0, gms_pending: 0 })
const vStatsRes = createResource({
	url: 'shop.api.verification.get_stats',
	auto: false,
	onSuccess(data: any) {
		vStats.value = data.stats || data
	},
})

async function fetchVData() {
	const params = new URLSearchParams()
	if (vFilters.value.search) params.set('search', vFilters.value.search)
	if (vFilters.value.ors_status) params.set('ors_status', vFilters.value.ors_status)
	if (vFilters.value.gms_status) params.set('gms_status', vFilters.value.gms_status)
	if (vFilters.value.source) params.set('source', vFilters.value.source)
	if (vFilters.value.review_state) params.set('review_state', vFilters.value.review_state)
	if (vFilters.value.needs_attention) params.set('needs_attention', vFilters.value.needs_attention)
	params.set('limit', String(vPageSize))
	params.set('offset', String(vOffset.value))
	const resp = await fetch(`/api/method/shop.api.verification.get_verifications?${params.toString()}`, {
		headers: { 'X-Frappe-CSRF-Token': csrfToken.value },
	})
	const json = await resp.json()
	return json.message || { rows: [], total: 0 }
}

async function loadVerifications() {
	vLoading.value = true
	try {
		await vStatsRes.fetch()
		const data = await fetchVData()
		vRows.value = data.rows
		vTotal.value = data.total
		// The attention count is the unfiltered size of that set, so read it from
		// the stats endpoint rather than from the current rows, which may be a
		// filtered and paginated page.
		await refreshAttentionCount()
	} finally {
		vLoading.value = false
	}
}

async function refreshAttentionCount() {
	try {
		const resp = await fetch('/api/method/shop.api.verification.get_provider_health?days=7', {
			headers: { 'X-Frappe-CSRF-Token': csrfToken.value },
		})
		const json = await resp.json()
		vAttentionCount.value = json.message?.needs_attention ?? 0
	} catch {
		vAttentionCount.value = 0
	}
}

function clearVFilters() {
	vFilters.value = { search: '', ors_status: '', gms_status: '', source: '', review_state: '', needs_attention: '' }
	vOffset.value = 0
	loadVerifications()
}function vPrevPage() {
	vOffset.value = Math.max(0, vOffset.value - vPageSize)
	loadVerifications()
}
function vNextPage() {
	vOffset.value += vPageSize
	loadVerifications()
}

function reviewTheme(state: string) {
	if (state === 'Verified') return 'green'
	if (state === 'Rejected') return 'red'
	if (state === 'Needs Lookup') return 'amber'
	return 'gray'
}

function statusTheme(status: string) {
	if (status === 'Complete') return 'green'
	if (status === 'Pending' || status === 'Queued') return 'amber'
	if (status === 'Failed') return 'red'
	return 'gray'
}

const REJECTION_HINTS: Record<string, string> = {
	fallback_match: 'The geocoder returned a fallback match — a fallback is not a location. It found no street and gave back something plausible anyway.',
	country_mismatch: 'The geocode resolved to a country this shop does not deliver to.',
	not_found: 'The geocoder returned no result for this address.',
}

function orsRejectionTitle(row: any) {
	return (
		REJECTION_HINTS[row.ors_rejection_reason]
		?? 'The geocoder answered, but not with this address. Nothing was charged to the customer for it.'
	)
}

function countLinks(orders: string) {
	if (!orders) return 0
	return orders.split(',').filter((o: string) => o.trim()).length
}

const reverifyBusy = ref<string | null>(null)

async function handleReverify(name: string) {
	reverifyBusy.value = name
	try {
		await fetch('/api/method/shop.api.verification.reverify_address', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': csrfToken.value },
			body: JSON.stringify({ name }),
		})
		toast.create({ title: 'Added to queue — press Process Queue to run it', icon: 'clock', iconClasses: 'text-amber-600' })
		await loadVerifications()
	} finally {
		reverifyBusy.value = null
	}
}

// ── Queue ──

const queueStarting = ref(false)
const queueRunning = ref(false)
const queuePending = ref(0)
let queueTimer: number | null = null

async function pollQueue() {
	try {
		const resp = await fetch('/api/method/shop.api.verification.get_queue_status', {
			headers: { 'X-Frappe-CSRF-Token': csrfToken.value },
		})
		const json = await resp.json()
		const st = json.message || {}
		queueRunning.value = !!st.running
		queuePending.value = st.pending || 0
		if (!st.running && queueTimer) {
			stopQueuePolling()
			loadVerifications()
		}
	} catch {
		// transient network errors — next tick retries
	}
}

function startQueuePolling() {
	if (queueTimer) return
	queueTimer = window.setInterval(pollQueue, 5000)
}

function stopQueuePolling() {
	if (queueTimer) {
		window.clearInterval(queueTimer)
		queueTimer = null
	}
}

async function handleProcessQueue() {
	queueStarting.value = true
	try {
		await fetch('/api/method/shop.api.verification.run_queue', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': csrfToken.value },
			body: JSON.stringify({}),
		})
		queueRunning.value = true
		startQueuePolling()
	} finally {
		queueStarting.value = false
	}
}

const vExporting = ref(false)
async function handleVExport() {
	vExporting.value = true
	try {
		await fetch('/api/method/shop.api.verification.export_csv', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': csrfToken.value },
			body: JSON.stringify({ filters: vFilters.value }),
		})
		setTimeout(async () => {
			const resp = await fetch('/api/method/shop.api.verification.get_export_status', {
				headers: { 'X-Frappe-CSRF-Token': csrfToken.value },
			})
			const json = await resp.json()
			if (json.message?.url) {
				window.open(json.message.url, '_blank')
			}
		}, 3000)
	} finally {
		vExporting.value = false
	}
}

const showVImport = ref(false)
const importContent = ref('')
const importing = ref(false)
const importResult = ref<any>(null)

async function handleVImport() {
	if (!importContent.value.trim()) return
	importing.value = true
	try {
		const resp = await fetch('/api/method/shop.api.verification.import_csv', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json', 'X-Frappe-CSRF-Token': csrfToken.value },
			body: JSON.stringify({ csv_content: importContent.value }),
		})
		const json = await resp.json()
		importResult.value = json.message
		loadVerifications()
	} finally {
		importing.value = false
	}
}

// ── Init ──

onMounted(async () => {
	loadVerifications()
	await pollQueue()
	if (queueRunning.value) startQueuePolling()
})

onUnmounted(stopQueuePolling)
</script>
