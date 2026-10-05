<template>
	<!--
		Search rather than a wall of chips.

		The province table holds every city the shop delivers to, so rendering one
		toggle per city meant 369 chips wrapped across the panel: nothing was
		findable and the selected cities were lost in the noise. Now the selected
		cities sit on their own as removable chips, and everything else is reached
		through a search box over a province-grouped list. The list is still one
		click from any city, but the panel stays a fixed height.

		A city name is de-duplicated across provinces, so Alipur — which is in
		both Punjab and Islamabad — is listed once, under whichever province
		comes first. Toggling it is by name, not by province, so offering it twice
		would give two entries that select the identical thing.
	-->
	<div class="max-w-xl space-y-2">
		<div v-if="selected.length" class="flex flex-wrap items-center gap-1.5">
			<span
				v-for="city in selected"
				:key="city.key"
				class="inline-flex items-center gap-1 rounded-full border border-ink-gray-8 bg-ink-gray-1 px-2.5 py-1 text-xs text-ink-gray-8"
			>
				{{ city.name }}
				<button
					type="button"
					class="text-ink-gray-5 transition-colors hover:text-ink-gray-8"
					:aria-label="`Stop offering cash on delivery in ${city.name}`"
					@click="toggle(city.name)"
				>
					<LucideX class="size-3" />
				</button>
			</span>
		</div>

		<div v-if="options.length" class="space-y-2">
			<div class="relative">
				<LucideSearch
					class="pointer-events-none absolute left-2.5 top-1/2 size-4 -translate-y-1/2 text-ink-gray-4"
				/>
				<input
					v-model="query"
					type="text"
					:placeholder="`Search ${options.length} cities…`"
					class="w-full rounded-lg border border-outline-gray-1 bg-surface-white py-2 pl-8 pr-8 text-sm text-ink-gray-8 placeholder:text-ink-gray-4 focus:border-outline-gray-2 focus:outline-none focus:ring-2 focus:ring-ink-gray-3"
					@keydown.down.prevent="move(1)"
					@keydown.up.prevent="move(-1)"
					@keydown.enter.prevent="commitHighlighted()"
					@keydown.esc="query = ''"
				/>
				<button
					v-if="query"
					type="button"
					class="absolute right-2 top-1/2 -translate-y-1/2 text-ink-gray-4 hover:text-ink-gray-7"
					aria-label="Clear search"
					@click="query = ''"
				>
					<LucideX class="size-4" />
				</button>
			</div>

			<div class="max-h-64 overflow-y-auto rounded-lg border border-outline-gray-1">
				<div v-if="!groups.length" class="px-3 py-6 text-center text-sm text-ink-gray-5">
					No city matches “{{ query }}”.
				</div>
				<div v-for="group in groups" :key="group.province" class="border-b border-outline-gray-1 last:border-b-0">
					<div class="sticky top-0 bg-surface-gray-2 px-3 py-1.5 text-xs font-medium text-ink-gray-6">
						{{ group.province }}
					</div>
					<button
						v-for="city in group.cities"
						:key="city.name"
						type="button"
						class="flex w-full items-center justify-between gap-3 px-3 py-1.5 text-left text-sm transition-colors hover:bg-surface-gray-2"
						:class="
							selectedKeys.has(city.name.toLowerCase())
								? 'text-ink-gray-9'
								: 'text-ink-gray-7'
						"
						@click="toggle(city.name)"
					>
						<span class="min-w-0 truncate">{{ city.name }}</span>
						<LucideCheck
							v-if="selectedKeys.has(city.name.toLowerCase())"
							class="size-4 shrink-0 text-ink-gray-8"
						/>
					</button>
				</div>
			</div>
			<p v-if="truncated" class="text-xs text-ink-gray-5">
				Some provinces list more than {{ limit }} cities — search to reach the rest.
			</p>
		</div>

		<FormControl
			v-else
			:model-value="modelValue"
			label="COD allowed cities"
			description="Add cities in Provinces & Cities to choose them here. Leave empty to allow every city."
			class="max-w-sm"
			@update:model-value="$emit('update:modelValue', $event)"
		/>

		<p class="text-xs text-ink-gray-5">
			<template v-if="!selectedKeys.size">
				No city selected — cash on delivery is offered everywhere.
			</template>
			<template v-else>
				{{ selectedKeys.size }} selected — cash on delivery only in{{ selected.length === 1 ? ' this city' : ' these cities' }}.
			</template>
			<button
				v-if="selectedKeys.size"
				type="button"
				class="ml-1 underline"
				@click="$emit('update:modelValue', '')"
			>
				Allow everywhere
			</button>
		</p>
	</div>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { FormControl } from 'frappe-ui'

