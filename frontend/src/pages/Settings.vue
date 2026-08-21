<template>
	<div class="mx-auto max-w-5xl px-6 py-8">
		<h1 class="text-xl font-semibold text-ink-gray-9">Settings</h1>

		<CatalogListState
			:loading="settings.loading && !settings.data"
			:error="settings.error"
			empty-title=""
			@retry="settings.reload()"
		/>

		<div v-if="settings.data" class="mt-6 space-y-6">
			<CatalogSection title="Store" description="How your store shows up to customers.">
				<FormControl v-model="store.store_name" label="Store name" class="max-w-sm" />
				<CatalogImageInput v-model="store.store_logo" label="Logo" />
				<div class="grid max-w-sm grid-cols-2 gap-4">
					<FormControl :model-value="data.currency" label="Currency" disabled />
					<FormControl :model-value="data.company" label="Company" disabled />
				</div>
				<p class="text-p-sm text-ink-gray-5">
					Currency and company come from your ERPNext setup and cannot be changed here.
				</p>
				<template #footer>
					<Button variant="solid" :loading="saving === 'store'" @click="saveSection('store', store)">
						Save
					</Button>
				</template>
			</CatalogSection>

			<CatalogSection title="Payments" description="Choose how customers pay at checkout.">
				<Switch
					v-model="payments.enable_cod"
					label="Cash on Delivery"
					description="Let customers pay in cash when their order arrives."
				/>
				<FormControl
					v-model="payments.payment_gateway_account"
					type="select"
					label="Online payment gateway"
					:options="gatewayOptions"
					class="max-w-sm"
				/>
				<a
					href="/app/payment-gateway-account"
					target="_blank"
					class="inline-flex items-center gap-1 text-sm text-ink-gray-6 underline hover:text-ink-gray-8"
				>
					Open payment gateway settings in Desk
					<LucideExternalLink class="size-3.5" />
				</a>
				<template #footer>
					<Button
						variant="solid"
						:loading="saving === 'payments'"
						@click="saveSection('payments', payments)"
					>
						Save
					</Button>
				</template>
			</CatalogSection>

			<CatalogSection title="Shipping" description="Delivery charges applied at checkout.">
				<div class="grid max-w-sm grid-cols-2 gap-4">
					<FormControl
						v-model.number="shipping.flat_shipping_rate"
						type="number"
						:label="`Flat rate (${data.currency})`"
						description="0 means shipping is free."
					/>
					<FormControl
						v-model.number="shipping.free_shipping_above"
						type="number"
						:label="`Free shipping above (${data.currency})`"
						description="0 turns this threshold off."
					/>
				</div>
				<FormControl
					v-model="shipping.shipping_account"
					type="select"
					label="Shipping account"
					:options="accountOptions"
					class="max-w-sm"
				/>
				<p class="text-p-sm text-ink-gray-5">
					A shipping account is required for shipping charges to apply on orders.
				</p>
				<template #footer>
					<Button
						variant="solid"
						:loading="saving === 'shipping'"
						@click="saveSection('shipping', shipping)"
					>
						Save
					</Button>
				</template>
			</CatalogSection>

			<CatalogSection title="Fulfillment" description="Who picks, packs and ships your orders.">
				<FormControl
					v-model="fulfillment.fulfillment_provider"
					type="select"
					label="Default provider"
					:options="providerOptions"
					class="max-w-sm"
				/>
				<Switch
					v-model="fulfillment.auto_send_to_fulfillment"
					label="Automatically send paid orders"
					description="Hand an order over as soon as its payment is recorded."
				/>
				<p class="text-p-sm text-ink-gray-5">
					Providers marked as needing setup have to be connected before orders can reach them.
				</p>
				<a
					href="/app/shop-amazon-fulfillment-settings"
					target="_blank"
					class="inline-flex items-center gap-1 text-sm text-ink-gray-6 underline hover:text-ink-gray-8"
				>
					Set up Amazon Multi-Channel Fulfillment in Desk
					<LucideExternalLink class="size-3.5" />
				</a>
				<template #footer>
					<Button
						variant="solid"
						:loading="saving === 'fulfillment'"
						@click="saveSection('fulfillment', fulfillment)"
					>
						Save
					</Button>
				</template>
			</CatalogSection>

			<CatalogSection title="Catalog" description="Pricing, stock and tax defaults.">
				<div class="grid max-w-lg grid-cols-2 gap-4">
					<FormControl
						v-model="catalog.price_list"
						type="select"
						label="Price list"
						:options="listOptions(data.price_lists)"
					/>
					<FormControl
						v-model="catalog.default_warehouse"
						type="select"
						label="Default warehouse"
						:options="data.warehouses || []"
					/>
					<FormControl
						v-model.number="catalog.low_stock_threshold"
						type="number"
						label="Low stock threshold"
					/>
					<FormControl
						v-model="catalog.tax_template"
						type="select"
						label="Tax template"
						:options="taxOptions"
					/>
				</div>
				<Switch
					v-model="catalog.allow_out_of_stock"
					label="Allow out of stock orders"
					description="Customers can order items with zero stock."
				/>
				<Switch
					v-model="catalog.prices_include_tax"
					label="Prices include tax"
					description="Storefront prices are treated as tax inclusive."
				/>
				<template #footer>
					<Button
						variant="solid"
						:loading="saving === 'catalog'"
						@click="saveSection('catalog', catalog)"
					>
						Save
					</Button>
				</template>
			</CatalogSection>

			<CatalogSection title="Fraud Protection" description="Score every checkout against blacklists, velocity, address quality and device fingerprint.">
				<Switch
					v-model="fraud.enable_fraud_check"
					label="Enable fraud check"
					description="Evaluate risk on every COD order and switch high-risk orders to advance payment."
				/>
				<div class="grid max-w-lg grid-cols-2 gap-4">
					<FormControl
						v-model.number="fraud.fraud_advance_threshold"
						type="number"
						label="Advance payment score"
						description="Orders scoring at or above this are switched from COD to online."
					/>
					<FormControl
						v-model.number="fraud.fraud_velocity_max"
						type="number"
						label="Max orders per hour"
						description="Orders from the same phone faster than this are blocked."
					/>
					<FormControl
						v-model.number="fraud.fraud_auto_blacklist_failures"
						type="number"
						label="Auto-blacklist after"
						description="Failed/RTO deliveries for the same customer after this are auto-blacklisted."
					/>
					<div class="grid grid-cols-2 gap-4">
						<FormControl
							v-model.number="fraud.fraud_risky_hour_start"
							type="number"
							label="Risky hour start"
						/>
						<FormControl
							v-model.number="fraud.fraud_risky_hour_end"
							type="number"
							label="Risky hour end"
						/>
					</div>
				</div>
				<Switch
					v-model="fraud.fraud_blacklist_blocks_all"
					label="Blacklist blocks all payments"
					description="When off, blacklisted phones are blocked from COD only; online orders pass (but are logged)."
				/>
				<template #footer>
					<Button
						variant="solid"
						:loading="saving === 'fraud'"
						@click="saveSection('fraud', fraud)"
					>
						Save
					</Button>
				</template>
			</CatalogSection>

			<CatalogSection title="Pakistani Addresses" description="Standardize checkout for Pakistani courier routing.">
				<Switch
					v-model="address_cfg.landmark_required"
					label="Require nearest landmark"
					description="Checkout requires a famous landmark so courier riders can find the address."
				/>
				<div class="max-w-lg">
					<label class="mb-1 block text-sm text-ink-gray-6">Pakistan city list</label>
					<textarea
						v-model="address_cfg.pk_cities"
						rows="4"
						class="w-full rounded-lg border border-outline-gray-1 px-3 py-2 text-sm text-ink-gray-8 focus:outline-none focus:ring-2 focus:ring-ink-gray-4"
						placeholder="Islamabad, Rawalpindi, Lahore, Karachi, ..."
					/>
					<p class="mt-1 text-p-sm text-ink-gray-5">
						Comma-separated canonical cities offered in the checkout city box. Cities outside this list add to the fraud score.
					</p>
				</div>
				<template #footer>
					<Button
						variant="solid"
						:loading="saving === 'address_cfg'"
						@click="saveSection('address_cfg', address_cfg)"
					>
						Save
					</Button>
				</template>
			</CatalogSection>

			<CatalogSection title="Fingerprint Identification" description="Server-verified device fingerprinting for high-value orders via Fingerprint v4.">
				<p class="text-p-sm text-ink-gray-5">
					Every checkout already fingerprints the browser with the free FingerprintJS library.
					When a public key is configured and the cart value crosses the threshold below,
					the v4 agent loads instead and sends an event ID for server-side verification.
				</p>
				<div class="grid max-w-lg grid-cols-2 gap-4">
					<FormControl
						v-model="fingerprint.fingerprint_public_key"
						label="Public key"
						placeholder="e.g. 73Ia25Y0GgzY0HwWAWfD"
					/>
					<FormControl
						v-model="fingerprint.fingerprint_region"
						type="select"
						label="Region"
						:options="[
							{ label: 'Asia (Mumbai) — ap', value: 'ap' },
							{ label: 'Global (US) — us', value: 'us' },
							{ label: 'EU (Frankfurt) — eu', value: 'eu' },
						]"
					/>
					<FormControl
						v-model="fingerprint.fingerprint_secret_key"
						type="password"
						label="Secret key"
						placeholder="Enter to change"
					/>
					<FormControl
						v-model.number="fingerprint.fingerprint_verify_above"
						type="number"
						:label="`Verify orders above (${data.currency})`"
						description="0 means never verify server-side."
					/>
				</div>
				<template #footer>
					<Button
						variant="solid"
						:loading="saving === 'fingerprint'"
						@click="saveSection('fingerprint', fingerprint)"
					>
						Save
					</Button>
				</template>
			</CatalogSection>

			<CatalogSection title="Storefront" description="Your storefront pages are built with Builder.">
				<template #header-action>
					<Button @click="openBuilder">
						<template #prefix><LucideExternalLink class="size-3.5" /></template>
						Edit in Builder
					</Button>
				</template>
				<StorefrontThemes @applied="settings.reload()" />
			</CatalogSection>
		</div>
	</div>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { FormControl, Switch, call, createResource, toast } from 'frappe-ui'

