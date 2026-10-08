(function () {
	const state = {
		product: window.page_data && window.page_data.product,
		selection: {},
		cart: (window.page_data && window.page_data.cart) || null,
	};

	// Device fingerprint — supports three providers:
	//   thumbmarkjs      – free, no API key, self-hosted via CDN
	//   fingerprintjs-oss – free, no API key, self-hosted via CDN
	//   creepjs           – free, self-hosted via CDN, most signals
	//
	// fingerprintjs-pro used to be a fourth option. It needed the paid API to be
	// reachable over the network, and this bench no longer talks to that host, so
	// the branch was removed rather than left to fail on every page load.
	// Checkout whitelists store fields flat on page_data; other pages nest
	// them under store. Fall back so both shapes resolve.
	function storeContext() {
		const data = window.page_data || {};
		return data.store || data;
	}
	function loadFingerprint() {
		const store = storeContext();
		let provider = store.fingerprint_provider || "thumbmarkjs";

		// Loud, because the alternative is invisible. A provider that never
		// reaches the page falls back to thumbmarkjs here, and every order then
		// records "thumbmarkjs" -- which reads as a setting that was applied and
		// silently was not. It was: Builder rebuilds page_data from a fixed key
		// list, so a value nested under `store` or missing from that list is
		// dropped before this code runs, with nothing in any log.
		if (!store.fingerprint_provider) {
			console.warn(
				"[shop] Shop Settings.fingerprint_provider did not reach this page " +
					"(page_data.store and page_data.fingerprint_provider are both absent). " +
					`Falling back to "${provider}". Check the page's page_data_script allowlist.`
			);
		}

		if (provider === "fingerprintjs-pro") {
			// Loud on purpose. Shop Settings still offers this option, so a value
			// set before the branch was removed would otherwise fall through to
			// thumbmarkjs and every order would record "thumbmarkjs" - reading as
			// a setting that was applied and silently was not.
			console.warn(
				'[shop] Shop Settings.fingerprint_provider is "fingerprintjs-pro", ' +
					"which is no longer supported. Falling back to thumbmarkjs. " +
					"Change the setting in Shop Settings."
			);
			provider = "thumbmarkjs";
		}

		if (provider === "fingerprintjs-oss") {
			// dist/fp.esm.js, not dist/fingerprintjs.min.js. The filename the old
			// URL named does not exist in the package -- it 404s, so this branch never
			// ran and the .catch below quietly returned an empty visitorId, which is
			// indistinguishable at checkout from "the customer has no fingerprint".
			//
			// It also has to be the ESM build specifically. dist/fp.min.js is a plain
			// script that assigns a global; import() of it yields a module with no
			// exports at all, so .load would be undefined. fp.esm.js is the only one of
			// the dist files that is a real module.
			return import("https://cdn.jsdelivr.net/npm/@fingerprintjs/fingerprintjs/dist/fp.esm.js")
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

	// --- Image preview -------------------------------------------------------
	//
	// Clicking a product photo opens it fullscreen. Zoom comes from two places
	// because neither input works everywhere: a slider is precise but fiddly with
	// a thumb, and a pinch is the gesture a phone already uses for exactly this
	// but does not exist on a desktop trackpad-less mouse. The slider is offered
	// on the phone as well and steps aside while two fingers are down, since the
	// bar sits under the fingers doing the pinching.
	//
	// Pan is not in the brief but is what makes zoom usable: at 3x most of the
	// photo is off screen, so without a drag there is no way to look at any of it.
	const ZOOM_MIN = 1;
	const ZOOM_MAX = 5;

	const preview = {
		scale: ZOOM_MIN,
		x: 0,
		y: 0,
		pointers: new Map(),
		// Captured when the second finger lands; the zoom is then derived
		// absolutely from these two rather than accumulated across moves.
		pinchStartDistance: 0,
		pinchStartScale: ZOOM_MIN,
		pan: null,
	};

	function previewRoot() {
		return document.querySelector('[data-shop="lightbox"]');
	}

	function previewStage() {
		const root = previewRoot();
		return root ? root.querySelector(".lightbox-stage") : null;
	}

	function previewImage() {
		const root = previewRoot();
		return root ? root.querySelector('[data-shop="lightbox-image"]') : null;
	}

	function openPreview(src, alt) {
		const root = previewRoot();
		const image = previewImage();
		// The placeholder src Builder leaves on an unbound img is not a photo, so
		// opening on it would flash a broken image at the customer.
		if (!root || !image || !src || src.indexOf("/assets/builder/") === 0) return;
		image.setAttribute("src", src);
		image.setAttribute("alt", alt || "");
		resetPreview();
		root.dataset.open = "true";
		document.documentElement.style.overflow = "hidden";
	}

	function closePreview() {
		const root = previewRoot();
		if (!root || root.dataset.open !== "true") return;
		root.dataset.open = "false";
		root.dataset.pinching = "false";
		document.documentElement.style.overflow = "";
		resetPreview();
		const image = previewImage();
		if (image) image.removeAttribute("src");
	}

	/** Back to 1x, centred, with no gesture state left over from last time. */
	function resetPreview() {
		preview.scale = ZOOM_MIN;
		preview.x = 0;
		preview.y = 0;
		preview.pointers.clear();
		preview.pinchStartDistance = 0;
		preview.pinchStartScale = ZOOM_MIN;
		preview.pan = null;
		const stage = previewStage();
		if (stage) stage.dataset.panning = "false";
		renderPreview();
	}

	function renderPreview() {
		const image = previewImage();
		if (image) {
			image.style.transform =
				"translate(" + preview.x + "px, " + preview.y + "px) scale(" + preview.scale + ")";
		}
		const root = previewRoot();
		if (!root) return;
		const slider = root.querySelector('[data-shop="lightbox-zoom"]');
		// Written on every gesture frame, not just when the slider moves, so the
		// thumb follows a pinch instead of jumping to wherever it was left.
		if (slider && document.activeElement !== slider) slider.value = String(preview.scale);
		const level = root.querySelector('[data-shop="lightbox-level"]');
		if (level) level.textContent = Math.round(preview.scale * 100) + "%";
	}

	/**
	 * Keep the photo covering the stage, never sliding off to leave bare backdrop.
	 *
	 * The rect of a transformed element is its *transformed* box, so reading it
	 * back gives the on-screen size without recomputing the scale by hand. When
	 * the scaled photo is narrower than the stage on an axis, the offset is pinned
	 * to zero on that axis so it stays centred instead of drifting.
	 */
	function clampPreviewPan() {
		const stage = previewStage();
		const image = previewImage();
		if (!stage || !image) return;
		const box = stage.getBoundingClientRect();
		const shot = image.getBoundingClientRect();
		if (!box.width || !box.height || !shot.width || !shot.height) return;
		const limitX = shot.width >= box.width ? (shot.width - box.width) / 2 : 0;
		const limitY = shot.height >= box.height ? (shot.height - box.height) / 2 : 0;
		preview.x = Math.min(limitX, Math.max(-limitX, preview.x));
		preview.y = Math.min(limitY, Math.max(-limitY, preview.y));
	}

	/**
	 * @param {number} next     scale to move to
	 * @param {?{x: number, y: number}} focus  stage-relative point to hold still,
	 *   or null to leave the current pan alone (what the slider does).
	 *
	 * The offset maths: a stage point `a` sits over the image point
	 * (a - t) / s. Holding that same image point under `a` after the scale changes
	 * to s1 means t1 = a - s1 * (a - t0) / s0, which rearranges to a shift of
	 * (a - t0) * (1 - s1 / s0). That is what keeps a pinch anchored between the
	 * fingers rather than sliding the photo out from under them.
	 */
	function applyPreviewZoom(next, focus) {
		const previous = preview.scale;
		preview.scale = Math.min(ZOOM_MAX, Math.max(ZOOM_MIN, next));
		if (focus && previous > 0 && preview.scale !== previous) {
			const ratio = 1 - preview.scale / previous;
			preview.x += (focus.x - preview.x) * ratio;
			preview.y += (focus.y - preview.y) * ratio;
		}
		clampPreviewPan();
		renderPreview();
	}

	/** Midpoint of the two live pointers, relative to the stage's centre. */
	function pinchFocus() {
		const stage = previewStage();
		if (!stage || preview.pointers.size < 2) return null;
		const points = Array.from(preview.pointers.values());
		const box = stage.getBoundingClientRect();
		return {
			x: (points[0].x + points[1].x) / 2 - (box.left + box.width / 2),
			y: (points[0].y + points[1].y) / 2 - (box.top + box.height / 2),
		};
	}

	function pinchSpread() {
		const points = Array.from(preview.pointers.values());
		if (points.length < 2) return 0;
		return Math.hypot(points[1].x - points[0].x, points[1].y - points[0].y);
	}

	function onPreviewPointerDown(event) {
		const stage = previewStage();
		if (!stage) return;
		// Capture on the stage so a finger that slides off the photo still
		// reports its moves; without it the gesture dies the moment it leaves.
		if (stage.setPointerCapture) {
			try {
				stage.setPointerCapture(event.pointerId);
			} catch (error) {
				/* capture is best-effort */
			}
		}
		preview.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
		if (preview.pointers.size >= 2) {
			preview.pinchStartDistance = pinchSpread();
			preview.pinchStartScale = preview.scale;
			preview.pan = null;
			stage.dataset.panning = "false";
			const root = previewRoot();
			if (root) root.dataset.pinching = "true";
			return;
		}
		preview.pan = {
			x: event.clientX,
			y: event.clientY,
			originX: preview.x,
			originY: preview.y,
		};
		stage.dataset.panning = "true";
	}

	function onPreviewPointerMove(event) {
		if (!preview.pointers.has(event.pointerId)) return;
		preview.pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });

		if (preview.pointers.size >= 2) {
			const spread = pinchSpread();
			if (preview.pinchStartDistance > 0 && spread > 0) {
				// Absolute, from the distance and scale the pinch began at - not
				// scale *= (spread / startDistance), which reapplies the ratio
				// measured at the start to the running scale on every single move.
				// That compounds: fingers opening from 80px to 160px, a true 2x,
				// landed at 4.2x and hit the 5x ceiling almost immediately, which
				// is what made the zoom feel like it was racing away.
				applyPreviewZoom(
					preview.pinchStartScale * (spread / preview.pinchStartDistance),
					pinchFocus()
				);
			}
			return;
		}
		if (!preview.pan) return;
		preview.x = preview.pan.originX + (event.clientX - preview.pan.x);
		preview.y = preview.pan.originY + (event.clientY - preview.pan.y);
		clampPreviewPan();
		renderPreview();
	}

	function onPreviewPointerUp(event) {
		const stage = previewStage();
		preview.pointers.delete(event.pointerId);
		if (stage && stage.releasePointerCapture) {
			try {
				stage.releasePointerCapture(event.pointerId);
			} catch (error) {
				/* already released */
			}
		}
		if (preview.pointers.size < 2) {
			preview.pinchStartDistance = 0;
			const root = previewRoot();
			if (root) root.dataset.pinching = "false";
		}
		if (preview.pointers.size === 1) {
			// One finger came up mid-pinch. Re-anchor the drag to the finger that
			// stayed down, or the photo jumps by the difference on the next move.
			const remaining = Array.from(preview.pointers.entries())[0];
			preview.pan = {
				x: remaining[1].x,
				y: remaining[1].y,
				originX: preview.x,
				originY: preview.y,
			};
		} else if (preview.pointers.size === 0) {
			preview.pan = null;
			if (stage) stage.dataset.panning = "false";
		}
	}

	function initPreview() {
		const root = previewRoot();
		if (!root) return;
		const stage = previewStage();
		if (stage) {
			stage.addEventListener("pointerdown", onPreviewPointerDown);
			stage.addEventListener("pointermove", onPreviewPointerMove);
			stage.addEventListener("pointerup", onPreviewPointerUp);
			stage.addEventListener("pointercancel", onPreviewPointerUp);
			stage.addEventListener("dragstart", (event) => event.preventDefault());
		}
		const slider = root.querySelector('[data-shop="lightbox-zoom"]');
		if (slider) {
			slider.addEventListener("input", () => {
				applyPreviewZoom(parseFloat(slider.value) || ZOOM_MIN, null);
			});
		}
	}

	function initVariantPicker() {
		const product = state.product;
		if (!product) return;
		if (!product.has_variants) {
			// Stock state has to be applied here too, not only for variant
			// products. This used to return immediately for anything without
			// variants, so the one and only thing that ever disabled Add to cart
			// or relabelled it "Out of stock" was the variant picker - and the
			// majority of products have no variants. A product with actual_qty 0
			// kept a live, clickable Add to cart button, because nothing in the
			// non-variant path ever consulted product.in_stock.
			applyStockToButtons(product.in_stock);
			return;
		}
		const defaultVariant = product.variants.find(
			(variant) => variant.item_code === product.default_item_code
		);
		if (defaultVariant) state.selection = Object.assign({}, defaultVariant.attributes);
		syncVariantUI();
	}

	function applyStockToButtons(inStock) {
		document.querySelectorAll('[data-shop="add-to-cart"], [data-shop="buy-now"]').forEach((button) => {
			button.disabled = !inStock;
			if (!inStock) {
				button.textContent = button.dataset.outOfStockLabel || "Out of stock";
			} else if (button.dataset.label) {
				button.textContent = button.dataset.label;
			}
		});
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
		});
		applyStockToButtons(variant.in_stock);
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
		else if (action === "thumb") {
			// A thumbnail promotes its photo and nothing else. It used to also open
			// the fullscreen preview, which made the obvious next step - "let me see
			// the other one full size" - arrive unasked, and left the row unable to
			// be used for what it is plainly for: flicking between photos. The big
			// picture is the control that opens the preview.
			showImage(target.dataset.image);
		}
		else if (action === "main-image") {
			openPreview(target.getAttribute("src"), target.getAttribute("alt"));
		}
		else if (action === "lightbox-close" || action === "lightbox-backdrop") closePreview();
		else if (action === "rating-star") selectRating(parseInt(target.dataset.value, 10));
		else if (action === "variant-option") selectOption(target);
		else if (action === "qty-inc") setQty(target.dataset.itemCode, rowQty(target.dataset.itemCode) + 1);
		else if (action === "qty-dec") setQty(target.dataset.itemCode, rowQty(target.dataset.itemCode) - 1);
		else if (action === "remove") setQty(target.dataset.itemCode, 0);
	});

	document.addEventListener("keydown", (event) => {
		// The preview is the topmost layer, so Escape closes it first and leaves
		// the drawer alone; otherwise Escape on a zoomed photo would also empty a
		// cart the customer never touched.
		if (event.key !== "Escape") return;
		const root = previewRoot();
		if (root && root.dataset.open === "true") closePreview();
		else closeDrawer();
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
		// Raast's note says the QR arrives with the order, so it belongs to
		// the moment the method is picked, not to the summary below it.
		const raastNote = document.querySelector('[data-shop="raast-instructions"]');
		if (raastNote) raastNote.hidden = chosen?.value !== "raast";
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
		// page_data hands address_cities over as repeater rows ([{name}]), but
		// province_city_map's values are already plain strings. Compare and
		// render one shape, or every lookup here silently misses.
		const allCities = (store.address_cities || [])
			.map((row) => (row && typeof row === "object" ? row.name || "" : row))
			.filter(Boolean);

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
		// bidirectional cascade — picking a province narrows the city list to
		// that province's cities, and picking a city selects its province.
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

				// Rebuild the city's <option>s in place. Replacing the <select>
				// itself would drop the name, id, required and aria-label the form
				// reads on submit, so the options are swapped instead. The disabled
				// empty placeholder added above is kept so the label still shows
				// while nothing is chosen.
				const setCityOptions = (cities) => {
					const first = cityInput.options[0];
					const placeholder =
						first && !first.value && first.disabled ? first : null;
					const previous = cityInput.value;
					while (cityInput.options.length) cityInput.remove(0);
					if (placeholder) cityInput.appendChild(placeholder);
					cities.forEach((city) => {
						const option = document.createElement("option");
						option.value = city;
						option.textContent = city;
						cityInput.appendChild(option);
					});
					// Keep the chosen city when the new province still has it,
					// otherwise leave the select on the placeholder rather than
					// showing a value that is no longer in the list.
					const kept = cities.some(
						(c) => String(c).trim().toLowerCase() === previous.trim().toLowerCase()
					);
					cityInput.value = kept ? previous : "";
					return kept;
				};

				// With no province chosen the full list stands: narrowing to
				// nothing would make the city unselectable.
				if (!stateInput.value.trim()) setCityOptions(allCities);

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
					const chosen = stateInput.value.trim();
					setCityOptions(chosen ? citiesFor(chosen) || [] : allCities);
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

	// The hero's coverflow of products. Structure and behaviour from a CodePen
	// (codepen.io/frise/pen/mZvKpe): the cards are placed by a data-pos of -2..2
	// and moving one only rewrites those attributes. What differs is that these
	// cards are links to their products, so a click cannot mean both "come
	// forward" and "open": a card at the side comes forward, and only the card
	// already in the centre opens. Two taps to reach a product, one to browse.
	function initHeroCarousel() {
		const list = document.querySelector(".carousel__list");
		if (!list) return;
		const cards = Array.from(list.children);
		if (cards.length < 2) return;

		// Start in the middle, so the first thing shown is a product rather than
		// the end of a row. With one card there is nothing to choose.
		let active = Math.floor((cards.length - 1) / 2);

		const SLOTS = 2; // How far either side the pen shows: -2..2.

		function place() {
			const count = cards.length;
			cards.forEach((card, index) => {
				// The distance from the centre, the short way round. Taking it
				// straight off the index difference sends the carousel walking
				// instead of cycling: with three cards, centring the last one puts
				// the others at -1 and -2, and they slide out of sight rather than
				// coming back round.
				let offset = (index - active + count) % count;
				if (offset > count / 2) offset -= count;
				// Further out than the pen's slots: parked, not dropped, so a shop
				// with more products in stock can still reach all of them.
				if (offset > SLOTS) offset = SLOTS + 1;
				if (offset < -SLOTS) offset = -SLOTS - 1;
				card.dataset.pos = String(offset);
			});
			list.dataset.ready = "true";
		}

		function moveTo(index) {
			if (index === active || index < 0 || index >= cards.length) return;
			active = index;
			place();
			schedule();
			// If the keyboard is in the carousel, take it to the card that just came
			// forward. Otherwise focus stays on a card that is no longer the one
			// being read, and the next Tab lands somewhere unrelated.
			if (list.contains(document.activeElement)) cards[active].focus();
			// The cards animate for 300ms. A click landing inside that window
			// would go to whichever card happens to be sliding under the finger,
			// so the list stops taking clicks until they have settled.
			list.dataset.moving = "true";
			clearTimeout(moveTo.timer);
			moveTo.timer = setTimeout(() => {
				list.dataset.moving = "false";
			}, 320);
		}

		list.addEventListener("click", (event) => {
			if (list.dataset.moving === "true") {
				event.preventDefault();
				return;
			}
			const card = event.target.closest("a");
			if (!card || !list.contains(card)) return;
			if (Number(card.dataset.pos) === 0) return; // the centre card opens
			event.preventDefault();
			moveTo(cards.indexOf(card));
		});

		// On the list, not the document: the cards are links, so the keyboard
		// arrives here by bubbling from whichever card is focused. A carousel-wide
		// handler would steal the arrow keys from every filter and field on the
		// page.
		list.addEventListener("keydown", (event) => {
			if (event.key !== "ArrowLeft" && event.key !== "ArrowRight") return;
			event.preventDefault();
			moveTo(active + (event.key === "ArrowRight" ? 1 : -1));
		});

		// It turns itself over every few seconds, which is a change the
		// shopper did not ask for, so it stands down whenever they are actually
		// using it: while a pointer is resting on the box, while the keyboard is
		// in it, and while the tab is in the background. Interacting also
		// restarts the countdown, so a card never moves away from someone who has
		// just clicked it.
		const ROTATE_MS = 4000;
		let timer = null;
		function schedule() {
			clearTimeout(timer);
			timer = setTimeout(turn, ROTATE_MS);
		}
		function turn() {
			const busy =
				document.hidden || list.matches(":hover") || list.contains(document.activeElement);
			if (!busy) moveTo((active + 1) % cards.length);
			else schedule();
		}

		place();
		schedule();
	}

	document.addEventListener("DOMContentLoaded", () => {
		initGallery();
		initHeroCarousel();
		initPreview();
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