import LucideCheck from '~icons/lucide/check'
import LucideSearch from '~icons/lucide/search'
import LucideX from '~icons/lucide/x'

// Cities rendered per province before the rest are counted as hidden. The
// province headings are sticky and the box scrolls, so the real navigation aid
// is the search box; this only stops one enormous province from rendering
// thousands of rows at once.
const limit = 250

const props = defineProps<{
	modelValue: string
	provinces: Array<{ province_name: string; cities: string }>
}>()

const emit = defineEmits<{ 'update:modelValue': [string] }>()

const query = ref('')
const highlighted = ref(0)

/**
 * Every city on offer, as `{name, province}`. A selected city that is no longer
 * in the province table is kept with a null province so a stale selection stays
 * visible and clearable instead of silently disappearing from the field.
 */
const options = computed(() => {
	const seen = new Set<string>()
	const out: Array<{ name: string; province: string | null }> = []
	for (const row of props.provinces || []) {
		for (const part of String(row.cities || '').split(',')) {
			const name = part.trim()
			const key = name.toLowerCase()
			if (!name || seen.has(key)) continue
			seen.add(key)
			out.push({ name, province: row.province_name })
		}
	}
	for (const part of String(props.modelValue || '').split(',')) {
		const name = part.trim()
		const key = name.toLowerCase()
		if (!name || seen.has(key)) continue
		seen.add(key)
		out.push({ name, province: null })
	}
	return out
})

const selectedKeys = computed(
	() =>
		new Set(
			String(props.modelValue || '')
				.split(',')
				.map((city) => city.trim().toLowerCase())
				.filter(Boolean),
		),
)

/** Selected cities as `{key, name}`, so v-for keys stay unique and stable. */
const selected = computed(() =>
	[...selectedKeys.value]
		.map((key) => {
			const match = options.value.find((city) => city.name.toLowerCase() === key)
			return { key, name: match ? match.name : key }
		})
		.sort((a, b) => a.name.localeCompare(b.name)),
)

/**
 * Every province is always listed, however many cities it holds.
 *
 * The cap is applied per province, never across the whole list. Punjab alone
 * holds 189 of the 369 cities, so a flat cap of 200 filled the scroll box with
 * Punjab and part of Sindh and the other five provinces never appeared at all
 * — with no search term typed, there was nothing to narrow it down either.
 */
const groups = computed(() => {
	const needle = query.value.trim().toLowerCase()
	const matches = options.value.filter((city) =>
		needle ? city.name.toLowerCase().includes(needle) : true,
	)
	const byProvince = new Map<string, Array<{ name: string }>>()
	for (const city of matches) {
		const province = city.province || 'Not in Provinces & Cities'
		const bucket = byProvince.get(province)
		if (bucket) {
			if (bucket.length < limit) bucket.push({ name: city.name })
		} else {
			byProvince.set(province, [{ name: city.name }])
		}
	}
	return [...byProvince].map(([province, cities]) => ({
		province,
		cities,
		hidden: matches.filter((city) => (city.province || 'Not in Provinces & Cities') === province)
			.length - cities.length,
	}))
})

const truncated = computed(() => groups.value.some((group) => group.hidden > 0))

// A changing list makes a remembered highlight point at the wrong row.
watch([query, () => props.modelValue], () => {
	highlighted.value = 0
})

function move(step: number) {
	const count = groups.value.reduce((total, group) => total + group.cities.length, 0)
	if (!count) return
	highlighted.value = (highlighted.value + step + count) % count
}

function commitHighlighted() {
	let index = 0
	for (const group of groups.value) {
		if (index + group.cities.length > highlighted.value) {
			toggle(group.cities[highlighted.value - index].name)
			return
		}
		index += group.cities.length
	}
}

function toggle(name: string) {
	const next = new Set(selectedKeys.value)
	const key = name.toLowerCase()
	if (next.has(key)) next.delete(key)
	else next.add(key)
	// Written back in the order the picker lists them, so the stored string is
	// stable and does not depend on the order things were clicked.
	emit(
		'update:modelValue',
		options.value
			.map((city) => city.name)
			.filter((city) => next.has(city.toLowerCase()))
			.join(', '),
	)
}
</script>
