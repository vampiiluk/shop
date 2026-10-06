<template>
	<div class="rounded-lg border border-outline-gray-1">
		<div class="flex items-center justify-between border-b border-outline-gray-1 px-4 py-2.5">
			<div class="flex items-center gap-2">
				<span class="text-sm font-medium text-ink-gray-8">Geocoder health</span>
				<span class="text-xs text-ink-gray-4">last {{ days }} days · {{ totalRecords }} record{{ totalRecords === 1 ? '' : 's' }} touched</span>
			</div>
			<div v-if="loading" class="text-xs text-ink-gray-4">Loading…</div>
			<div v-else-if="error" class="text-xs text-amber-600">{{ error }}</div>
		</div>

		<div v-if="!loading && !error" class="divide-y divide-outline-gray-1">
			<div v-for="p in providers" :key="p.key" class="flex items-start gap-4 px-4 py-3">
				<span
					class="mt-1.5 size-2.5 shrink-0 rounded-full"
					:class="dotClass(p.state)"
					:title="p.state"
				/>

				<div class="w-40 shrink-0">
					<div class="text-sm font-medium text-ink-gray-8">{{ p.name }}</div>
					<div class="text-xs text-ink-gray-5">
						{{ p.state === 'idle' ? 'not run' : pctLabel(p) }}
					</div>
				</div>

				<div class="min-w-0 flex-1">
					<!-- A usable-rate bar. It is deliberately a share of attempts
						that produced a real geocode, because that is the number
						that decides whether a score can be trusted; a plain
						success/failure split hides a 1-in-3 fallback rate inside
						"mostly fine". -->
					<div v-if="p.attempts" class="mb-1.5 flex h-1.5 w-full overflow-hidden rounded-full bg-surface-gray-3">
						<div class="bg-green-500" :style="{ width: share(p, 'usable') }" />
						<div class="bg-amber-400" :style="{ width: share(p, 'rejected') }" />
						<div class="bg-red-500" :style="{ width: share(p, 'failed') }" />
					</div>

					<div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-ink-gray-6">
						<span v-if="p.usable" class="text-green-700">{{ p.usable }} usable</span>
						<span v-if="p.rejected" class="text-amber-700">
							{{ p.rejected }} no usable match
						</span>
						<span v-if="p.failed" class="text-red-700">{{ p.failed }} call{{ p.failed === 1 ? '' : 's' }} failed</span>
						<span v-if="p.disabled" class="text-ink-gray-4">{{ p.disabled }} disabled</span>
						<span v-if="p.pending" class="text-ink-gray-4">{{ p.pending }} pending</span>
						<span v-if="!p.usable && !p.rejected && !p.failed && !p.pending && !p.disabled" class="text-ink-gray-4">
							Nothing to report
						</span>
						<span v-if="p.last_run" class="ml-auto text-ink-gray-4">{{ ago(p.last_run) }}</span>
					</div>

					<p class="mt-1 text-xs text-ink-gray-5">{{ p.note }}</p>
				</div>
			</div>

			<div class="flex items-center justify-between bg-surface-gray-2 px-4 py-2.5 text-xs">
				<span class="text-ink-gray-6">
					{{
						needsAttention
							? `${needsAttention} record${needsAttention === 1 ? '' : 's'} need${needsAttention === 1 ? 's' : ''} attention — a provider did not produce a usable result.`
							: 'Every record in this window was verified by both providers.'
					}}
				</span>
				<Button
					size="sm"
					variant="ghost"
					:disabled="!needsAttention"
					@click="$emit('attention')"
				>
					Show them
				</Button>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Button } from 'frappe-ui'

const props = defineProps<{ days?: number }>()
defineEmits<{ (e: 'attention'): void }>()

const csrfToken = computed(() => (window as any).csrf_token || '')
const days = props.days ?? 7

const loading = ref(true)
const error = ref('')
const data = ref<any>(null)

async function load() {
	loading.value = true
	error.value = ''
	try {
		const resp = await fetch(`/api/method/shop.api.verification.get_provider_health?days=${days}`, {
			headers: { 'X-Frappe-CSRF-Token': csrfToken.value },
		})
		const json = await resp.json()
		if (!json.message) throw new Error(json._server_messages || 'no response')
		data.value = json.message
	} catch (e: any) {
		error.value = 'Could not read provider health.'
	} finally {
		loading.value = false
	}
}

const providers = computed<any[]>(() => data.value?.providers ?? [])
const totalRecords = computed(() => data.value?.total_records ?? 0)
const needsAttention = computed(() => data.value?.needs_attention ?? 0)

function dotClass(state: string) {
	if (state === 'ok') return 'bg-green-500'
	if (state === 'warn') return 'bg-amber-400'
	if (state === 'down') return 'bg-red-500'
	// 'unknown' is grey, not amber. Too few attempts to call a trend is not a
	// warning, and a dot that cries wolf on a healthy provider is a dot you
	// learn to stop looking at.
	return 'bg-ink-gray-4'
}

function pctLabel(p: any) {
	if (p.usable_pct === null || p.usable_pct === undefined) return 'no attempts yet'
	return `${p.usable_pct}% usable`
}

// Widths are shares of attempts, not of the record total, so an unrun provider
// does not render a half-empty bar that reads as half-broken.
function share(p: any, kind: string) {
	if (!p.attempts) return '0%'
	return `${(100 * (p[kind] || 0)) / p.attempts}%`
}

function ago(value: string) {
	if (!value) return ''
	const then = new Date(value.endsWith('Z') || value.includes('+') ? value : `${value.replace(' ', 'T')}Z`)
	if (Number.isNaN(then.getTime())) return value
	const mins = Math.round((Date.now() - then.getTime()) / 60000)
	if (mins < 1) return 'just now'
	if (mins < 60) return `${mins} min ago`
	const hrs = Math.round(mins / 60)
	if (hrs < 24) return `${hrs} hr ago`
	return `${Math.round(hrs / 24)} d ago`
}

onMounted(load)
</script>