import LucideExternalLink from '~icons/lucide/external-link'

import CatalogImageInput from '@/components/CatalogImageInput.vue'
import CatalogListState from '@/components/CatalogListState.vue'
import CatalogSection from '@/components/CatalogSection.vue'
import StorefrontThemes from '@/components/StorefrontThemes.vue'

const saving = ref('')

const store = reactive({ store_name: '', store_logo: '' })
const payments = reactive({ enable_cod: true, payment_gateway_account: '' })
const shipping = reactive({ flat_shipping_rate: 0, free_shipping_above: 0, shipping_account: '' })
const fulfillment = reactive({ fulfillment_provider: 'manual', auto_send_to_fulfillment: false })
const catalog = reactive({
	price_list: '',
	default_warehouse: '',
	low_stock_threshold: 0,
	tax_template: '',
	allow_out_of_stock: false,
	prices_include_tax: false,
})
const fraud = reactive({
	enable_fraud_check: true,
	fraud_advance_threshold: 70,
	fraud_velocity_max: 2,
	fraud_risky_hour_start: 23,
	fraud_risky_hour_end: 5,
	fraud_auto_blacklist_failures: 2,
	fraud_blacklist_blocks_all: false,
})
const address_cfg = reactive({ landmark_required: true, pk_cities: '' })
const fingerprint = reactive({
	fingerprint_public_key: '',
	fingerprint_secret_key: '',
	fingerprint_region: 'ap',
	fingerprint_verify_above: 0,
})

