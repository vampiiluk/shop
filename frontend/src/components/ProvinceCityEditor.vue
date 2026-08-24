<template>
	<div>
		<div class="mb-4 flex items-center justify-between">
			<div>
				<h3 class="text-base font-semibold text-ink-gray-9">Provinces &amp; Cities</h3>
				<p class="mt-0.5 text-p-sm text-ink-gray-5">
					Define which cities belong to each province. Customers select from these at checkout.
				</p>
			</div>
			<Button variant="solid" size="sm" @click="addProvince">
				<template #icon><LucidePlus class="size-4" /></template>
				Add Province
			</Button>
		</div>

		<div v-if="!provinces.length" class="rounded-xl border border-dashed border-outline-gray-2 py-12 text-center">
			<div class="mx-auto mb-2 flex size-10 items-center justify-center rounded-full bg-surface-gray-2">
				<LucideMapPin class="size-5 text-ink-gray-5" />
			</div>
			<p class="text-sm font-medium text-ink-gray-7">No provinces yet</p>
			<p class="mt-1 text-p-sm text-ink-gray-5">Add your first province to define checkout regions.</p>
		</div>

		<div v-else class="rounded-xl border border-outline-gray-1">
			<table class="w-full text-left text-sm">
				<thead class="border-b border-outline-gray-1 bg-surface-gray-2 text-p-sm text-ink-gray-6">
					<tr>
						<th class="px-4 py-2.5 font-medium">Province / State</th>
						<th class="px-4 py-2.5 font-medium">Cities</th>
						<th class="w-20 px-4 py-2.5 text-right font-medium">Count</th>
						<th class="w-24 px-4 py-2.5 text-right font-medium">Actions</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-outline-gray-1">
					<tr
						v-for="(prov, idx) in provinces"
						:key="idx"
						class="group cursor-pointer transition-colors hover:bg-surface-gray-2"
						@click="editProvince(idx)"
					>
						<td class="px-4 py-3 font-medium text-ink-gray-8">{{ prov.province_name }}</td>
						<td class="max-w-xs truncate px-4 py-3 text-ink-gray-5">
							{{ prov.cities || 'No cities' }}
						</td>
						<td class="px-4 py-3 text-right">
							<span class="inline-flex items-center justify-center rounded-full bg-surface-gray-3 px-2 py-0.5 text-xs font-medium text-ink-gray-7">
								{{ cityCount(prov.cities) }}
							</span>
						</td>
						<td class="px-4 py-3 text-right">
							<div class="flex items-center justify-end gap-1">
								<Button variant="subtle" size="xs" @click.stop="editProvince(idx)" title="Edit province">
									<template #icon><LucidePencil class="size-3.5" /></template>
								</Button>
								<Button variant="subtle" size="xs" theme="red" @click.stop="removeProvince(idx)" title="Delete province">
									<template #icon><LucideTrash2 class="size-3.5" /></template>
								</Button>
							</div>
						</td>
					</tr>
				</tbody>
			</table>
		</div>

		<!-- Edit Modal -->
		<div v-if="showDialog" class="fixed inset-0 z-50 flex items-center justify-center p-4" @click.self="showDialog = false">
			<div class="fixed inset-0 bg-black/50 backdrop-blur-sm" @click="showDialog = false"></div>
			<div class="relative z-10 w-full max-w-lg rounded-2xl bg-white shadow-2xl">
				<div class="flex items-center justify-between border-b border-outline-gray-1 px-6 py-4">
					<div>
						<h3 class="text-base font-semibold text-ink-gray-9">
							{{ editingIdx === -1 ? 'Add Province' : editForm.province_name }}
						</h3>
						<p v-if="editingIdx >= 0" class="mt-0.5 text-p-sm text-ink-gray-5">
							Edit cities for this province
						</p>
					</div>
					<button
						class="flex size-8 items-center justify-center rounded-lg text-ink-gray-5 transition-colors hover:bg-surface-gray-2 hover:text-ink-gray-8"
						@click="showDialog = false"
					>
						<LucideX class="size-4" />
					</button>
				</div>
				<div class="space-y-5 px-6 py-5">
					<div>
						<label class="mb-1.5 block text-sm font-medium text-ink-gray-7">Province / State name</label>
						<input
							v-model="editForm.province_name"
							type="text"
							class="w-full rounded-lg border border-outline-gray-1 bg-surface-white px-3 py-2.5 text-sm text-ink-gray-8 placeholder:text-ink-gray-4 focus:border-outline-gray-2 focus:outline-none focus:ring-2 focus:ring-ink-gray-3"
							placeholder="e.g. Punjab"
						/>
					</div>
					<div>
						<label class="mb-1.5 block text-sm font-medium text-ink-gray-7">Cities</label>
						<textarea
							v-model="editForm.cities"
							rows="4"
							class="w-full rounded-lg border border-outline-gray-1 bg-surface-white px-3 py-2.5 text-sm text-ink-gray-8 placeholder:text-ink-gray-4 focus:border-outline-gray-2 focus:outline-none focus:ring-2 focus:ring-ink-gray-3"
							placeholder="Lahore, Faisalabad, Rawalpindi, ..."
							@keydown.enter.ctrl="saveEdit"
						/>
						<p class="mt-1 text-p-sm text-ink-gray-5">
							Comma or newline separated. Ctrl+Enter to save.
						</p>
					</div>
					<div v-if="parsedCities.length" class="space-y-2">
						<div class="flex items-center justify-between">
							<span class="text-xs font-medium text-ink-gray-6">{{ parsedCities.length }} {{ parsedCities.length === 1 ? 'city' : 'cities' }}</span>
							<button v-if="parsedCities.length > 1" class="text-xs text-ink-gray-5 hover:text-ink-gray-8" @click="sortCities">Sort A-Z</button>
						</div>
						<div class="flex flex-wrap gap-1.5">
							<span
								v-for="city in parsedCities"
								:key="city"
								class="group/chip inline-flex items-center gap-1 rounded-full border border-outline-gray-1 bg-surface-gray-2 px-2.5 py-1 text-xs text-ink-gray-7 transition-colors hover:border-red-300 hover:bg-red-50"
							>
								{{ city }}
								<button
									class="text-ink-gray-4 transition-opacity hover:text-red-500"
									@click="removeCity(city)"
								>
									<LucideX class="size-3" />
								</button>
							</span>
						</div>
					</div>
				</div>
				<div class="flex items-center justify-end gap-2 border-t border-outline-gray-1 px-6 py-4">
					<Button variant="subtle" @click="showDialog = false">Cancel</Button>
					<Button
						variant="solid"
						:disabled="!editForm.province_name.trim()"
						@click="saveEdit"
					>
						{{ editingIdx >= 0 ? 'Save Changes' : 'Add Province' }}
					</Button>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { Button, createResource, toast } from 'frappe-ui'
import LucidePlus from '~icons/lucide/plus'
import LucidePencil from '~icons/lucide/pencil'
import LucideTrash2 from '~icons/lucide/trash-2'
import LucideX from '~icons/lucide/x'
import LucideMapPin from '~icons/lucide/map-pin'

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

function cityCount(cities: string) {
	return cities
		.split(/[,\n]+/)
		.map((c) => c.trim())
		.filter(Boolean).length
}

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

function removeCity(city: string) {
	const parts = editForm.value.cities
		.split(/[,\n]+/)
		.map((c) => c.trim())
		.filter(Boolean)
	editForm.value.cities = parts.filter((c) => c !== city).join(', ')
}

function sortCities() {
	const parts = editForm.value.cities
		.split(/[,\n]+/)
		.map((c) => c.trim())
		.filter(Boolean)
	editForm.value.cities = parts.sort((a, b) => a.localeCompare(b)).join(', ')
}

function saveEdit() {
	const entry = {
		province_name: editForm.value.province_name.trim(),
		cities: parsedCities.value.join(', '),
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
