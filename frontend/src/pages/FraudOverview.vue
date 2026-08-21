<template>
	<div class="mx-auto max-w-6xl px-6 py-8">
		<h1 class="text-xl font-semibold text-ink-gray-9">Fraud Overview</h1>

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
						<UiStatusBadge v-if="kpi(key).flag" :label="`${kpi(key).flag} flagged`" />
						<UiStatusBadge v-if="kpi(key).pass" theme="green" :label="`${kpi(key).pass} passed`" />
						<span v-if="!kpi(key).total" class="text-ink-gray-4">No orders</span>
					</div>
				</div>
			</div>

			<div class="mt-6 grid gap-6 lg:grid-cols-3">
				<!-- Recent events -->
				<div class="lg:col-span-2">
					<div class="overflow-hidden rounded-lg border border-outline-gray-1">
						<div class="border-b border-outline-gray-1 px-4 py-3 text-sm font-medium text-ink-gray-7">
							Recent orders
						</div>
						<table v-if="overview.data.recent_events.length" class="w-full text-base">
							<thead>
								<tr class="border-b border-outline-gray-1 text-left text-sm text-ink-gray-5">
									<th class="px-3 py-2 font-normal">Order</th>
									<th class="px-3 py-2 font-normal">Phone</th>
									<th class="px-3 py-2 font-normal">City</th>
									<th class="px-3 py-2 font-normal">Fraud</th>
									<th class="px-3 py-2 text-right font-normal">When</th>
								</tr>
							</thead>
							<tbody>
								<tr
									v-for="event in overview.data.recent_events"
									:key="event.order_name"
									class="border-b border-outline-gray-1 last:border-b-0"
								>
									<td class="px-3 py-2">
										<div class="flex items-center gap-2">
											<router-link
												:to="`/orders/${event.order_name}`"
												class="font-medium text-ink-gray-8 hover:underline"
											>
												{{ event.order_name }}
											</router-link>
											<router-link
												:to="`/fraud/${event.order_name}`"
												class="text-xs text-ink-gray-4 underline hover:text-ink-gray-6"
												title="Fraud detail"
											>
												detail
											</router-link>
										</div>
									</td>
									<td class="px-3 py-2 text-ink-gray-7">{{ event.phone || '—' }}</td>
									<td class="px-3 py-2 text-ink-gray-7">{{ event.city || '—' }}</td>
									<td class="px-3 py-2">
										<div class="flex items-center gap-1.5">
											<UiStatusBadge :theme="verdictTheme(event.verdict)" :label="`${event.verdict} (${event.score})`" />
											<span v-if="!event.fingerprinted" class="text-xs text-ink-gray-4">no fp</span>
										</div>
									</td>
									<td class="px-3 py-2 text-right text-sm text-ink-gray-5">
										{{ formatDateTime(event.creation) }}
									</td>
								</tr>
							</tbody>
						</table>
						<div v-else class="px-4 py-6 text-center text-sm text-ink-gray-4">Nothing flagged yet</div>
					</div>
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

import CatalogListState from '@/components/CatalogListState.vue'
import UiStatusBadge from '@/components/UiStatusBadge.vue'
import { formatDateTime } from '@/utils/format'

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

function verdictTheme(verdict: string) {
	if (verdict === 'Block') return 'red'
	if (verdict === 'Advance Required') return 'orange'
	if (verdict === 'Flag') return 'gray'
	return 'green'
}
</script>
