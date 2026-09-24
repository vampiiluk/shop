<template>
	<div>
		<div class="mb-4 flex items-center justify-between">
			<div>
				<h3 class="text-base font-semibold text-ink-gray-9">Pickup Locations</h3>
				<p class="mt-0.5 text-p-sm text-ink-gray-5">
					Where customers collect their orders. Each location is shown with a map on checkout and the
					confirmation page. Payment is taken when they pick the order up, like cash on delivery.
				</p>
			</div>
			<Button variant="solid" size="sm" @click="addLocation">
				<template #icon><LucidePlus class="size-4" /></template>
				Add Location
			</Button>
		</div>

		<div
			v-if="!locations.length"
			class="rounded-xl border border-dashed border-outline-gray-2 py-12 text-center"
		>
			<div class="mx-auto mb-2 flex size-10 items-center justify-center rounded-full bg-surface-gray-2">
				<LucideMapPin class="size-5 text-ink-gray-5" />
			</div>
			<p class="text-sm font-medium text-ink-gray-7">No pickup locations yet</p>
			<p class="mt-1 text-p-sm text-ink-gray-5">
				Add your first store location so customers can collect orders from it.
			</p>
		</div>

		<div v-else class="overflow-x-auto rounded-xl border border-outline-gray-1">
			<table class="w-full text-left text-sm">
				<thead class="border-b border-outline-gray-1 bg-surface-gray-2 text-p-sm text-ink-gray-6">
					<tr>
						<th class="px-4 py-2.5 font-medium">Location</th>
						<th class="px-4 py-2.5 font-medium">Address</th>
						<th class="px-4 py-2.5 font-medium">Map link</th>
						<th class="px-4 py-2.5 font-medium">Phone</th>
						<th class="w-24 px-4 py-2.5 text-right font-medium">Actions</th>
					</tr>
				</thead>
				<tbody class="divide-y divide-outline-gray-1">
					<tr
						v-for="(loc, idx) in locations"
						:key="idx"
						class="group cursor-pointer transition-colors hover:bg-surface-gray-2"
						@click="editLocation(idx)"
					>
						<td class="px-4 py-3 font-medium text-ink-gray-8">{{ loc.location_name }}</td>
						<td class="max-w-xs truncate px-4 py-3 text-ink-gray-5">
							{{ loc.address || 'No address' }}
						</td>
						<td class="max-w-[16rem] truncate px-4 py-3 text-ink-gray-5">
							<span v-if="loc.google_maps_link" class="font-mono text-xs" :title="loc.google_maps_link">
								{{ loc.google_maps_link }}
							</span>
							<span
								v-else-if="loc.latitude && loc.longitude"
								class="font-mono text-xs"
								:title="`${loc.latitude}, ${loc.longitude}`"
							>
								{{ loc.latitude }}, {{ loc.longitude }}
							</span>
							<span v-else class="text-ink-gray-4">—</span>
						</td>
						<td class="px-4 py-3 text-ink-gray-5">{{ loc.phone || '—' }}</td>
						<td class="px-4 py-3 text-right">
							<div class="flex items-center justify-end gap-1">
								<Button
									variant="subtle"
									size="xs"
									@click.stop="editLocation(idx)"
									title="Edit location"
								>
									<template #icon><LucidePencil class="size-3.5" /></template>
								</Button>
								<Button
									variant="subtle"
									size="xs"
									theme="red"
									@click.stop="removeLocation(idx)"
									title="Delete location"
								>
									<template #icon><LucideTrash2 class="size-3.5" /></template>
								</Button>
							</div>
						</td>
					</tr>
				</tbody>
			</table>
		</div>

		<!-- Edit Modal -->
		<div
			v-if="showDialog"
			class="fixed inset-0 z-50 flex items-center justify-center p-4"
			@click.self="showDialog = false"
		>
			<div class="fixed inset-0 bg-black/50 backdrop-blur-sm" @click="showDialog = false"></div>
			<div class="relative z-10 w-full max-w-lg rounded-2xl bg-white shadow-2xl">
				<div class="flex items-center justify-between border-b border-outline-gray-1 px-6 py-4">
					<div>
						<h3 class="text-base font-semibold text-ink-gray-9">
							{{ editingIdx === -1 ? 'Add Location' : editForm.location_name || 'Edit Location' }}
						</h3>
						<p class="mt-0.5 text-p-sm text-ink-gray-5">
							Customers pick this location at checkout; the map shows it on the confirmation page.
						</p>
					</div>
					<button
						class="flex size-8 items-center justify-center rounded-lg text-ink-gray-5 transition-colors hover:bg-surface-gray-2 hover:text-ink-gray-8"
						@click="showDialog = false"
					>
						<X class="size-4" />
					</button>
				</div>
				<div class="space-y-4 px-6 py-5">
					<div>
						<label class="mb-1.5 block text-sm font-medium text-ink-gray-7">Location name</label>
						<input
							v-model="editForm.location_name"
							type="text"
							class="w-full rounded-lg border border-outline-gray-1 bg-surface-white px-3 py-2.5 text-sm text-ink-gray-8 placeholder:text-ink-gray-4 focus:border-outline-gray-2 focus:outline-none focus:ring-2 focus:ring-ink-gray-3"
							placeholder="e.g. Main Store — Rahim Yar Khan"
						/>
					</div>
					<div>
						<label class="mb-1.5 block text-sm font-medium text-ink-gray-7">Address</label>
						<textarea
							v-model="editForm.address"
							rows="3"
							class="w-full rounded-lg border border-outline-gray-1 bg-surface-white px-3 py-2.5 text-sm text-ink-gray-8 placeholder:text-ink-gray-4 focus:border-outline-gray-2 focus:outline-none focus:ring-2 focus:ring-ink-gray-3"
							placeholder="Street, area, city"
						/>
					</div>
					<div>
						<label class="mb-1.5 block text-sm font-medium text-ink-gray-7">Map location</label>
						<div class="mb-2 flex rounded-lg border border-outline-gray-1 p-0.5">
							<button
								type="button"
								class="flex-1 rounded-md px-3 py-1.5 text-sm font-medium"
								:class="editForm.mode === 'link' ? 'bg-ink-gray-8 text-white' : 'bg-surface-gray-2 text-ink-gray-8'"
								@click="editForm.mode = 'link'"
							>
								Google Maps link
							</button>
							<button
								type="button"
								class="flex-1 rounded-md px-3 py-1.5 text-sm font-medium"
								:class="editForm.mode === 'coords' ? 'bg-ink-gray-8 text-white' : 'bg-surface-gray-2 text-ink-gray-8'"
								@click="editForm.mode = 'coords'"
							>
								Latitude / longitude
							</button>
						</div>
						<input
							v-if="editForm.mode === 'link'"
							v-model="editForm.google_maps_link"
							type="text"
							class="w-full rounded-lg border border-outline-gray-1 bg-surface-white px-3 py-2.5 font-mono text-sm text-ink-gray-8 placeholder:text-ink-gray-4 focus:border-outline-gray-2 focus:outline-none focus:ring-2 focus:ring-ink-gray-3"
							placeholder="https://www.google.com/maps/place/.../@29.1044,70.3298,17z"
						/>
						<div v-else class="grid grid-cols-2 gap-2">
							<input
								v-model="editForm.latitude"
								type="text"
								inputmode="decimal"
								class="w-full rounded-lg border border-outline-gray-1 bg-surface-white px-3 py-2.5 font-mono text-sm text-ink-gray-8 placeholder:text-ink-gray-4 focus:border-outline-gray-2 focus:outline-none focus:ring-2 focus:ring-ink-gray-3"
								placeholder="Latitude, e.g. 28.437106"
							/>
							<input
								v-model="editForm.longitude"
								type="text"
								inputmode="decimal"
								class="w-full rounded-lg border border-outline-gray-1 bg-surface-white px-3 py-2.5 font-mono text-sm text-ink-gray-8 placeholder:text-ink-gray-4 focus:border-outline-gray-2 focus:outline-none focus:ring-2 focus:ring-ink-gray-3"
								placeholder="Longitude, e.g. 70.280557"
							/>
						</div>
					</div>
					<p v-if="editForm.mode === 'link'" class="text-p-sm text-ink-gray-5">
						In Google Maps, long-press the store pin (or use Share → Copy link) and paste the
						link here. The map embed and directions button are built from it.
					</p>
					<p v-else class="text-p-sm text-ink-gray-5">
						Latitude between -90 and 90, longitude between -180 and 180. The map pin sits
						exactly on these coordinates.
					</p>
					<div>
						<label class="mb-1.5 block text-sm font-medium text-ink-gray-7">Phone (optional)</label>
						<input
							v-model="editForm.phone"
							type="text"
							class="w-full rounded-lg border border-outline-gray-1 bg-surface-white px-3 py-2.5 text-sm text-ink-gray-8 placeholder:text-ink-gray-4 focus:border-outline-gray-2 focus:outline-none focus:ring-2 focus:ring-ink-gray-3"
							placeholder="Contact number for the pickup desk"
						/>
					</div>
				</div>
				<div class="flex items-center justify-end gap-2 border-t border-outline-gray-1 px-6 py-4">
					<Button variant="subtle" @click="showDialog = false">Cancel</Button>
					<Button
						variant="solid"
						:disabled="!editForm.location_name.trim() || !editForm.address.trim() || !mapLocationValid"
						@click="saveEdit"
					>
						{{ editingIdx >= 0 ? 'Save Changes' : 'Add Location' }}
					</Button>
				</div>
			</div>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Button, createResource, toast } from 'frappe-ui'
