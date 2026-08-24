<template>
	<div class="mx-auto max-w-5xl px-6 py-8">
		<UiPageHeader title="Fraud Overview" />

		<CatalogListState
			:loading="overview.loading && !overview.data"
			:error="overview.error"
			empty-title=""
			@retry="overview.reload()"
		/>

		<template v-if="overview.data">
			<!-- KPI cards -->
			<div class="mt-6 grid gap-4 sm:grid-cols-3">
				<div
					v-for="(label, key) in { today: 'Today', week: 'This week', month: 'This month' }"
					:key="key"
					class="rounded-lg border border-outline-gray-1 p-4"
				>
					<div class="flex items-baseline justify-between">
						<div class="text-p-sm text-ink-gray-5">{{ label }}</div>
						<div v-if="kpi(key).total" class="text-xs text-ink-gray-5">
							avg {{ kpi(key).avg_score }} · {{ fingerprintedPct(key) }}% fingerprinted
						</div>
					</div>
					<div class="mt-2 text-2xl font-semibold text-ink-gray-9">{{ kpi(key).total }}</div>
					<div class="mt-1 flex flex-wrap gap-1.5 text-xs">
						<UiStatusBadge v-if="kpi(key).block" theme="red" :label="`${kpi(key).block} blocked`" />
						<UiStatusBadge v-if="kpi(key).advance" theme="orange" :label="`${kpi(key).advance} advance`" />
						<UiStatusBadge v-if="kpi(key).flag" theme="amber" :label="`${kpi(key).flag} flagged`" />
						<UiStatusBadge v-if="kpi(key).pass" theme="green" :label="`${kpi(key).pass} passed`" />
						<span v-if="!kpi(key).total" class="text-ink-gray-4">No orders</span>
					</div>
				</div>
			</div>

			<div class="mt-8 grid gap-6 lg:grid-cols-3">
				<!-- Recent events -->
				<div class="lg:col-span-2">
					<div class="mb-3 flex items-center justify-between">
						<h2 class="text-lg font-medium text-ink-gray-8">Recent orders</h2>
						<router-link to="/orders" class="text-base text-ink-gray-6 hover:text-ink-gray-8">View all</router-link>
					</div>
					<UiDataTable
						:columns="recentColumns"
						:rows="overview.data.recent_events"
						row-key="order_name"
						clickable
						@row-click="(row) => router.push(`/fraud/${row.order_name}`)"
					>
						<template #cell-order_name="{ row }">
							<span class="font-medium text-ink-gray-8">{{ row.order_name }}</span>
						</template>
						<template #cell-fraud="{ row }">
							<div class="flex items-center gap-1.5">
								<UiStatusBadge
									v-if="eventInProcess(row)"
									theme="amber"
									label="Detection in process"
								/>
								<UiStatusBadge
									v-else
									:theme="verdictTheme(row.verdict)"
									:label="`${row.verdict} (${row.score})`"
								/>
								<span v-if="!row.fingerprinted" class="text-xs text-ink-gray-4">no fp</span>
							</div>
						</template>
						<template #cell-when="{ row }">
							{{ formatDateTime(row.creation) }}
						</template>
						<template #empty>
							<UiEmptyState
								:icon="LucideShieldAlert"
								title="No orders yet"
								message="Placed orders will appear here once fraud scoring starts."
							/>
						</template>
					</UiDataTable>
				</div>

				<!-- Right column -->
				<div class="space-y-6">
					<div class="rounded-lg border border-outline-gray-1 p-4">
						<h2 class="text-base font-medium text-ink-gray-8">Risky cities <span class="text-xs font-normal text-ink-gray-4">(30-day RTO)</span></h2>
						<ul v-if="overview.data.cities.length" class="mt-3 space-y-3">
							<li v-for="city in overview.data.cities" :key="city.city">
								<div class="flex justify-between text-sm">
									<span class="text-ink-gray-7">{{ city.city }}</span>
									<span class="text-ink-gray-5">{{ city.failed_30d }}/{{ city.orders_30d }}</span>
								</div>
								<div class="mt-1 h-1.5 w-full overflow-hidden rounded-full bg-surface-gray-3">
									<div
										class="h-full rounded-full"
										:class="city.rto_rate >= 40 ? 'bg-red-500' : city.rto_rate >= 20 ? 'bg-orange-500' : 'bg-green-500'"
										:style="{ width: `${Math.min(100, city.rto_rate)}%` }"
									/>
								</div>
							</li>
						</ul>
						<p v-else class="mt-2 text-sm text-ink-gray-4">No delivery data yet</p>
					</div>

					<div class="rounded-lg border border-outline-gray-1 p-4">
						<h2 class="text-base font-medium text-ink-gray-8">
							Blacklist <UiStatusBadge v-if="overview.data.blacklist.length" theme="red" :label="`${overview.data.blacklist.length} active`" />
						</h2>
						<ul v-if="overview.data.blacklist.length" class="mt-3 space-y-2.5">
							<li v-for="row in overview.data.blacklist" :key="row.name" class="flex items-start justify-between gap-2">
								<div class="min-w-0">
									<div class="truncate font-mono text-sm text-ink-gray-8">{{ row.phone }}</div>
									<div class="truncate text-xs text-ink-gray-5">{{ row.reason || 'No reason recorded' }}</div>
								</div>
								<UiStatusBadge :theme="row.source === 'Auto' ? 'red' : 'gray'" :label="`×${row.hit_count}`" />
							</li>
						</ul>
						<p v-else class="mt-2 text-sm text-ink-gray-4">Nobody blacklisted</p>
					</div>
				</div>
			</div>
		</template>
	</div>
</template>

<script setup lang="ts">
import { Spinner, createResource } from 'frappe-ui'
import { useRouter } from 'vue-router'

import LucideShieldAlert from '~icons/lucide/shield-alert'
import CatalogListState from '@/components/CatalogListState.vue'
import UiDataTable from '@/components/UiDataTable.vue'
import UiEmptyState from '@/components/UiEmptyState.vue'
import UiPageHeader from '@/components/UiPageHeader.vue'
import UiStatusBadge from '@/components/UiStatusBadge.vue'
import { formatDateTime } from '@/utils/format'
import { verdictTheme } from '@/utils/verdict'

const router = useRouter()

const recentColumns = [
	{ key: 'order_name', label: 'Order' },
	{ key: 'customer', label: 'Customer' },
	{ key: 'city', label: 'City' },
	{ key: 'fraud', label: 'Fraud' },
	{ key: 'when', label: 'When', align: 'right' as const },
]

const overview = createResource({
	url: 'shop.api.fraud.get_overview',
	auto: true,
})

function kpi(key: string) {
	return overview.data?.kpis?.[key] ?? { total: 0, pass: 0, flag: 0, advance: 0, block: 0, avg_score: 0, fingerprinted: 0 }
}

function fingerprintedPct(key: string) {
	const b = kpi(key)
	return b.total ? Math.round((b.fingerprinted / b.total) * 100) : 0
}

function eventInProcess(event: any): boolean {
	if (event.fraud_state === 'Processing') return true
	return ['Queued', 'Pending'].includes(event.verification_status)
}

</script>
