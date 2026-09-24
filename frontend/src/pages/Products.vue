<template>
	<div class="mx-auto max-w-5xl px-6 py-8">
		<div class="flex items-center justify-between">
			<h1 class="text-xl font-semibold text-ink-gray-9">Products</h1>
			<div class="flex gap-2">
				<Button :loading="syncing" @click="syncMeta">
					<template #prefix><LucideRefreshCw class="size-4" /></template>
					Sync to Meta
				</Button>
				<Button :route="{ path: '/products/new', query: { mode: 'link' } }">
					Link existing item
				</Button>
				<Button variant="solid" route="/products/new">
					<template #prefix><LucidePlus class="size-4" /></template>
					Add product
				</Button>
			</div>
		</div>

		<div class="mt-6 flex items-center justify-between gap-4">
			<FormControl
				v-model="search"
				type="text"
				placeholder="Search products"
				class="w-64"
				:debounce="300"
			>
				<template #prefix><LucideSearch class="size-4 text-ink-gray-5" /></template>
			</FormControl>
			<TabButtons v-model="status" :options="statusTabs" />
		</div>

		<CatalogListState
			:loading="products.loading && !products.data"
			:error="products.error"
			:empty="!rows.length"
			empty-title="No products found"
			empty-subtitle="Add a product or adjust your filters."
			@retry="products.reload()"
		>
			<template #action>
				<Button variant="solid" route="/products/new">Add product</Button>
			</template>
		</CatalogListState>

		<template v-if="rows.length && !products.error">
			<div class="mt-4 overflow-hidden rounded-lg border border-outline-gray-1">
				<table class="w-full text-base">
					<thead>
						<tr class="border-b border-outline-gray-1 text-left text-sm text-ink-gray-5">
							<th class="w-14 px-3 py-2 font-normal"></th>
							<th class="px-3 py-2 font-normal">Product</th>
							<th class="px-3 py-2 text-right font-normal">Price</th>
							<th class="px-3 py-2 text-right font-normal">Stock</th>
							<th class="px-3 py-2 text-right font-normal">Published</th>
							<th class="w-10 px-1 py-2"></th>
						</tr>
					</thead>
					<tbody>
						<tr
							v-for="row in rows"
							:key="row.name"
							class="cursor-pointer border-b border-outline-gray-1 last:border-b-0 hover:bg-surface-gray-1"
							@click="openProduct(row.name)"
						>
							<td class="px-3 py-2">
								<div
									class="flex size-9 items-center justify-center overflow-hidden rounded border border-outline-gray-1 bg-surface-gray-1"
								>
									<img
										v-if="row.image"
										:src="row.image"
										:alt="row.product_name"
										class="size-full object-cover"
									/>
									<LucideImage v-else class="size-4 text-ink-gray-4" />
								</div>
							</td>
							<td class="px-3 py-2">
								<div class="font-medium text-ink-gray-8">{{ row.product_name }}</div>
								<div class="text-sm text-ink-gray-5">/{{ row.slug }}</div>
								<div v-if="row.has_variants" class="flex items-center gap-1 text-sm text-ink-gray-5">
									<LucideLayers class="size-3" />
									Variants
								</div>
							</td>
							<td class="px-3 py-2 text-right text-ink-gray-7">{{ row.formatted_price }}</td>
							<td
								class="px-3 py-2 text-right"
								:class="row.stock ? 'text-ink-gray-7' : 'font-medium text-ink-red-8'"
							>
								{{ row.stock }}
							</td>
							<td class="px-3 py-2 text-right" @click.stop>
								<Switch
									:model-value="!!row.published"
									@update:model-value="(value: boolean) => togglePublished(row, value)"
								/>
							</td>
							<td class="px-1 py-2" @click.stop>
								<Dropdown :options="rowActions(row)">
									<Button variant="ghost">
										<template #icon><LucideEllipsisVertical class="size-4" /></template>
									</Button>
								</Dropdown>
							</td>
						</tr>
					</tbody>
				</table>
			</div>
			<CatalogPagination
				:start="start"
				:limit="PAGE_SIZE"
				:total="products.data?.total || 0"
				@update:start="start = $event"
			/>
		</template>

		<Dialog v-model="showSync" :title="syncTitle" size="lg" :actions="syncActions">
			<template #default>
				<div
					v-if="syncError"
					class="rounded-lg border border-outline-red-1 bg-surface-red-1 p-3 text-p-sm text-ink-red-8"
				>
					{{ syncError }}
				</div>
				<div v-else-if="syncResult">
					<p
						class="flex items-start gap-2 text-p-base"
						:class="syncResult.success ? 'text-ink-green-8' : 'text-ink-red-8'"
					>
						<LucideCheck v-if="syncResult.success" class="mt-0.5 size-4 shrink-0" />
						<LucideX v-else class="mt-0.5 size-4 shrink-0" />
						<span>{{ syncResult.status || 'Catalogue synced' }}</span>
					</p>
					<p v-if="syncResult.products" class="mt-2 text-p-sm text-ink-gray-5">
						{{ syncResult.products }} products · {{ syncResult.pushed }} items pushed<template
							v-if="syncResult.deleted"
						>
							· {{ syncResult.deleted }} removed</template
						><template v-if="syncResult.linked"> · {{ syncResult.linked }} ids linked</template>
					</p>
					<ul v-if="syncIssues.length" class="mt-3 space-y-1 border-t border-outline-gray-1 pt-3">
						<li v-for="issue in syncIssues" :key="issue" class="text-p-sm text-ink-gray-6">
							{{ issue }}
						</li>
					</ul>
				</div>
				<template v-else>
					<p class="text-p-base text-ink-gray-6">
						Publishing the catalogue to Meta. Every step shows up here as it happens.
					</p>
					<p v-if="!syncSteps.length" class="mt-3 text-p-sm text-ink-gray-5">
						Waiting for the sync to start…
					</p>
					<ul v-else class="mt-3 space-y-2.5">
						<li v-for="step in syncSteps" :key="step.key" class="flex items-start gap-2.5">
							<Spinner v-if="step.state === 'active'" class="mt-0.5 size-4 shrink-0" />
							<LucideCheck
								v-else-if="step.state === 'done'"
								class="mt-0.5 size-4 shrink-0 text-ink-green-7"
							/>
							<LucideX
								v-else-if="step.state === 'error'"
								class="mt-0.5 size-4 shrink-0 text-ink-red-8"
							/>
							<span
								v-else
								class="mt-1 size-2.5 shrink-0 rounded-full border border-outline-gray-2"
							/>
							<span class="min-w-0">
								<span
									class="block text-sm"
									:class="
										step.state === 'pending'
											? 'text-ink-gray-4'
											: 'font-medium text-ink-gray-8'
									"
								>
									{{ step.label }}
								</span>
								<span v-if="step.detail" class="block text-p-sm text-ink-gray-5">
									{{ step.detail }}
								</span>
							</span>
						</li>
					</ul>
				</template>
			</template>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Dialog, Dropdown, FormControl, Spinner, Switch, TabButtons, call, createResource, dialog, toast } from 'frappe-ui'