import LucidePlus from '~icons/lucide/plus'
import LucidePencil from '~icons/lucide/pencil'
import LucideTrash2 from '~icons/lucide/trash-2'
import LucideMapPin from '~icons/lucide/map-pin'
import X from '~icons/lucide/x'

interface PickupLocation {
	name?: string
	location_name: string
	address: string
	google_maps_link: string
	latitude?: string
	longitude?: string
	phone: string
}

const props = defineProps<{
	modelValue: PickupLocation[]
}>()

const emit = defineEmits<{
	'update:modelValue': [value: PickupLocation[]]
}>()

const locations = ref<PickupLocation[]>([...props.modelValue])

watch(
	() => props.modelValue,
	(val) => {
		locations.value = [...val]
	},
)

const showDialog = ref(false)
const editingIdx = ref(-1)
const editForm = ref({
	location_name: '',
	address: '',
	google_maps_link: '',
	latitude: '',
	longitude: '',
	phone: '',
	mode: 'link' as 'link' | 'coords',
})

/** Link mode needs a link; coordinate mode needs both numbers within range. */
const mapLocationValid = computed(() => {
	if (editForm.value.mode === 'link') return !!editForm.value.google_maps_link.trim()
	const lat = editForm.value.latitude.trim()
	const lng = editForm.value.longitude.trim()
	if (!lat || !lng) return false
	const latNum = Number(lat)
	const lngNum = Number(lng)
	return (
		Number.isFinite(latNum) &&
		Number.isFinite(lngNum) &&
		latNum >= -90 &&
		latNum <= 90 &&
		lngNum >= -180 &&
		lngNum <= 180
	)
})

