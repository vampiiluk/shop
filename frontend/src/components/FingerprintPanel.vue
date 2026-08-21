<template>
	<div class="rounded-lg border border-outline-gray-1 p-4">
		<h2 class="text-base font-medium text-ink-gray-8">Device Fingerprint</h2>
		<div v-if="related.loading" class="mt-2 flex justify-center"><Spinner class="size-4" /></div>
		<div v-else-if="related.data" class="mt-2">
			<div v-if="related.data.fingerprint" class="font-mono text-sm text-ink-gray-8 break-all bg-surface-gray-2 p-2 rounded border border-outline-gray-2">
				{{ related.data.fingerprint }}
			</div>
			<div v-else class="text-sm text-ink-gray-5">
				No fingerprint available (likely blocked by browser).
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { Spinner, createResource } from "frappe-ui"

const props = defineProps<{ order: string }>()

const related = createResource({
	url: "shop.api.fraud.get_related_orders",
	makeParams: () => ({ order: props.order }),
	auto: true,
})
</script>
