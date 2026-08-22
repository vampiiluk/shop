<template>
	<div>
		<div class="mb-3 flex items-center justify-between">
			<div>
				<h3 class="text-sm font-medium text-ink-gray-8">Provinces &amp; Cities</h3>
				<p class="text-p-sm text-ink-gray-5">
					Each row is a province. Click Edit to manage its cities. Used for fraud
					validation and checkout dropdowns.
				</p>
			</div>
			<Button variant="solid" size="sm" @click="addProvince">
				<template #icon><LucidePlus class="size-4" /></template>
				Add Province
			</Button>
		</div>

		<div v-if="!provinces.length" class="rounded-lg border border-dashed border-outline-gray-2 py-8 text-center text-p-sm text-ink-gray-5">
			No provinces added yet. Click "Add Province" to start.
		</div>

		<div v-else class="space-y-2">
			<div
				v-for="(prov, idx) in provinces"
				:key="idx"
				class="flex items-center gap-3 rounded-lg border border-outline-gray-1 bg-surface-white px-4 py-3"
			>
				<div class="min-w-0 flex-1">
					<div class="text-sm font-medium text-ink-gray-8">{{ prov.province_name }}</div>
					<div class="text-p-sm text-ink-gray-5 truncate">
						{{ prov.cities || 'No cities set' }}
					</div>
				</div>
				<div class="flex items-center gap-1">
					<Button variant="subtle" size="sm" @click="editProvince(idx)">
						<template #icon><LucidePencil class="size-3.5" /></template>
						Edit
					</Button>
					<Button variant="subtle" size="sm" theme="red" @click="removeProvince(idx)">
						<template #icon><LucideTrash2 class="size-3.5" /></template>
					</Button>
				</div>
			</div>
		</div>

		<!-- Edit Modal -->
		<Dialog v-model="showDialog">
			<template #body-title>
				<h3>{{ editingIdx === -1 ? 'Add Province' : 'Edit Province' }}</h3>
			</template>
			<template #body>
				<div class="space-y-4">
					<FormControl
						v-model="editForm.province_name"
						label="Province / State name"
						placeholder="e.g. Punjab"
					/>
					<div>
						<label class="mb-1 block text-sm text-ink-gray-6">Cities (comma-separated)</label>
						<textarea
							v-model="editForm.cities"
							rows="6"
							class="w-full rounded-lg border border-outline-gray-1 px-3 py-2 text-sm text-ink-gray-8 focus:outline-none focus:ring-2 focus:ring-ink-gray-4"
							placeholder="Lahore, Faisalabad, Rawalpindi, Multan, ..."
						/>
						<p class="mt-1 text-p-sm text-ink-gray-5">
							Enter one city per line or separated by commas. These cities appear in the checkout
							city dropdown and are used for fraud scoring.
						</p>
					</div>
					<div v-if="editForm.cities" class="flex flex-wrap gap-1.5">
						<span
							v-for="city in parsedCities"
							:key="city"
							class="inline-flex items-center rounded-full bg-surface-gray-2 px-2.5 py-0.5 text-xs text-ink-gray-7"
						>
							{{ city }}
						</span>
					</div>
				</div>
			</template>
			<template #secondary-action>
				<Button variant="subtle" @click="showDialog = false">Cancel</Button>
			</template>
			<template #primary-action>
				<Button
					variant="solid"
					:disabled="!editForm.province_name.trim()"
					@click="saveEdit"
				>
					Save
				</Button>
			</template>
		</Dialog>
	</div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Button, Dialog, FormControl, createResource, toast } from 'frappe-ui'
import LucidePlus from '~icons/lucide/plus'
import LucidePencil from '~icons/lucide/pencil'
import LucideTrash2 from '~icons/lucide/trash-2'

interface Province {
	name?: string
	province_name: string
	cities: string
}

const props = defineProps<{
	modelValue: Province[]
}>()

const emit = defineEmits<{
	'update:modelValue': [value: Province[]]
}>()

const provinces = ref<Province[]>([...props.modelValue])

watch(
	() => props.modelValue,
	(val) => {
		provinces.value = [...val]
	},
)

const showDialog = ref(false)
const editingIdx = ref(-1)
const editForm = ref({ province_name: '', cities: '' })

const parsedCities = computed(() => {
	return editForm.value.cities
		.split(/[,\n]+/)
		.map((c) => c.trim())
		.filter(Boolean)
})

function addProvince() {
	editingIdx.value = -1
	editForm.value = { province_name: '', cities: '' }
	showDialog.value = true
}

function editProvince(idx: number) {
	editingIdx.value = idx
	const prov = provinces.value[idx]
	editForm.value = { province_name: prov.province_name, cities: prov.cities }
	showDialog.value = true
}

function removeProvince(idx: number) {
	provinces.value.splice(idx, 1)
	emit('update:modelValue', [...provinces.value])
	saveProvinces()
}

function saveEdit() {
	const entry = {
		province_name: editForm.value.province_name.trim(),
		cities: editForm.value.cities.trim(),
	}
	if (editingIdx.value >= 0) {
		provinces.value[editingIdx.value] = entry
	} else {
		provinces.value.push(entry)
	}
	showDialog.value = false
	emit('update:modelValue', [...provinces.value])
	saveProvinces()
}

const saveMutation = createResource({
	url: 'shop.api.settings.save_provinces',
	onSuccess: () => toast.success('Provinces saved'),
	onError: () => toast.error('Failed to save provinces'),
})

function saveProvinces() {
	saveMutation.submit({ provinces: provinces.value })
}
</script>