function addLocation() {
	editingIdx.value = -1
	editForm.value = {
		location_name: '',
		address: '',
		google_maps_link: '',
		latitude: '',
		longitude: '',
		phone: '',
		mode: 'link',
	}
	showDialog.value = true
}

function editLocation(idx: number) {
	editingIdx.value = idx
	const loc = locations.value[idx]
	editForm.value = {
		location_name: loc.location_name,
		address: loc.address,
		google_maps_link: loc.google_maps_link,
		latitude: loc.latitude || '',
		longitude: loc.longitude || '',
		phone: loc.phone,
		// A stored link reopens in link mode; otherwise show the coordinates.
		mode: loc.google_maps_link ? 'link' : loc.latitude && loc.longitude ? 'coords' : 'link',
	}
	showDialog.value = true
}

function removeLocation(idx: number) {
	locations.value.splice(idx, 1)
	emit('update:modelValue', [...locations.value])
	saveLocations()
}

function saveEdit() {
	const linkMode = editForm.value.mode === 'link'
	const entry = {
		location_name: editForm.value.location_name.trim(),
		address: editForm.value.address.trim(),
		phone: editForm.value.phone.trim(),
		// Only the active mode travels: link mode clears the coordinates and
		// coordinate mode clears the link, so a bad link still throws server-side.
		google_maps_link: linkMode ? editForm.value.google_maps_link.trim() : '',
		latitude: linkMode ? '' : editForm.value.latitude.trim(),
		longitude: linkMode ? '' : editForm.value.longitude.trim(),
	}
	if (editingIdx.value >= 0) {
		locations.value[editingIdx.value] = entry
	} else {
		locations.value.push(entry)
	}
	showDialog.value = false
	emit('update:modelValue', [...locations.value])
	saveLocations()
}

const saveMutation = createResource({
	url: 'shop.api.settings.save_pickup_locations',
	onSuccess: () => toast.success('Pickup locations saved'),
	onError: (error: any) => toast.error(serverErrorMessage(error) || 'Failed to save pickup locations'),
})

/** Frappe's thrown message arrives wrapped in HTML/JSON — pull the text out. */
function serverErrorMessage(error: any): string {
	const raw =
		error?.messages?.[0] ||
		(typeof error?.message === 'string' ? error.message : '') ||
		''
	return raw
		.replace(/<[^>]+>/g, ' ')
		.replace(/\s+/g, ' ')
		.trim()
}

function saveLocations() {
	saveMutation.submit({ locations: locations.value })
}
</script>
