<template>
	<Dialog
		:model-value="modelValue"
		:title="title"
		size="3xl"
		:actions="actions"
		@update:model-value="(value) => emit('update:modelValue', value)"
	>
		<template #default>
			<div class="max-h-[65vh] space-y-6 overflow-y-auto pr-1">
				<section>
					<h3 class="mb-3 text-sm font-semibold text-ink-gray-8">Customer</h3>
					<div class="grid gap-3 sm:grid-cols-3">
						<FormControl
							v-model="form.customer.full_name"
							label="Name"
							placeholder="Who is the order for?"
							required
						/>
						<FormControl
							v-model="form.customer.email"
							type="email"
							label="Email"
							placeholder="Where the receipt goes"
							required
						/>
						<FormControl
							v-model="form.customer.phone"
							type="tel"
							label="Phone"
							placeholder="The number to call"
							required
						/>
					</div>
				</section>

				<section>
					<h3 class="mb-3 text-sm font-semibold text-ink-gray-8">Delivery</h3>
					<div class="grid gap-3 sm:grid-cols-2">
						<FormControl
							v-model="form.address.address_line1"
							label="Address"
							placeholder="Street and house number"
							required
						/>
						<FormControl
							v-model="form.address.address_line2"
							label="Address line 2"
							placeholder="Flat, floor, block"
						/>
						<Autocomplete
							v-model="city"
							label="City"
							placeholder="Search the cities you deliver to"
							:options="cityOptions"
							required
						/>
						<Autocomplete
							v-model="province"
							label="Province"
							placeholder="Search the provinces"
							:options="provinceOptions"
						/>
						<FormControl
							v-model="form.address.country"
							type="select"
							label="Country"
							:options="countryOptions"
						/>
						<FormControl
							v-model="form.address.pincode"
							label="Pincode"
							placeholder="The pincode"
							required
						/>
						<FormControl
							v-model="form.address.landmark"
							label="Nearest landmark"
							placeholder="So the rider can find them"
							:description="landmarkHint"
						/>
						<FormControl
							v-model="form.address.alt_phone"
							type="tel"
							label="Alternative phone"
							placeholder="Another number for the delivery"
						/>
					</div>
				</section>

				<section>
					<div class="mb-3 flex items-center justify-between">
						<h3 class="text-sm font-semibold text-ink-gray-8">Items</h3>
						<Button size="sm" @click="addLine">
							<template #prefix><LucidePlus class="size-3.5" /></template>
							Add item
						</Button>
					</div>

					<div class="space-y-3">
						<div
							v-for="(line, index) in form.lines"
							:key="line.key"
							class="rounded-lg border border-outline-gray-1 p-3"
						>
							<div class="grid items-end gap-3 sm:grid-cols-[2fr_2fr_5rem_7rem_2rem]">
								<Autocomplete
									:model-value="line.product"
									label="Product"
									placeholder="Search the catalogue"
									:options="productOptions"
									@update:query="(query) => searchProducts(query)"
									@update:model-value="(option) => pickProduct(line, option)"
								/>
								<Autocomplete
									:model-value="line.option"
									label="Size or colour"
									placeholder="Pick one"
									:options="line.options"
									@update:model-value="(option) => pickOption(line, option)"
								/>
								<FormControl v-model.number="line.qty" type="number" label="Qty" />
								<FormControl v-model.number="line.rate" type="number" label="Rate" />
								<Button
									variant="ghost"
									theme="red"
									title="Remove this line"
									:disabled="form.lines.length === 1"
									@click="removeLine(index)"
								>
									<template #icon><LucideTrash2 class="size-4" /></template>
								</Button>
							</div>
							<p
								v-if="line.stock !== null && line.stock < (line.qty || 0)"
								class="mt-2 text-p-sm text-ink-red-8"
							>
								Only {{ line.stock }} in stock.
							</p>
						</div>
					</div>
				</section>

				<section>
					<h3 class="mb-3 text-sm font-semibold text-ink-gray-8">Payment</h3>
					<div class="grid gap-3 sm:grid-cols-2">
						<FormControl
							v-model="form.payment_method"
							type="select"
							label="Method"
							:options="paymentOptions"
						/>
						<FormControl
							v-model="form.notes"
							type="textarea"
							:rows="2"
							label="Note"
							placeholder="What the customer asked for"
						/>
						<div>
							<FormControl
								v-model="form.coupon_code"
								label="Coupon code"
								placeholder="If the customer has one"
								@blur="checkCoupon"
							/>
							<p v-if="coupon.valid" class="mt-1 text-p-sm text-ink-green-7">
								{{ coupon.code }} takes {{ coupon.formatted_discount }} off.
							</p>
							<p v-else-if="coupon.message" class="mt-1 text-p-sm text-ink-red-8">
								{{ coupon.message }}
							</p>
						</div>
					</div>
					<div class="mt-3">
						<Switch
							v-model="form.send_email"
							label="Send the customer a receipt"
							class="!w-auto"
						/>
					</div>
				</section>

				<p
					v-if="error"
					class="rounded-lg border border-outline-red-1 bg-surface-red-1 p-3 text-p-sm text-ink-red-8"
				>
					{{ error }}
				</p>
			</div>
		</template>
	</Dialog>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { Autocomplete, Button, Dialog, FormControl, Switch, call, toast } from 'frappe-ui'

