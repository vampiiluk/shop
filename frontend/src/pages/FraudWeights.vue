<template>
	<div class="mx-auto max-w-5xl px-6 py-8">
		<UiPageHeader title="Fraud Weights">
			<template #actions>
				<UiStatusBadge v-if="schema.data?.customized" theme="amber" label="Customized" />
			</template>
		</UiPageHeader>
		<p class="mt-1 max-w-2xl text-p-sm text-ink-gray-6">
			Points each signal adds to the fraud score. Changes apply to every new checkout
			immediately.
		</p>

		<CatalogListState
			:loading="schema.loading && !schema.data"
			:error="schema.error"
			empty-title=""
			@retry="schema.reload()"
		/>

		<div v-if="schema.data" class="mt-6 space-y-5">
			<CatalogListState v-if="saveError" :error="{ messages: [saveError] }" />

			<div
				v-for="group in schema.data.groups"
				:key="group.group"
				class="rounded-lg border border-outline-gray-1 p-4"
			>
				<h2 class="text-base font-medium text-ink-gray-8">{{ group.group }}</h2>
				<div class="mt-3 grid gap-2 sm:grid-cols-2">
					<label
						v-for="field in group.fields"
						:key="field.key"
						class="flex items-center justify-between gap-3 rounded bg-surface-gray-2 px-3 py-2 text-sm border border-outline-gray-2"
						:title="`Key: ${field.key}`"
					>
						<span class="text-ink-gray-6">{{ field.label }}</span>
						<input
							v-model.number="values[field.key]"
							type="number"
							class="w-20 rounded border border-outline-gray-2 bg-surface-white px-2 py-1 text-right font-semibold text-ink-gray-8 focus:outline-none focus:ring-1 focus:ring-ink-gray-4"
						/>
					</label>
				</div>
				<p class="mt-2 text-xs text-ink-gray-4">
					Default: {{ group.fields.map((f) => `${f.label.split(' ')[0].toLowerCase()} ${f.default}`).join(', ') }}
				</p>
			</div>

			<div class="flex gap-2">
				<Button variant="solid" :loading="saving" @click="save">Save</Button>
				<Button :disabled="saving" @click="resetDefaults">Restore defaults</Button>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue'

import { Button, call, createResource, toast } from 'frappe-ui'

import CatalogListState from '@/components/CatalogListState.vue'
import UiPageHeader from '@/components/UiPageHeader.vue'
import UiStatusBadge from '@/components/UiStatusBadge.vue'

const values = reactive<Record<string, number>>({})
const saving = ref(false)
const saveError = ref('')

const schema = createResource({
	url: 'shop.api.settings.get_weight_schema',
	auto: true,
	onSuccess(data) {
		for (const group of data.groups || []) {
			for (const field of group.fields) {
				values[field.key] = Number(field.value ?? field.default ?? 0)
			}
		}
	},
})

async function save() {
	saving.value = true
	saveError.value = ''
	try {
		await call('shop.api.settings.save_settings', {
			payload: { fraud_signal_weights: JSON.stringify(values) },
		})
		toast.success('Weights saved — applied to all new checkouts')
		schema.reload()
	} catch (e: any) {
		const messages = e?.messages
		saveError.value = messages?.[0] || 'Could not save weights'
		toast.error(saveError.value)
	} finally {
		saving.value = false
	}
}

async function resetDefaults() {
	if (!schema.data) return
	for (const group of schema.data.groups) {
		for (const field of group.fields) {
			values[field.key] = Number(field.default)
		}
	}
	await save()
}

</script>