import LucideCheck from '~icons/lucide/check'
import LucideEllipsisVertical from '~icons/lucide/ellipsis-vertical'
import LucideExternalLink from '~icons/lucide/external-link'
import LucideImage from '~icons/lucide/image'
import LucideLayers from '~icons/lucide/layers'
import LucidePencil from '~icons/lucide/pencil'
import LucidePlus from '~icons/lucide/plus'
import LucideRefreshCw from '~icons/lucide/refresh-cw'
import LucideSearch from '~icons/lucide/search'
import LucideTrash2 from '~icons/lucide/trash-2'
import LucideX from '~icons/lucide/x'

import CatalogListState from '@/components/CatalogListState.vue'
import CatalogPagination from '@/components/CatalogPagination.vue'

interface ProductRow {
	name: string
	product_name: string
	slug: string
	published: number
	image: string | null
	formatted_price: string
	stock: number
	has_variants: number
}

const PAGE_SIZE = 20

const route = useRoute()
const router = useRouter()
const search = ref((route.query.search as string) || '')
const status = ref('')
const start = ref(0)
const syncing = ref(false)

interface SyncStep {
	key: string
	label: string
	state: 'pending' | 'active' | 'done' | 'error'
	detail: string
}

interface SyncResult {
	success?: boolean
	status?: string
	pushed?: number
	products?: number
	deleted?: number
	linked?: number
	errors?: string[]
	warnings?: string[]
}

