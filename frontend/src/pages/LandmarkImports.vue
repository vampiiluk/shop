<template>
	<div class="mx-auto max-w-4xl px-6 py-8">
		<h1 class="text-xl font-semibold text-ink-gray-9">Landmarks Import</h1>

		<p class="mt-2 max-w-2xl text-p-sm text-ink-gray-6">
			Upload landmark CSVs produced by google-maps-scraper (slim format) to power
			address corroboration in the fraud engine. Rows are deduplicated by place_id
			or name + coordinates — re-uploading the same file is always safe.
		</p>

		<!-- Upload -->
		<div class="mt-6 rounded-lg border border-outline-gray-1 p-5">
			<h2 class="text-base font-medium text-ink-gray-8">Import CSV</h2>
			<p class="mt-1 text-xs text-ink-gray-5">
				Expected columns:
				<code class="rounded bg-surface-gray-3 px-1">input_id</code>,
				<code class="rounded bg-surface-gray-3 px-1">title</code>,
				<code class="rounded bg-surface-gray-3 px-1">category</code>,
				<code class="rounded bg-surface-gray-3 px-1">address</code>,
				<code class="rounded bg-surface-gray-3 px-1">latitude</code>,
				<code class="rounded bg-surface-gray-3 px-1">longitude</code>
				(optional: <code class="rounded bg-surface-gray-3 px-1">phone</code>, <code class="rounded bg-surface-gray-3 px-1">place_id</code>)
				— <code class="rounded bg-surface-gray-3 px-1">input_id</code> format:
				<code class="rounded bg-surface-gray-3 px-1">city|category</code>
			</p>

			<div class="mt-4 flex flex-wrap items-center gap-3">
				<label
					class="inline-flex cursor-pointer items-center gap-2 rounded border border-outline-gray-2 px-3 py-2 text-sm text-ink-gray-7 hover:bg-surface-gray-2"
				>
					<LucideFileUp class="size-4" />
					{{ file ? file.name : 'Choose CSV file' }}
					<input type="file" accept=".csv,text/csv" class="hidden" @change="onFile" />
				</label>
				<Button variant="solid" :loading="importing" :disabled="!file || importing" @click="run">
					Import {{ file ? `(${(file.size / 1024).toFixed(0)} KB)` : '' }}
				</Button>
			</div>

			<div v-if="result" class="mt-4 rounded-lg border border-outline-green-2 bg-surface-green-2 p-3 text-sm text-ink-green-8">
				<span class="font-medium">Done.</span>
				{{ result.inserted }} inserted · {{ result.updated }} updated · {{ result.skipped }} skipped.
				Landmarks in table: <strong>{{ result.total_landmarks }}</strong>
			</div>
			<div v-if="errorText" class="mt-4 rounded-lg border border-outline-red-2 bg-surface-red-2 p-3 text-sm text-ink-red-6">
				{{ errorText }}
			</div>
		</div>

		<!-- Stats -->
		<div class="mt-6 grid gap-6 lg:grid-cols-3">
			<div class="rounded-lg border border-outline-gray-1 p-5">
				<div class="text-xs uppercase tracking-wide text-ink-gray-5">Total landmarks</div>
				<div class="mt-1 text-2xl font-semibold text-ink-gray-9">{{ stats.data?.total ?? 0 }}</div>
			</div>

			<div class="rounded-lg border border-outline-gray-1 p-5 lg:col-span-2">
				<h2 class="text-base font-medium text-ink-gray-8">By city</h2>
				<table v-if="stats.data?.cities?.length" class="mt-3 w-full text-sm">
					<tbody>
						<tr
							v-for="c in stats.data.cities"
							:key="c.city"
							class="border-b border-outline-gray-2 last:border-b-0"
						>
							<td class="py-1.5 text-ink-gray-7">{{ c.city }}</td>
							<td class="py-1.5 text-right font-semibold text-ink-gray-8">{{ c.total }}</td>
						</tr>
					</tbody>
				</table>
				<p v-else class="mt-2 text-sm text-ink-gray-4">Nothing imported yet — upload a CSV above.</p>
			</div>
		</div>

		<div v-if="stats.data?.by_category?.length" class="mt-6 rounded-lg border border-outline-gray-1 p-5">
			<h2 class="text-base font-medium text-ink-gray-8">By category</h2>
			<div class="mt-3 flex flex-wrap gap-2">
				<UiStatusBadge
					v-for="cat in stats.data.by_category"
					:key="cat.category"
					:label="`${cat.category} (${cat.total})`"
				/>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import LucideFileUp from '~icons/lucide/file-up'

import { Button, call, createResource } from 'frappe-ui'

import UiStatusBadge from '@/components/UiStatusBadge.vue'

const file = ref<File | null>(null)
const importing = ref(false)
const result = ref<any>(null)
const errorText = ref('')

const stats = createResource({
	url: 'shop.api.landmarks.landmark_stats',
	auto: true,
})

function onFile(event: Event) {
	const input = event.target as HTMLInputElement
	file.value = input.files?.[0] || null
	result.value = null
	errorText.value = ''
}

async function run() {
	if (!file.value) return
	importing.value = true
	result.value = null
	errorText.value = ''
	try {
		const text = await file.value.text()
		result.value = await call('shop.api.landmarks.import_landmarks', {
			csv_content: text,
			source: 'google',
		})
		file.value = null
		stats.reload()
	} catch (e: any) {
		const messages = e?.messages
		errorText.value = messages?.[0] || e?.message || 'Import failed'
	} finally {
		importing.value = false
	}
}
</script>