import LucidePlus from '~icons/lucide/plus'
import LucideTrash2 from '~icons/lucide/trash-2'

interface Option {
	label: string
	value: string
}

interface LineOption extends Option {
	rate: number
	stock: number
}

interface Line {
	key: number
	product: Option | null
	options: LineOption[]
	option: LineOption | null
	qty: number
	rate: number
	stock: number | null
}

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
	'update:modelValue': [value: boolean]
	created: [name: string]
}>()

const title = 'New order'
const error = ref('')
const busy = ref(false)
let nextKey = 1

const form = reactive({
	customer: { full_name: '', email: '', phone: '' },
	address: {
		address_line1: '',
		address_line2: '',
		city: '',
		state: '',
		country: '',
		pincode: '',
		landmark: '',
		alt_phone: '',
	},
	lines: [] as Line[],
	payment_method: 'cod',
	notes: '',
	coupon_code: '',
	send_email: true,
})

// The city and the province come from autocompletes, which hand back an
// option rather than a string, so they are kept apart from the form and
// reduced to their value on the way out.
const city = ref<Option | null>(null)
const province = ref<Option | null>(null)

// The coupon is checked against the order as it stands, so the merchant
// sees what it takes off before the order is placed.
const coupon = reactive({ valid: 0, message: '', code: '', formatted_discount: '' })

const settings = ref<Record<string, any>>({})
const catalogue = ref<Record<string, any>>({})
const productChoices = ref<Option[]>([])

const cityOptions = computed<Option[]>(() =>
	(settings.value.cities || []).map((city: string) => ({ label: city, value: city })),
)
const provinceOptions = computed<Option[]>(() =>
	(settings.value.provinces || []).map((province: string) => ({ label: province, value: province })),
)
const countryOptions = computed<Option[]>(() =>
	(settings.value.countries || []).map((country: string) => ({ label: country, value: country })),
)
const paymentOptions = computed<Option[]>(() =>
	(settings.value.payment_methods || []).map((method: any) => ({ label: method.label, value: method.value })),
)
const landmarkHint = computed(() =>
	settings.value.landmark_required
		? 'Required - the delivery riders need it.'
		: 'Optional, but it helps the rider.',
)
const productOptions = computed<Option[]>(() => productChoices.value)

/** What the lines come to, which is what a coupon is measured against. */
const subtotal = computed(() =>
	form.lines.reduce((total, line) => total + Number(line.rate || 0) * Number(line.qty || 0), 0),
)

