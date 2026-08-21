<template>
	<Badge :theme="resolved" variant="subtle">{{ label }}</Badge>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { Badge } from 'frappe-ui'

const props = defineProps<{ label: string; theme?: string }>()

// Fallback map for status labels; an explicit `theme` prop always wins.
const themes: Record<string, string> = {
	Paid: 'green',
	Fulfilled: 'green',
	Completed: 'green',
	Converted: 'green',
	Unpaid: 'amber',
	'Partly fulfilled': 'amber',
	Abandoned: 'amber',
	Requested: 'amber',
	Approved: 'blue',
	Cancelled: 'red',
	Rejected: 'red',
	Draft: 'gray',
	Unfulfilled: 'gray',
}

const resolved = computed(() => (props.theme || themes[props.label] || 'blue') as any)
</script>
