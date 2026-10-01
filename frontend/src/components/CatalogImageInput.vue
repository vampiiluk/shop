<template>
	<div>
		<div v-if="label" class="mb-1.5 text-xs text-ink-gray-5">{{ label }}</div>
		<div class="flex items-center gap-3">
			<div
				class="flex size-14 shrink-0 items-center justify-center overflow-hidden rounded border border-outline-gray-1 bg-surface-gray-1"
			>
				<img v-if="model" :src="model" :alt="label || 'Image'" class="size-full object-cover" />
				<LucideImage v-else class="size-5 text-ink-gray-4" />
			</div>
			<!--
				private: false is required, not a preference. frappe-ui's FileUploader
				defaults `private` to true, so without this a product photo is stored
				under /private/files/ and the storefront hands that url to visitors,
				who get a 403. Frappe's own Attach field has the same default, which
				is right there (a desk attachment is often a private document) and
				wrong here: a shop photo is public by nature. The companion flag
				make_attachment_public on the DocType covers Frappe's Attach control
				and does nothing for this component, which posts to upload_file
				directly and never reads that flag.
			-->
			<FileUploader
				:file-types="['image/*']"
				:upload-args="{ private: false }"
				@success="onUpload"
				@failure="onFailure"
			>
				<template #default="{ uploading, progress, openFileSelector }">
					<Button :loading="uploading" @click="openFileSelector">
						{{ uploading ? `Uploading ${progress}%` : model ? 'Replace' : 'Upload' }}
					</Button>
				</template>
			</FileUploader>
			<Button v-if="model" variant="ghost" theme="red" @click="model = ''">Remove</Button>
		</div>
	</div>
</template>

<script setup lang="ts">
import { FileUploader, toast } from 'frappe-ui'

import LucideImage from '~icons/lucide/image'

defineProps<{ label?: string }>()

const model = defineModel<string>({ default: '' })

function onUpload(file: { file_url: string }) {
	model.value = file.file_url
}

function onFailure() {
	toast.error('Could not upload image')
}
</script>
