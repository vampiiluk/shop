(function () {
	const state = {
		product: window.page_data && window.page_data.product,
		selection: {},
		cart: (window.page_data && window.page_data.cart) || null,
	};

	// Device fingerprint — supports four providers:
	//   thumbmarkjs      – free, no API key, self-hosted via CDN
	//   fingerprintjs-oss – free, no API key, self-hosted via CDN
	//   fingerprintjs-pro – paid API, requires public key
	//   creepjs           – free, self-hosted via CDN, most signals
	// Checkout whitelists store fields flat on page_data; other pages nest
	// them under store. Fall back so both shapes resolve.
	function storeContext() {
		const data = window.page_data || {};
		return data.store || data;
	}
	function loadFingerprint() {
		const store = storeContext();
		const provider = store.fingerprint_provider || "thumbmarkjs";

		if (provider === "fingerprintjs-pro") {
			if (!store.fp_public_key) {
				return Promise.resolve({ visitorId: "", requestId: "", provider: "fingerprintjs-pro" });
			}
			return import(
				"https://metrics.sananahmad.dpdns.org/web/v4/" + encodeURIComponent(store.fp_public_key)
			)
				.then((Fingerprint) => Fingerprint.start({
					region: store.fp_region || "ap",
					endpoint: "https://metrics.sananahmad.dpdns.org",
				}))
				.then((agent) => agent.get())
				.then((result) => ({
					visitorId: result.visitorId || result.visitor_id || "",
					requestId: result.requestId || result.event_id || "",
					provider: "fingerprintjs-pro",
				}))
				.catch((error) => {
					console.warn("fingerprintjs-pro unavailable:", error && error.message);
					return { visitorId: "", requestId: "", provider: "fingerprintjs-pro" };
				});
		}

		if (provider === "fingerprintjs-oss") {
			return import("https://cdn.jsdelivr.net/npm/@fingerprintjs/fingerprintjs@4/dist/fingerprintjs.min.js")
				.then((FingerprintJS) => FingerprintJS.load())
				.then((agent) => agent.get())
				.then((result) => ({
					visitorId: result.visitorId || "",
					requestId: "",
					provider: "fingerprintjs-oss",
					// Capture raw browser signals from components
					signals: result.components || {},
				}))
				.catch((error) => {
					console.warn("fingerprintjs-oss unavailable:", error && error.message);
					return { visitorId: "", requestId: "", provider: "fingerprintjs-oss" };
				});
		}

		if (provider === "creepjs") {
			// CreepJS self-hosted: check cache first, then iframe + postMessage
			const CACHE_KEY = "creepjs_fp";
			const CACHE_TTL = 24 * 60 * 60 * 1000; // 24 hours

			// Return cached fingerprint if fresh
			try {
				const cached = JSON.parse(localStorage.getItem(CACHE_KEY) || "null");
				if (cached && cached.hash && (Date.now() - cached.ts) < CACHE_TTL) {
					return Promise.resolve({
						visitorId: cached.hash,
						requestId: "",
						provider: "creepjs",
						signals: cached.sections || {},
					});
				}
			} catch(e) {}

			// Compute via iframe
			return new Promise((resolve) => {
				const timeout = setTimeout(() => {
					try { document.body.removeChild(iframe); } catch(e) {}
					resolve({ visitorId: "", requestId: "", provider: "creepjs" });
				}, 15000);

				const iframe = document.createElement("iframe");
				iframe.style.cssText = "position:fixed;top:-9999px;left:-9999px;width:1px;height:1px;opacity:0;pointer-events:none;";
				iframe.src = "/assets/shop/fingerprint/index.html";

				const handler = (event) => {
					if (event.data && event.data.type === "creepjs-fingerprint") {
						clearTimeout(timeout);
						window.removeEventListener("message", handler);
						try { document.body.removeChild(iframe); } catch(e) {}
						const d = event.data.data || {};
						const hash = d.hash || "";
						// Cache the result
						if (hash) {
							try {
								localStorage.setItem(CACHE_KEY, JSON.stringify({
									hash: hash,
									sections: d.sections || {},
									ts: Date.now(),
								}));
							} catch(e) {}
						}
						resolve({
							visitorId: hash,
							requestId: "",
							provider: "creepjs",
							signals: d.sections || d,
						});
					}
				};
				window.addEventListener("message", handler);
				document.body.appendChild(iframe);
			});
		}

		// Default: thumbmarkjs
		return import("https://cdn.jsdelivr.net/npm/@thumbmarkjs/thumbmarkjs/dist/thumbmark.umd.js")
			.then(() => {
				const tm = new window.ThumbmarkJS.Thumbmark({ logging: false });
				return tm.get();
			})
			.then((result) => ({
				visitorId: result.thumbmark || "",
				requestId: "",
				provider: "thumbmarkjs",
			}))
			.catch((error) => {
				console.warn("thumbmarkjs unavailable:", error && error.message);
				return { visitorId: "", requestId: "", provider: "thumbmarkjs" };
			});
	}

	function esc(value) {
		const div = document.createElement("div");
		div.textContent = value == null ? "" : String(value);
		return div.innerHTML;
	}

	async function call(method, args) {
		const response = await fetch(`/api/method/${method}`, {
			method: "POST",
			headers: {
				"Content-Type": "application/json",
				"X-Frappe-CSRF-Token": (window.frappe && window.frappe.csrf_token) || "",
			},
			body: JSON.stringify(args || {}),
		});
		const body = await response.json();
		if (!response.ok) throw new Error(serverMessage(body));
		return body.message;
	}

	function serverMessage(body) {
		try {
			const messages = JSON.parse(body._server_messages || "[]");
			if (messages.length) return JSON.parse(messages[0]).message.replace(/<[^>]+>/g, "");
		} catch (e) {}
		// Fallback: try exc (exception string) or message field
		try {
			if (body.message && typeof body.message === "string") return body.message.replace(/<[^>]+>/g, "");
			if (body.exc) {
				var excLines = body.exc.split("\n").filter(function(l){return l.indexOf("frappe.exceptions")===-1 && l.trim();});
				if (excLines.length) return excLines[excLines.length-1].replace(/<[^>]+>/g, "");
			}
		} catch(e) {}
		return "Something went wrong. Please try again.";
	}

	function showError(message) {
		const target = document.querySelector('[data-shop="error"]');
		if (target) {
			target.textContent = message;
			target.style.display = "block";
		} else {
			alert(message);
		}
	}

	function updateCartCount(count) {
		document.querySelectorAll('[data-shop="cart-count"]').forEach((el) => {
			el.textContent = count;
			el.dataset.empty = count ? "false" : "true";
		});
	}

	async function refreshCartCount() {
		if (!document.querySelector('[data-shop="cart-count"]')) return;
		if (window.page_data && window.page_data.cart) {
			updateCartCount(window.page_data.cart.item_count || 0);
			return;
		}
		try {
			const cart = await call("shop.storefront.cart.get_cart");
			updateCartCount(cart.item_count || 0);
		} catch (e) {}
	}

	async function addToCart(button) {
		const itemCode = button.dataset.itemCode;
		if (!itemCode) return;
		button.disabled = true;
		const label = button.textContent;
		try {
			const cart = await call("shop.storefront.cart.add_item", { item_code: itemCode });
			updateCartCount(cart.item_count || 0);
			if (drawerElement()) {
				renderDrawer(cart);
				openDrawer();
			} else {
				button.textContent = button.dataset.addedLabel || "Added";
				setTimeout(() => (button.textContent = label), 1500);
			}
		} catch (error) {
			showError(error.message);
		} finally {
			button.disabled = false;
		}
	}

	function drawerElement() {
		return document.querySelector('[data-shop="cart-drawer"]');
	}

	function openDrawer() {
		const drawer = drawerElement();
		if (!drawer) return false;
		drawer.dataset.open = "true";
		document.documentElement.style.overflow = "hidden";
		return true;
	}

	function closeDrawer() {
		const drawer = drawerElement();
		if (!drawer) return;
		drawer.dataset.open = "false";
		document.documentElement.style.overflow = "";
	}

	async function toggleDrawer() {
		const cart = await call("shop.storefront.cart.get_cart");
		renderDrawer(cart);
		openDrawer();
	}

	function renderDrawer(cart) {
		state.cart = cart;
		updateCartCount(cart.item_count || 0);
		const drawer = drawerElement();
		if (!drawer) return;
		const total = drawer.querySelector('[data-shop="drawer-total"]');
		if (total) total.textContent = cart.formatted_total || "";
		const list = drawer.querySelector('[data-shop="drawer-items"]');
		if (!list) return;
		if (!cart.items.length) {
			list.innerHTML = '<p class="drawer-empty">Your cart is empty.</p>';
			return;
		}
		list.innerHTML = cart.items
			.map(
				(item) => `
			<div class="drawer-item">
				<img class="drawer-thumb" src="${esc(item.image || "")}" alt="" loading="lazy">
				<div class="drawer-info">
					<a class="drawer-name" href="/product/${esc(item.slug || "")}">${esc(item.product_name || item.item_code)}</a>
					<span class="drawer-rate">${esc(item.formatted_rate || "")}</span>
					<div class="drawer-qty">
						<button type="button" data-drawer-step="-1" data-item-code="${esc(item.item_code)}" aria-label="Decrease quantity">&minus;</button>
						<span>${esc(item.qty)}</span>
						<button type="button" data-drawer-step="1" data-item-code="${esc(item.item_code)}" aria-label="Increase quantity">+</button>
						<button type="button" class="drawer-remove" data-drawer-step="0" data-item-code="${esc(item.item_code)}">Remove</button>
					</div>
				</div>
				<span class="drawer-amount">${esc(item.formatted_amount || "")}</span>
			</div>`
			)
			.join("");
	}

	async function drawerStep(itemCode, step) {
		const row = state.cart && state.cart.items.find((item) => item.item_code === itemCode);
		const qty = step === 0 ? 0 : Math.max((row ? row.qty : 1) + step, 0);
		try {
			const cart = await call("shop.storefront.cart.set_qty", { item_code: itemCode, qty: qty });
			renderDrawer(cart);
		} catch (error) {
			showError(error.message);
		}
	}

	async function setQty(itemCode, qty) {
		try {
			await call("shop.storefront.cart.set_qty", { item_code: itemCode, qty: qty });
			window.location.reload();
		} catch (error) {
			showError(error.message);
		}
	}

	function rowQty(itemCode) {
		const row = window.page_data && window.page_data.cart
			? window.page_data.cart.items.find((item) => item.item_code === itemCode)
			: null;
		return row ? row.qty : 1;
	}

	function mainImage() {
		return document.querySelector('[data-shop="main-image"]');
	}

	function showImage(src) {
		const target = mainImage();
		if (!target || !src || target.getAttribute("src") === src) return;
		target.setAttribute("src", src);
		document.querySelectorAll('[data-shop="thumb"]').forEach((thumb) => {
			thumb.dataset.selected = thumb.dataset.image === src ? "true" : "false";
		});
	}

	function initGallery() {
		const first = document.querySelector('[data-shop="thumb"]');
		if (first) first.dataset.selected = "true";
	}

	function initVariantPicker() {
		const product = state.product;
		if (!product || !product.has_variants) return;
		const defaultVariant = product.variants.find(
			(variant) => variant.item_code === product.default_item_code
		);
		if (defaultVariant) state.selection = Object.assign({}, defaultVariant.attributes);
		syncVariantUI();
	}

	function selectOption(button) {
		state.selection[button.dataset.attribute] = button.dataset.value;
		syncVariantUI();
	}

	function selectedVariant() {
		const product = state.product;
		if (!product) return null;
		return product.variants.find((variant) =>
			Object.entries(variant.attributes).every(
				([attribute, value]) => state.selection[attribute] === value
			)
		);
	}

	function syncVariantUI() {
		document.querySelectorAll('[data-shop="variant-option"]').forEach((button) => {
			const selected = state.selection[button.dataset.attribute] === button.dataset.value;
			button.dataset.selected = selected ? "true" : "false";
			button.setAttribute("aria-pressed", selected ? "true" : "false");
		});
		const variant = selectedVariant();
		const buttons = document.querySelectorAll('[data-shop="add-to-cart"], [data-shop="buy-now"]');
		if (!variant) {
			buttons.forEach((button) => (button.disabled = true));
			return;
		}
		buttons.forEach((button) => {
			button.dataset.itemCode = variant.item_code;
			button.disabled = !variant.in_stock;
			if (!variant.in_stock)
				button.textContent = button.dataset.outOfStockLabel || "Out of stock";
			else if (button.dataset.label) button.textContent = button.dataset.label;
		});
		if (variant.formatted_price) {
			document.querySelectorAll('[data-shop="pdp-price"]').forEach((price) => {
				price.textContent = variant.formatted_price;
			});
		}
		syncSavings(variant);
		if (variant.image) showImage(variant.image);
	}

	function syncSavings(variant) {
		const savings = document.querySelector('[data-shop="pdp-savings"]');
		if (savings) {
			savings.hidden = !variant.formatted_savings;
			const amount = savings.querySelectorAll("span")[1];
			if (amount && variant.formatted_savings) amount.textContent = variant.formatted_savings;
		}
		const badge = document.querySelector('[data-shop="pdp-discount"]');
		if (badge) {
			badge.hidden = !variant.discount_pct;
			const pct = badge.querySelector("span");
			if (pct && variant.discount_pct) pct.textContent = variant.discount_pct;
		}
	}

	async function buyNow(button) {
		const itemCode = button.dataset.itemCode;
		if (!itemCode) return;
		button.disabled = true;
		try {
			await call("shop.storefront.cart.add_item", { item_code: itemCode });
			window.location.href = "/checkout";
		} catch (error) {
			showError(error.message);
			button.disabled = false;
		}
	}

	async function submitCheckout(form) {
		const data = new FormData(form);
		const getVal = (name) => {
			const input = form.querySelector(`[name="${name}"]`);
			return (data.get(name) || (input ? input.value : "") || "").trim();
		};
		// Pickup hands the order over in person: a location must be chosen first.
		const chosenMethod = form.querySelector('input[name="payment_method"]:checked');
		if (chosenMethod && chosenMethod.value === "pickup" && !data.get("pickup_location")) {
			showError("Choose where you would like to pick up your order");
			return;
		}
		const submit = form.querySelector('[type="submit"]');
		if (submit) submit.disabled = true;
		try {
			const fp = await loadFingerprint();
			const result = await call("shop.storefront.checkout.place_order", {
				customer: {
					email: getVal("email"),
					full_name: getVal("full_name") || getVal("name"),
					phone: getVal("phone"),
				},
				address: {
					address_line1: getVal("address_line1"),
					address_line2: getVal("address_line2"),
					city: getVal("city"),
					state: getVal("state"),
					country: getVal("country") || "Pakistan",
					pincode: getVal("pincode"),
					landmark: getVal("landmark") || getVal("custom_landmark"),
					alt_phone: getVal("alt_phone") || getVal("custom_alt_phone"),
				},
				payment_method: getVal("payment_method") || "cod",
				pickup_location: getVal("pickup_location"),
				device_fingerprint: fp.visitorId,
				fp_request_id: fp.requestId,
				fingerprint_provider: fp.provider,
				fp_signals: fp.signals ? JSON.stringify(fp.signals) : "",
			});
			window.location.href = result.payment_url || result.confirmation_url;
		} catch (error) {
			showError(error.message);
			if (submit) submit.disabled = false;
		}
	}

	document.addEventListener("click", (event) => {
		const stepper = event.target.closest("[data-drawer-step]");
		if (stepper) {
			drawerStep(stepper.dataset.itemCode, parseInt(stepper.dataset.drawerStep, 10));
			return;
		}
		const target = event.target.closest("[data-shop]");
		if (!target) return;
		const action = target.dataset.shop;
		if (action === "cart-toggle" && drawerElement()) {
			event.preventDefault();
			toggleDrawer();
		} else if (action === "drawer-close" || action === "drawer-backdrop") closeDrawer();
		else if (action === "coupon-remove") removeCoupon();
		else if (action === "add-to-cart") addToCart(target);
		else if (action === "buy-now") buyNow(target);
		else if (action === "thumb") showImage(target.dataset.image);
		else if (action === "rating-star") selectRating(parseInt(target.dataset.value, 10));
		else if (action === "variant-option") selectOption(target);
		else if (action === "qty-inc") setQty(target.dataset.itemCode, rowQty(target.dataset.itemCode) + 1);
		else if (action === "qty-dec") setQty(target.dataset.itemCode, rowQty(target.dataset.itemCode) - 1);
		else if (action === "remove") setQty(target.dataset.itemCode, 0);
	});

	document.addEventListener("keydown", (event) => {
		if (event.key === "Escape") closeDrawer();
	});

	document.addEventListener("submit", (event) => {
		const form = event.target.closest("[data-shop]");
		if (!form) return;
		if (form.dataset.shop === "checkout-form") {
			event.preventDefault();
			submitCheckout(form);
		} else if (form.dataset.shop === "review-form") {
			event.preventDefault();
			submitReview(form);
		} else if (form.dataset.shop === "coupon-form") {
			event.preventDefault();
			applyCoupon(form);
		} else if (form.dataset.shop === "return-form") {
			event.preventDefault();
			submitReturn(form);
		} else if (form.dataset.shop === "search-form") {
			event.preventDefault();
			const term = form.querySelector('[name="search"]');
			window.location.href = "/products?search=" + encodeURIComponent(term ? term.value : "");
		}
	});

	function loggedIn() {
		const match = document.cookie.match(/(?:^|; )user_id=([^;]*)/);
		return !!match && decodeURIComponent(match[1]) !== "Guest";
	}

	function initReviewForm() {
		const form = document.querySelector('[data-shop="review-form"]');
		const prompt = document.querySelector('[data-shop="review-signin"]');
		if (!form) return;
		if (loggedIn()) {
			form.style.display = "flex";
			if (prompt) prompt.style.display = "none";
		} else if (prompt) {
			prompt.setAttribute(
				"href",
				"/login?redirect-to=" + encodeURIComponent(window.location.pathname)
			);
		}
	}

	function selectRating(value) {
		state.reviewRating = value;
		document.querySelectorAll('[data-shop="rating-star"]').forEach((star) => {
			star.dataset.selected = parseInt(star.dataset.value, 10) <= value ? "true" : "false";
		});
	}

	async function submitReview(form) {
		if (!state.reviewRating) {
			showError("Pick a star rating first.");
			return;
		}
		const data = new FormData(form);
		const submit = form.querySelector('[type="submit"]');
		if (submit) submit.disabled = true;
		try {
			await call("shop.storefront.reviews.add_review", {
				product: window.page_data.product.name,
				rating: state.reviewRating,
				title: data.get("title"),
				review: data.get("review"),
			});
			window.location.reload();
		} catch (error) {
			showError(error.message);
			if (submit) submit.disabled = false;
		}
	}

	async function applyCoupon(form) {
		const input = form.querySelector('[name="code"]');
		if (!input || !input.value.trim()) return;
		const submit = form.querySelector('[type="submit"]');
		if (submit) submit.disabled = true;
		try {
			await call("shop.storefront.cart.apply_coupon", { code: input.value.trim() });
			window.location.reload();
		} catch (error) {
			showError(error.message);
			if (submit) submit.disabled = false;
		}
	}

	async function removeCoupon() {
		try {
			await call("shop.storefront.cart.remove_coupon", {});
			window.location.reload();
		} catch (error) {
			showError(error.message);
		}
	}

	function applySavedAddress(picker) {
		const addresses = (window.page_data && window.page_data.addresses) || [];
		const chosen = addresses.find((address) => address.name === picker.value);
		const fields = ["address_line1", "address_line2", "city", "state", "country", "pincode", "landmark", "alt_phone"];
		fields.forEach((field) => {
			const input = document.querySelector(`[data-shop="checkout-form"] [name="${field}"]`);
			if (input) input.value = (chosen && chosen[field]) || "";
		});
	}

	// COD restricted to selected cities: hide the option while the chosen
	// city is outside the list and move the customer to another method.
	function initCodRestriction() {
		const form = document.querySelector('[data-shop="checkout-form"]');
		const cityInput = form && form.querySelector('[name="city"]');
		const codRadio = form && form.querySelector('input[name="payment_method"][value="cod"]');
		if (!cityInput || !codRadio) return;
		const allowed = (storeContext().cod_allowed_cities || []).map((c) =>
			String(c).trim().toLowerCase()
		);
		if (!allowed.length) return;
		const option = codRadio.closest("label") || codRadio.parentElement;
		if (!option) return;
		const shownDisplay = option.style.display;
		function sync() {
			const city = (cityInput.value || "").trim().toLowerCase();
			const eligible = !city || allowed.includes(city);
			option.style.display = eligible ? shownDisplay : "none";
			if (!eligible && codRadio.checked) {
				const fallback =
					form.querySelector('input[name="payment_method"][value="advance"]') ||
					form.querySelector('input[name="payment_method"][value="gateway"]') ||
					form.querySelector('input[name="payment_method"][value="pickup"]');
				if (fallback) {
					fallback.checked = true;
					fallback.dispatchEvent(new Event("change", { bubbles: true }));
				}
			}
		}
		cityInput.addEventListener("change", sync);
		sync();
	}

	// Settings > Payments can name a default pickup location: check it the
	// first time Store Pickup opens and never fight an explicit choice. An
	// empty data-default means nothing is pre-checked, so the server-side
	// "choose where you would like to pick up" validation still runs.
	function preselectPickupLocation(panel) {
		const radios = [...panel.querySelectorAll('input[name="pickup_location"]')];
		if (!radios.length || radios.some((radio) => radio.checked)) return;
		const wanted = (panel.getAttribute("data-default") || "").trim().toLowerCase();
		if (!wanted) return;
		const match = radios.find((radio) => (radio.value || "").trim().toLowerCase() === wanted);
		if (match) match.checked = true;
	}

	function syncPaymentUI() {
		const chosen = document.querySelector('input[name="payment_method"]:checked');
		const submit = document.querySelector('[data-shop="checkout-form"] [type="submit"]');
		if (submit && chosen)
			submit.textContent = chosen.value === "gateway" ? "Pay now" : "Place order";
		const note = document.querySelector('[data-shop="gateway-note"]');
		if (note) note.hidden = chosen?.value !== "gateway";
		const advNote = document.querySelector('[data-shop="advance-instructions"]');
		if (advNote) advNote.hidden = chosen?.value !== "advance";
		// Pickup: show the location picker and swap in the no-shipping totals.
		const pickup = chosen?.value === "pickup";
		const pickupPanel = document.querySelector('[data-shop="pickup-panel"]');
		if (pickupPanel) pickupPanel.style.display = pickup ? "flex" : "none";
		if (pickup && pickupPanel) preselectPickupLocation(pickupPanel);
		document
			.querySelectorAll('[data-shop="delivery-totals"], [data-shop="delivery-grand"]')
			.forEach((row) => {
				row.style.display = pickup ? "none" : "flex";
			});
		document
			.querySelectorAll('[data-shop="pickup-totals"], [data-shop="pickup-grand"]')
			.forEach((row) => {
				row.style.display = pickup ? "flex" : "none";
			});
	}

	function preselectPayment() {
		const radios = document.querySelectorAll(
			'[data-shop="checkout-form"] input[name="payment_method"]'
		);
		if (radios.length && ![...radios].some((radio) => radio.checked)) radios[0].checked = true;
	}

	async function submitReturn(form) {
		const data = new FormData(form);
		const submit = form.querySelector('[type="submit"]');
		if (submit) submit.disabled = true;
		try {
			await call("shop.storefront.returns.create_request", {
				order: window.location.pathname.split("/").filter(Boolean).pop(),
				token: new URLSearchParams(window.location.search).get("token") || undefined,
				item_code: data.get("item_code"),
				request_type: data.get("request_type"),
				reason: data.get("reason"),
			});
			window.location.reload();
		} catch (error) {
			showError(error.message);
			if (submit) submit.disabled = false;
		}
	}

	function initFilters() {
		const toggle = document.querySelector('[data-shop="filter-toggle"]');
		const panel = document.querySelector('[data-shop="filter-panel"]');
		if (!toggle || !panel) return;
		// applying a filter reloads the page, so the panel folds away on its own
		toggle.addEventListener("click", () => {
			const open = panel.dataset.open !== "true";
			panel.dataset.open = open ? "true" : "false";
			toggle.setAttribute("aria-expanded", open ? "true" : "false");
		});
	}

	function initBuyBar() {
		const bar = document.querySelector(".pdp-buybar");
		const anchor = document.querySelector('[data-shop="add-to-cart"]');
		if (!bar || !anchor || !("IntersectionObserver" in window)) return;
		new IntersectionObserver(
			(entries) => {
				bar.dataset.visible = entries[0].isIntersecting ? "false" : "true";
			},
			{ rootMargin: "-60px 0px 0px 0px" }
		).observe(anchor);
	}

	/* ── cascading searchable dropdown (replaces datalist) ────────────────── */
	function createShopSelect(input, items, opts) {
		if (!input || !items || !items.length) return { setValue() {}, setItems() {} };

		const wrapper = document.createElement("div");
		wrapper.style.cssText = "position:relative;display:inline-block;width:100%";
		input.parentNode.insertBefore(wrapper, input);
		wrapper.appendChild(input);

		// hide native autocomplete
		input.setAttribute("autocomplete", "off");
		input.setAttribute("spellcheck", "false");
		input.style.cssText += "box-sizing:border-box;width:100%";

		// dropdown panel
		const panel = document.createElement("div");
		panel.style.cssText =
			"display:none;position:absolute;top:100%;left:0;right:0;z-index:9999;" +
			"max-height:200px;overflow-y:auto;background:#fff;border:1px solid #e5e5e5;" +
			"border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,.08);margin-top:2px";
		wrapper.appendChild(panel);

		let currentItems = [...items];
		let highlighted = -1;

		function render(filter) {
			const q = (filter || "").toLowerCase();
			const matches = q
				? currentItems.filter((i) => i.toLowerCase().includes(q))
				: currentItems;
			panel.innerHTML = "";
			if (!matches.length) {
				panel.style.display = "none";
				return;
			}
			matches.forEach((item) => {
				const row = document.createElement("div");
				row.textContent = item;
				row.style.cssText =
					"padding:8px 12px;cursor:pointer;font-size:13px;color:#333;" +
					"transition:background .1s";
				row.addEventListener("mouseenter", () => {
					highlighted = [...panel.children].indexOf(row);
					highlightRow();
				});
				row.addEventListener("mousedown", (e) => {
					e.preventDefault();
					input.value = item;
					panel.style.display = "none";
					if (opts && opts.onChange) opts.onChange(item);
				});
				panel.appendChild(row);
			});
			panel.style.display = "block";
			highlighted = -1;
		}

		function highlightRow() {
			[...panel.children].forEach((r, i) => {
				r.style.background = i === highlighted ? "#f5f5f5" : "";
			});
		}

		input.addEventListener("focus", () => render(input.value));
		input.addEventListener("input", () => render(input.value));
		input.addEventListener("blur", () => {
			// delay so mousedown fires first
			setTimeout(() => {
				panel.style.display = "none";
				// enforce strict: if typed value not in list, revert
				const v = input.value.trim();
				if (v && !currentItems.some((i) => i.toLowerCase() === v.toLowerCase())) {
					input.value = "";
				}
			}, 200);
		});
		input.addEventListener("keydown", (e) => {
			const rows = panel.children;
			if (e.key === "ArrowDown") {
				e.preventDefault();
				highlighted = Math.min(highlighted + 1, rows.length - 1);
				highlightRow();
				if (rows[highlighted]) rows[highlighted].scrollIntoView({ block: "nearest" });
			} else if (e.key === "ArrowUp") {
				e.preventDefault();
				highlighted = Math.max(highlighted - 1, 0);
				highlightRow();
				if (rows[highlighted]) rows[highlighted].scrollIntoView({ block: "nearest" });
			} else if (e.key === "Enter") {
				e.preventDefault();
				if (highlighted >= 0 && rows[highlighted]) {
					input.value = rows[highlighted].textContent;
					panel.style.display = "none";
					if (opts && opts.onChange) opts.onChange(input.value);
				}
			} else if (e.key === "Escape") {
				panel.style.display = "none";
			}
		});

		return {
			setValue(v) {
				input.value = v || "";
			},
			setItems(newItems) {
				currentItems = [...newItems];
			},
		};
	}

	function initAddressDatalists() {
		const store = storeContext();
		const form = document.querySelector('[data-shop="checkout-form"]');
		if (!form) return;

		const provinceMap = store.province_city_map || {};
		const allProvinces = Object.keys(provinceMap);
		const allCities = store.address_cities || [];

		const stateInput = form.querySelector('[name="state"]');
		const cityInput = form.querySelector('[name="city"]');
		const countryInput = form.querySelector('[name="country"]');
		const homeCountry = store.address_country;

		// Country: locked to the store's single country. page_data exposes
		// address_country as the repeater's [{name}] rows, so unwrap the row,
		// and keep re-applying until the option exists — the repeater's
		// <option>s hydrate after this script runs, so a one-shot assignment
		// to the still-empty select is silently dropped.
		if (countryInput && homeCountry) {
			const home =
				typeof homeCountry === "string"
					? homeCountry
					: (homeCountry[0] && (homeCountry[0].name || homeCountry[0])) || "";
			countryInput.setAttribute("readonly", "readonly");
			let tries = 0;
			const lockCountry = () => {
				if (!home || countryInput.value) return;
				if (countryInput.tagName !== "SELECT") {
					countryInput.value = home;
					return;
				}
				const hasOption = Array.from(countryInput.options).some(
					(option) => option.value === home
				);
				if (hasOption) {
					countryInput.value = home;
					countryInput.dispatchEvent(new Event("change", { bubbles: true }));
					return;
				}
				if (tries++ < 50) setTimeout(lockCountry, 100);
			};
			lockCountry();
		}

		// Theme select blocks render their <option>s from a Builder repeater, which
		// cannot emit a static placeholder. Add one here so required selects (city)
		// start unselected and still show their field label, then skip the custom
		// panel wiring below — native selects manage their own dropdown.
		[stateInput, cityInput, countryInput].forEach((select) => {
			if (!select || select.tagName !== "SELECT") return;
			const previous = select.value;
			const first = select.options[0];
			if (!(first && !first.value && first.disabled)) {
				const placeholder = document.createElement("option");
				placeholder.value = "";
				placeholder.disabled = true;
				placeholder.textContent = select.getAttribute("aria-label") || "Select";
				select.insertBefore(placeholder, select.firstChild);
			}
			if (select.required) select.options[0].selected = true;
			else if (previous) select.value = previous;
		});
		// Native <select> pair (what the generated themes render): wire the
		// bidirectional cascade — picking a city selects its province, and
		// picking a province clears a city that is not one of its own.
		if (stateInput && stateInput.tagName === "SELECT") {
			if (cityInput && cityInput.tagName === "SELECT" && allProvinces.length) {
				const cityToProvince = {};
				Object.keys(provinceMap).forEach((prov) => {
					(provinceMap[prov] || []).forEach((city) => {
						cityToProvince[String(city).trim().toLowerCase()] = prov;
					});
				});
				const citiesFor = (prov) => {
					const key = Object.keys(provinceMap).find(
						(p) => p.toLowerCase() === String(prov || "").trim().toLowerCase()
					);
					return key ? provinceMap[key] : null;
				};
				cityInput.addEventListener("change", () => {
					const city = cityInput.value.trim();
					if (!city) return;
					const prov = cityToProvince[city.toLowerCase()];
					if (!prov) return;
					const option = Array.from(stateInput.options).find(
						(o) => o.value && o.value.toLowerCase() === prov.toLowerCase()
					);
					if (option && stateInput.value !== option.value) {
						stateInput.value = option.value;
						stateInput.dispatchEvent(new Event("change", { bubbles: true }));
					}
				});
				stateInput.addEventListener("change", () => {
					const city = cityInput.value.trim();
					if (!city) return;
					const cities = citiesFor(stateInput.value);
					if (!(cities || []).some((c) => String(c).trim().toLowerCase() === city.toLowerCase())) {
						cityInput.value = "";
					}
				});
			}
			return;
		}

		// Province: searchable dropdown from DB
		const provinceSel = createShopSelect(stateInput, allProvinces, {
			onChange(prov) {
				// cascade: when province changes, filter cities
				const cities = provinceMap[prov] || allCities;
				citySel.setItems(cities);
				// clear city if it's not in the new province
				if (cityInput.value && !cities.some((c) => c.toLowerCase() === cityInput.value.trim().toLowerCase())) {
					cityInput.value = "";
				}
			},
		});

		// City: initially shows all, then filtered by province
		const citySel = createShopSelect(cityInput, allCities, {
			onChange(city) {
				// reverse cascade: a city selects the province it belongs to
				const prov = Object.keys(provinceMap).find((p) =>
					(provinceMap[p] || []).some(
						(c) => String(c).trim().toLowerCase() === String(city).trim().toLowerCase()
					)
				);
				if (prov) provinceSel.setValue(prov);
			},
		});

		// Pre-fill from saved address if present
		if (stateInput.value.trim() && allProvinces.some((p) => p.toLowerCase() === stateInput.value.trim().toLowerCase())) {
			// trigger province cascade
			const match = allProvinces.find((p) => p.toLowerCase() === stateInput.value.trim().toLowerCase());
			if (match) provinceSel.setValue(match);
		}
	}

	function appleMapsDirectionsLinks() {
		// iPhone/iPad: hand "Get directions" links to Apple Maps instead of Google.
		const ua = navigator.userAgent;
		const isApple =
			/iPad|iPhone|iPod/.test(ua) ||
			(navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1); // iPadOS
		if (!isApple) return;
		document.querySelectorAll('a[href*="google.com/maps/dir/"]').forEach((link) => {
			const match = (link.getAttribute("href") || "").match(
				/destination=(-?\d+(?:\.\d+)?),(-?\d+(?:\.\d+)?)/
			);
			if (!match) return;
			link.setAttribute("href", `https://maps.apple.com/?daddr=${match[1]},${match[2]}`);
		});
	}

	// The theme's dataScript fills the directions hrefs after load, so the
	// swap is repeated (idempotently) whenever the DOM changes. The embedded
	// map stays view-only — no overlay, so panning/selecting on the map never
	// opens the maps app by accident.
	function refreshDirectionsLinks() {
		appleMapsDirectionsLinks();
	}

	// The pickup number button is device-aware. Phones keep the plain tel:
	// link; desktops have no dialer, so the click is intercepted and the
	// number is copied to the clipboard instead — with a brief "Copied ✓"
	// swap and a scale pop so the action always shows feedback. Detected per
	// click (hover+pointer media query), so hybrid/touch laptops behave too.
	function legacyCopyText(text) {
		const area = document.createElement("textarea");
		area.value = text;
		area.setAttribute("readonly", "");
		area.style.position = "fixed";
		area.style.opacity = "0";
		document.body.appendChild(area);
		area.select();
		let copied = false;
		try {
			copied = document.execCommand("copy");
		} catch (error) {
			copied = false;
		}
		area.remove();
		return copied;
	}

	function flashCopiedLink(link) {
		// Remember the real number once, swap the label, pop, then restore.
		if (!link.dataset.copyText) link.dataset.copyText = (link.textContent || "").trim();
		link.textContent = "Copied \u2713";
		if (typeof link.animate === "function") {
			link.animate(
				[
					{ transform: "scale(1)" },
					{ transform: "scale(1.07)" },
					{ transform: "scale(0.98)" },
					{ transform: "scale(1)" },
				],
				{ duration: 340, easing: "ease-out" },
			);
		}
		clearTimeout(link._copyTimer);
		link._copyTimer = setTimeout(() => {
			link.textContent = link.dataset.copyText || link.textContent;
			delete link.dataset.copyText;
		}, 1600);
	}

	function initPhoneCopy() {
		const isDesktop = () =>
			typeof window.matchMedia === "function" &&
			window.matchMedia("(hover: hover) and (pointer: fine)").matches;
		if (isDesktop()) {
			document.querySelectorAll('[data-shop="phone-copy"]').forEach((link) => {
				link.title = "Click to copy the number";
			});
		}
		// Delegated: the theme may re-render the pickup panel at any time.
		document.addEventListener("click", (event) => {
			const link =
				event.target instanceof Element
					? event.target.closest('[data-shop="phone-copy"]')
					: null;
			if (!link || !isDesktop()) return;
			event.preventDefault(); // desktop must never navigate to tel:
			if (!link.title) link.title = "Click to copy the number";
			const href = link.getAttribute("href") || "";
			const number = href.replace(/^tel:/i, "").trim() || (link.textContent || "").trim();
			if (!number) return;
			const copied =
				typeof navigator.clipboard === "function" && navigator.clipboard.writeText
					? navigator.clipboard.writeText(number).then(() => true).catch(() => legacyCopyText(number))
					: legacyCopyText(number);
			Promise.resolve(copied).then((ok) => {
				if (ok) flashCopiedLink(link);
			});
		});
	}

	// Raast confirmation: the QR is only scannable from a different device, so
	// everything a customer on the paying phone needs has to work without
	// scanning — copy the raw IBAN, copy a paste-ready block of account,
	// amount and order number, and download the image itself. Both handlers
	// are delegated so a re-rendered confirmation panel keeps working.
	function initRaastActions() {
		const writeClipboard = (text) =>
			typeof navigator.clipboard === "function" && navigator.clipboard.writeText
				? navigator.clipboard.writeText(text).then(() => true).catch(() => legacyCopyText(text))
				: legacyCopyText(text);

		document.addEventListener("click", (event) => {
			const target = event.target instanceof Element ? event.target : null;
			if (!target) return;

			const copier = target.closest('[data-shop="raast-copy"]');
			if (copier) {
				const text = copier.getAttribute("data-copy") || "";
				if (!text) return;
				event.preventDefault();
				Promise.resolve(writeClipboard(text)).then((ok) => {
					if (ok) flashCopiedLink(copier);
				});
				return;
			}

			const link = target.closest('[data-shop="raast-download"]');
			if (!link) return;
			// Second pass after a failed Blob attempt: leave the click alone so
			// the anchor's own download handling runs instead of looping.
			if (link.dataset.nativeDownload === "1") return;
			const href = link.getAttribute("href") || "";
			if (!/^data:image\//i.test(href)) return;
			event.preventDefault();

			const filename = link.getAttribute("download") || "raast-qr.png";
			const nativeDownload = () => {
				// Rarer than it looks: data URLs are same-origin, but if the
				// conversion fails the plain anchor still saves the file rather
				// than the button silently doing nothing.
				link.dataset.nativeDownload = "1";
				link.click();
			};
			if (typeof fetch !== "function") {
				nativeDownload();
				return;
			}
			fetch(href)
				.then((response) => (response.ok ? response.blob() : Promise.reject(new Error("no blob"))))
				.then((blob) => {
					const url = URL.createObjectURL(blob);
					const anchor = document.createElement("a");
					anchor.href = url;
					anchor.download = filename;
					document.body.appendChild(anchor);
					anchor.click();
					anchor.remove();
					setTimeout(() => URL.revokeObjectURL(url), 4000);
				})
				.catch(nativeDownload);
		});
	}

	// The map embed is view-only (pointer-events: none), so zooming is ours:
	// rewrite the embed URL symmetrically around the pin — OSM's bbox rescaled
	// about the marker, Google's z stepped with q untouched — which keeps the
	// location exactly centred at every zoom level.
	function zoomMapFrame(frame, direction) {
		let url;
		try {
			url = new URL(frame.getAttribute("src") || "", window.location.href);
		} catch (error) {
			return;
		}
		if (url.hostname.endsWith("openstreetmap.org")) {
			const bbox = (url.searchParams.get("bbox") || "").split(",").map(Number);
			if (bbox.length !== 4 || bbox.some((value) => Number.isNaN(value))) return;
			const marker = (url.searchParams.get("marker") || "").split(",").map(Number);
			const hasMarker = marker.length === 2 && marker.every((value) => !Number.isNaN(value));
			const centerLat = hasMarker ? marker[0] : (bbox[1] + bbox[3]) / 2;
			const centerLng = hasMarker ? marker[1] : (bbox[0] + bbox[2]) / 2;
			// Symmetric half-extents around the pin, scaled 0.5 in / 2 out,
			// clamped so the box never leaves the world or collapses to zero.
			let halfW = ((bbox[2] - bbox[0]) / 2) * (direction > 0 ? 0.5 : 2);
			let halfH = ((bbox[3] - bbox[1]) / 2) * (direction > 0 ? 0.5 : 2);
			halfW = Math.min(Math.max(halfW, 1e-7), Math.max(1e-7, 180 - Math.abs(centerLng)));
			halfH = Math.min(Math.max(halfH, 1e-7), Math.max(1e-7, 90 - Math.abs(centerLat)));
			url.searchParams.set(
				"bbox",
				[centerLng - halfW, centerLat - halfH, centerLng + halfW, centerLat + halfH].join(","),
			);
			// The marker param stays untouched — it is the rebuilt box's centre.
		} else if (/(^|\.)google\./.test(url.hostname)) {
			let zoom = parseInt(url.searchParams.get("z") || "16", 10);
			if (Number.isNaN(zoom)) zoom = 16;
			url.searchParams.set("z", String(Math.min(20, Math.max(1, zoom + (direction > 0 ? 1 : -1)))));
			// The q param stays untouched — Google re-centres every zoom on it.
		} else {
			return;
		}
		frame.setAttribute("src", url.toString());
	}

	function initMapZoom() {
		// Delegated: the theme may re-render the pickup panel at any time.
		document.addEventListener("click", (event) => {
			const button =
				event.target instanceof Element
					? event.target.closest('[data-shop="map-zoom"]')
					: null;
			if (!button) return;
			const direction = Number(button.getAttribute("data-delta")) || 0;
			if (!direction) return;
			const wrapper = button.closest('[data-shop="map-frame"]');
			const frame = wrapper && wrapper.querySelector("iframe");
			if (!frame) return;
			event.preventDefault(); // type=button never submits, this just guards default.
			zoomMapFrame(frame, direction);
		});
	}

	document.addEventListener("DOMContentLoaded", () => {
		initGallery();
		initVariantPicker();
		refreshCartCount();
		initReviewForm();
		preselectPayment();
		syncPaymentUI();
		initMapZoom();
		initPhoneCopy();
		initRaastActions();
		initBuyBar();
		initFilters();
		initAddressDatalists();
		document
			.querySelectorAll('[data-shop="checkout-form"] input[name="payment_method"]')
			.forEach((radio) => radio.addEventListener("change", syncPaymentUI));
		const picker = document.querySelector('[data-shop="address-picker"]');
		if (picker)
			picker.addEventListener("change", () => {
				applySavedAddress(picker);
				// Re-run dependent checks (city cascade, COD availability).
				const city = document.querySelector('[data-shop="checkout-form"] [name="city"]');
				if (city) city.dispatchEvent(new Event("change", { bubbles: true }));
			});
		initCodRestriction();
		refreshDirectionsLinks();
		let mapRefreshQueued = false;
		new MutationObserver(() => {
			if (mapRefreshQueued) return;
			mapRefreshQueued = true;
			setTimeout(() => {
				mapRefreshQueued = false;
				refreshDirectionsLinks();
			}, 50);
		}).observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ["href"] });

		// Preload CreepJS fingerprint on checkout page (runs in background, cached in localStorage)
		const store = storeContext();
		if (store.fingerprint_provider === "creepjs") {
			loadFingerprint(); // kicks off iframe + caches result
		}
	});
})();