async function checkCoupon() {
	const code = form.coupon_code.trim()
	if (!code) {
		coupon.valid = 0
		coupon.message = ''
		return
	}
	try {
		const result = await call('shop.api.manual_orders.check_coupon', { code, subtotal: subtotal.value })
		coupon.valid = result?.valid ? 1 : 0
		coupon.message = result?.message || ''
		coupon.code = result?.code || ''
		coupon.formatted_discount = result?.formatted_discount || ''
	} catch (e) {
		coupon.valid = 0
		coupon.message = 'Could not check that coupon'
	}
}

const actions = computed(() => [
	{
		label: 'Cancel',
		variant: 'subtle' as const,
		onClick: () => emit('update:modelValue', false),
	},
	{
		label: 'Create order',
		variant: 'solid' as const,
		loading: busy.value,
		onClick: () => create(),
	},
])

watch(
	() => props.modelValue,
	async (open) => {
		if (!open) return
		error.value = ''
		await load()
	},
)

async function load() {
	if (!settings.value.cities) {
		settings.value = await call('shop.api.manual_orders.form_options')
		form.payment_method = settings.value.payment_methods?.[0]?.value || 'cod'
		form.address.country = settings.value.default_country || ''
	}
	await searchProducts('')
}

async function searchProducts(query: string) {
	try {
		const products = await call('shop.api.manual_orders.catalogue', { search: query, limit: 20 })
		catalogue.value = {}
		productChoices.value = products.map((product: any) => {
			catalogue.value[product.name] = product
			return { label: product.product_name, value: product.name }
		})
	} catch (e) {
		toast.error('Could not load the catalogue')
	}
}

function pickProduct(line: Line, option: Option | null) {
	line.product = option
	line.options = []
	line.option = null
	line.stock = null
	if (!option) return
	const product = catalogue.value[option.value]
	if (!product) return
	line.options = (product.options || []).map((item: any) => ({
		label: item.label,
		value: item.item_code,
		rate: item.rate,
		stock: item.stock,
	}))
	pickOption(line, line.options[0] || null)
}

function pickOption(line: Line, option: LineOption | null) {
	line.option = option
	if (!option) return
	line.rate = option.rate
	line.stock = option.stock
}

function addLine() {
	form.lines.push({ key: nextKey++, product: null, options: [], option: null, qty: 1, rate: 0, stock: null })
}

function removeLine(index: number) {
	form.lines.splice(index, 1)
}

async function create() {
	if (busy.value) return
	busy.value = true
	error.value = ''
	try {
		const payload = {
			customer: { ...form.customer },
			address: {
				...form.address,
				city: city.value?.value || '',
				state: province.value?.value || '',
			},
			items: form.lines.map((line) => ({
				item_code: line.option?.value || '',
				qty: line.qty,
				rate: line.rate,
			})),
			payment_method: form.payment_method,
			notes: form.notes,
			coupon_code: form.coupon_code.trim(),
			send_email: form.send_email,
		}
		const result = await call('shop.api.manual_orders.create', { payload })
		toast.success('Order created')
		reset()
		emit('update:modelValue', false)
		emit('created', result.order)
	} catch (e: any) {
		error.value = e?.messages?.[0] || e?.message || 'Could not create the order'
	} finally {
		busy.value = false
	}
}

function reset() {
	form.customer = { full_name: '', email: '', phone: '' }
	form.address = {
		address_line1: '',
		address_line2: '',
		city: '',
		state: '',
		country: settings.value.default_country || '',
		pincode: '',
		landmark: '',
		alt_phone: '',
	}
	city.value = null
	province.value = null
	form.lines = []
	form.notes = ''
	form.coupon_code = ''
	coupon.valid = 0
	coupon.message = ''
	coupon.code = ''
	coupon.formatted_discount = ''
	form.send_email = true
	addLine()
}

addLine()
</script>