const settings = createResource({
	url: 'shop.api.settings.get_settings',
	auto: true,
})

const data = computed(() => settings.data || {})

watch(
	() => settings.data,
	(doc) => {
		if (doc) hydrate(doc)
	},
	{ immediate: true },
)

function hydrate(doc: Record<string, any>) {
	Object.assign(store, { store_name: doc.store_name || '', store_logo: doc.store_logo || '' })
	Object.assign(payments, {
		enable_cod: !!doc.enable_cod,
		payment_gateway_account: doc.payment_gateway_account || '',
	})
	Object.assign(shipping, {
		flat_shipping_rate: doc.flat_shipping_rate || 0,
		free_shipping_above: doc.free_shipping_above || 0,
		shipping_account: doc.shipping_account || '',
	})
	Object.assign(fulfillment, {
		fulfillment_provider: doc.fulfillment_provider || 'manual',
		auto_send_to_fulfillment: !!doc.auto_send_to_fulfillment,
	})
	Object.assign(catalog, {
		price_list: doc.price_list || '',
		default_warehouse: doc.default_warehouse || '',
		low_stock_threshold: doc.low_stock_threshold || 0,
		tax_template: doc.tax_template || '',
		allow_out_of_stock: !!doc.allow_out_of_stock,
		prices_include_tax: !!doc.prices_include_tax,
	})
	Object.assign(fraud, {
		enable_fraud_check: !!doc.enable_fraud_check,
		fraud_advance_threshold: doc.fraud_advance_threshold ?? 70,
		fraud_velocity_max: doc.fraud_velocity_max ?? 2,
		fraud_risky_hour_start: doc.fraud_risky_hour_start ?? 23,
		fraud_risky_hour_end: doc.fraud_risky_hour_end ?? 5,
		fraud_auto_blacklist_failures: doc.fraud_auto_blacklist_failures ?? 2,
		fraud_blacklist_blocks_all: !!doc.fraud_blacklist_blocks_all,
	})
	Object.assign(address_cfg, {
		landmark_required: !!doc.landmark_required,
		pk_cities: doc.pk_cities || '',
	})
	Object.assign(fingerprint, {
		fingerprint_public_key: doc.fingerprint_public_key || '',
		fingerprint_secret_key: doc.fingerprint_secret_key || '',
		fingerprint_region: doc.fingerprint_region || 'ap',
		fingerprint_verify_above: doc.fingerprint_verify_above ?? 0,
	})
}

