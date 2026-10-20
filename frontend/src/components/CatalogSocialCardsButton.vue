<template>
	<Button
		:variant="compact ? 'ghost' : 'outline'"
		:loading="busy"
		:title="title"
		data-social-cards
		@click="run"
	>
		<template #prefix><LucideDownload class="size-4" /></template>
		<template v-if="!compact">{{ busy ? 'Building cards…' : 'Social cards' }}</template>
	</Button>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { Button, toast } from 'frappe-ui'

import LucideDownload from '~icons/lucide/download'

import { downloadSocialCards } from '@/utils/socialCards'

const props = defineProps<{ name: string; compact?: boolean }>()

const busy = ref(false)

const title = 'Social cards: download Instagram and TikTok cards for this product as a zip'

async function run() {
	if (busy.value) return
	busy.value = true
	try {
		await downloadSocialCards(props.name)
		toast.success('Social cards downloaded')
	} catch (error) {
		toast.error((error as Error).message || 'Could not build the social cards')
	} finally {
		busy.value = false
	}
}
</script>