const showSync = ref(false)
const syncSteps = ref<SyncStep[]>([])
const syncResult = ref<SyncResult | null>(null)
const syncError = ref<string | null>(null)
let syncRunId = ''
let syncPoll: ReturnType<typeof setInterval> | null = null

const syncTitle = computed(() =>
	syncResult.value || syncError.value ? 'Meta catalogue sync' : 'Syncing to Meta catalogue',
)
const syncIssues = computed(() =>
	[...(syncResult.value?.errors || []), ...(syncResult.value?.warnings || [])].slice(0, 6),
)
const syncActions = computed(() =>
	syncResult.value || syncError.value
		? [
				{
					label: 'Close',
					variant: 'solid' as const,
					onClick: () => {
						showSync.value = false
					},
				},
			]
		: [],
)

const statusTabs = [
	{ label: 'All', value: '' },
	{ label: 'Published', value: 'published' },
	{ label: 'Draft', value: 'draft' },
]

const products = createResource({
	url: 'shop.api.products.get_products',
	makeParams: () => ({
		search: search.value || undefined,
		status: status.value || undefined,
		start: start.value,
		limit: PAGE_SIZE,
	}),
	auto: true,
})

const rows = computed<ProductRow[]>(() => products.data?.products || [])

watch([search, status], () => {
	start.value = 0
	products.reload()
})
watch(start, () => products.reload())

function openProduct(name: string) {
	router.push(`/products/${encodeURIComponent(name)}`)
}

function rowActions(row: ProductRow) {
	return [
		{ label: 'Edit', icon: LucidePencil, onClick: () => openProduct(row.name) },
		{
			label: 'View on storefront',
			icon: LucideExternalLink,
			onClick: () => window.open(`/product/${row.slug}`, '_blank'),
		},
		{ label: 'Delete', icon: LucideTrash2, theme: 'red', onClick: () => confirmDelete(row) },
	]
}

function confirmDelete(row: ProductRow) {
	dialog.confirm({
		title: 'Delete product',
		message: `Remove <b>${row.product_name}</b> from the storefront? The underlying item is kept.`,
		theme: 'red',
		confirmLabel: 'Delete',
		onConfirm: async () => {
			await call('shop.api.products.delete_product', { name: row.name })
			toast.success('Product deleted')
			products.reload()
		},
	})
}

async function togglePublished(row: ProductRow, value: boolean) {
	row.published = value ? 1 : 0
	try {
		await call('shop.api.products.set_published', { name: row.name, published: value })
	} catch (error) {
		row.published = value ? 0 : 1
		toast.error('Could not update product')
	}
}

async function pollSyncProgress() {
	try {
		const snapshot = (await call('shop.api.settings.get_meta_sync_progress', {
			run_id: syncRunId,
		})) as { run_id?: string; steps?: SyncStep[] }
		// ignore anything from an earlier run — the server says which run it is
		if (snapshot?.run_id === syncRunId && snapshot.steps?.length) {
			syncSteps.value = snapshot.steps
		}
	} catch (error) {
		// polling is decoration: never let it interrupt the sync itself
	}
}

async function syncMeta() {
	if (syncing.value) return
	syncing.value = true
	syncRunId = `${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
	syncSteps.value = []
	syncResult.value = null
	syncError.value = null
	showSync.value = true
	await pollSyncProgress()
	syncPoll = setInterval(pollSyncProgress, 700)
	try {
		const result = (await call('shop.api.settings.sync_meta_catalog', {
			run_id: syncRunId,
		})) as SyncResult
		syncResult.value = result
		await pollSyncProgress()
		// the dialog shows the outcome when it is still open; if the user
		// closed it mid-run, fall back to the old toast
		if (!showSync.value) {
			if (result.success) toast.success(result.status || 'Catalogue synced')
			else toast.error(result.status || 'Sync failed')
		}
	} catch (error) {
		const messages = (error as { messages?: string[] }).messages
		syncError.value = messages?.[0] || 'Could not sync the Meta catalogue'
		if (!showSync.value) toast.error(syncError.value)
	} finally {
		if (syncPoll) {
			clearInterval(syncPoll)
			syncPoll = null
		}
		syncing.value = false
	}
}
</script>