const gatewayOptions = computed(() => [
	{ label: 'No online gateway', value: '' },
	...(data.value.gateway_accounts || []).map(
		(a: { name: string; payment_gateway: string; currency: string }) => ({
			label: `${a.payment_gateway} (${a.currency})`,
			value: a.name,
		}),
	),
])

const accountOptions = computed(() => [
	{ label: 'No shipping account', value: '' },
	...listOptions(data.value.income_accounts),
])

const providerOptions = computed(() =>
	(data.value.fulfillment_providers || []).map(
		(provider: { key: string; label: string; configured: boolean }) => ({
			label: provider.configured ? provider.label : `${provider.label} (needs setup)`,
			value: provider.key,
		}),
	),
)

const taxOptions = computed(() => [
	{ label: 'No tax template', value: '' },
	...listOptions(data.value.tax_templates),
])

function listOptions(names?: string[]) {
	return (names || []).map((name) => ({ label: name, value: name }))
}

async function saveSection(section: string, payload: Record<string, any>) {
	saving.value = section
	try {
		settings.data = await call('shop.api.settings.save_settings', {
			payload: normalize(payload),
		})
		toast.success('Settings saved')
	} catch (error) {
		const messages = (error as { messages?: string[] }).messages
		toast.error(messages?.[0] || 'Could not save settings')
	} finally {
		saving.value = ''
	}
}

function normalize(payload: Record<string, any>) {
	// Empty select values mean "unset" for link fields.
	return Object.fromEntries(
		Object.entries(payload).map(([key, value]) => [key, value === '' ? null : value]),
	)
}

function openBuilder() {
	window.open('/builder', '_blank')
}
</script>
