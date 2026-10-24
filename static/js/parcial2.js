/**
 * Lúmen storefront front-end.
 *
 * Vanilla JS (no framework, no build step) consuming the Flask JSON API:
 *   - GET  /api/products   catalog with server-side filters
 *   - GET  /api/categories category slugs + labels
 *   - POST /api/checkout   order creation
 *
 * The server owns the stock: the client only mirrors it to render
 * "en stock" / "Sin stock" labels and to block adding more units than
 * the server has available.
 */
(function () {
  'use strict';

  /** localStorage key holding the shopping cart. */
  var CART_STORAGE_KEY = 'parcial2_cart';
  /** Fixed IVA rate (same value the server applies). */
  var TAX_RATE = 0.21;
  /** Debounce applied to the free-text search field. */
  var SEARCH_DEBOUNCE_MS = 250;
  /** Placeholder used when a product image fails to load. */
  var PLACEHOLDER_IMAGE = 'https://placehold.co/500x350/e2e8f0/1e293b?text=';
  /** Endpoint paths. */
  var API_PRODUCTS = '/api/products';
  var API_CATEGORIES = '/api/categories';
  var API_CHECKOUT = '/api/checkout';

  /** Application state. */
  var state = {
    /** @type {Array<{product_id:number,title:string,price:number,image:string,quantity:number}>} */
    cart: [],
    /** Products of the last applied filter, used to render the grid. */
    catalog: [],
    /** Every product seen so far, keyed by id. */
    productById: new Map(),
    /** Server stock per product id. */
    stockById: new Map(),
    /** Active filters, always sent to the server. */
    filters: { q: '', category: 'all', minPrice: '', maxPrice: '' },
    /** Incremented on every catalog request to discard stale responses. */
    requestId: 0,
    /** Timer handle of the pending search debounce. */
    searchTimer: null,
    /** 'confirm' or 'success'. */
    checkoutState: 'confirm'
  };

  /** Cached DOM references. */
  var dom = {};

  // ---------------------------------------------------------------------
  // Helpers
  // ---------------------------------------------------------------------

  function byId(id) {
    return document.getElementById(id);
  }

  /**
   * Create an element, optionally with a class name and a text node.
   *
   * @param {string} tag
   * @param {string=} className
   * @param {string=} text
   * @returns {HTMLElement}
   */
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text !== undefined && text !== null) {
      node.textContent = text;
    }
    return node;
  }

  /**
   * Format a monetary amount the way the original page did.
   *
   * @param {number} value
   * @returns {string}
   */
  function money(value) {
    return '$' + Number(value || 0).toFixed(2);
  }

  /**
   * Build the query string for /api/products from the active filters.
   *
   * @returns {URLSearchParams}
   */
  function buildQuery() {
    var params = new URLSearchParams();
    var filters = state.filters;

    if (filters.q) {
      params.set('q', filters.q);
    }
    if (filters.category && filters.category !== 'all') {
      params.set('category', filters.category);
    }
    if (filters.minPrice !== '') {
      params.set('min_price', filters.minPrice);
    }
    if (filters.maxPrice !== '') {
      params.set('max_price', filters.maxPrice);
    }

    return params;
  }

  /**
   * Perform a JSON request.
   *
   * @param {string} url
   * @param {RequestInit=} options
   * @returns {Promise<{ok:boolean,status:number,payload:object}>}
   */
  function requestJson(url, options) {
    return fetch(url, options)
      .then(function (response) {
        return response
          .json()
          .catch(function () {
            return {};
          })
          .then(function (payload) {
            return { ok: response.ok, status: response.status, payload: payload || {} };
          });
      })
      .catch(function () {
        // Network level failure: reported as an unsuccessful request.
        return { ok: false, status: 0, payload: {} };
      });
  }

  /**
   * Return the server stock of a product.
   *
   * @param {number} productId
   * @returns {number}
   */
  function stockFor(productId) {
    var stock = state.stockById.get(productId);
    return typeof stock === 'number' ? stock : 0;
  }

  /**
   * Return the quantity of a product already in the cart.
   *
   * @param {number} productId
   * @returns {number}
   */
  function cartQty(productId) {
    var found = 0;
    state.cart.forEach(function (item) {
      if (item.product_id === productId) {
        found += item.quantity;
      }
    });
    return found;
  }

  /**
   * Register the products of a server response in the local indexes.
   *
   * @param {Array<object>} products
   */
  function indexProducts(products) {
    products.forEach(function (product) {
      state.productById.set(product.id, product);
      state.stockById.set(product.id, product.stock);
    });
  }

  // ---------------------------------------------------------------------
  // Catalog
  // ---------------------------------------------------------------------

  /**
   * Fetch the catalog with the active filters and render the grid.
   *
   * @returns {Promise<void>}
   */
  function loadCatalog() {
    var requestId = ++state.requestId;
    var query = buildQuery().toString();
    var url = API_PRODUCTS + (query ? '?' + query : '');

    return requestJson(url).then(function (result) {
      // A newer request already started: drop this (stale) response.
      if (requestId !== state.requestId) {
        return;
      }
      if (!result.ok) {
        return;
      }
      var products = result.payload.products || [];
      state.catalog = products;
      indexProducts(products);
      renderGrid();
    });
  }

  /**
   * Refresh the stock index with the full catalog, keeping the visible
   * filter untouched.
   *
   * @returns {Promise<void>}
   */
  function loadStockIndex() {
    return requestJson(API_PRODUCTS).then(function (result) {
      if (!result.ok) {
        return;
      }
      indexProducts(result.payload.products || []);
      renderGrid();
    });
  }

  /**
   * Populate the category filter with the categories served by the API.
   *
   * @returns {Promise<void>}
   */
  function loadCategories() {
    return requestJson(API_CATEGORIES).then(function (result) {
      if (!result.ok) {
        return;
      }
      var select = dom.categoryFilter;
      var current = select.value;
      var categories = result.payload.categories || [];

      select.querySelectorAll('option[data-api="true"]').forEach(function (option) {
        option.remove();
      });

      categories.forEach(function (category) {
        var option = document.createElement('option');
        option.value = category.value;
        option.textContent = category.label;
        option.setAttribute('data-api', 'true');
        select.appendChild(option);
      });

      select.value = current;
    });
  }

  /**
   * Render the product grid from the last catalog response.
   */
  function renderGrid() {
    var grid = dom.productsGrid;
    var emptyState = dom.noProducts;

    grid.innerHTML = '';

    if (!state.catalog.length) {
      emptyState.classList.remove('d-none');
      return;
    }

    emptyState.classList.add('d-none');
    state.catalog.forEach(function (product) {
      grid.appendChild(buildProductCard(product));
    });
  }

  /**
   * Build a single product card, mirroring the original markup.
   *
   * @param {object} product
   * @returns {HTMLElement}
   */
  function buildProductCard(product) {
    var inCart = cartQty(product.id);
    var stockLeft = stockFor(product.id) - inCart;
    var isOutOfStock = stockLeft <= 0;

    var column = el('div', 'col-12 col-sm-6 col-lg-4 col-xl-3');
    var card = el('div', 'product-card');

    var imageContainer = el('div', 'product-img-container');
    imageContainer.appendChild(el('span', 'badge-category', product.category_label));

    var image = document.createElement('img');
    image.src = product.image;
    image.alt = product.title;
    image.addEventListener('error', function () {
      image.src = PLACEHOLDER_IMAGE + encodeURIComponent(product.title);
    });
    imageContainer.appendChild(image);

    if (isOutOfStock) {
      var overlay = el(
        'div',
        'position-absolute top-0 start-0 w-100 h-100 d-flex align-items-center justify-content-center'
      );
      overlay.style.background = 'rgba(0,0,0,0.4)';
      overlay.style.borderRadius = '16px';
      overlay.appendChild(el('span', 'badge bg-danger fs-6', 'Agotado'));
      imageContainer.appendChild(overlay);
    }

    var body = el('div', 'p-3 d-flex flex-column flex-grow-1');
    body.appendChild(el('h5', 'fw-bold text-dark fs-6 mb-2 line-clamp-2', product.title));
    body.appendChild(el('p', 'text-muted small mb-3 flex-grow-1', product.description));

    var footer = el('div', 'd-flex align-items-center justify-content-between pt-2 border-top mt-auto');

    var priceBox = el('div');
    priceBox.appendChild(el('span', 'fs-5 fw-bold text-dark font-monospace', money(product.price)));
    priceBox.appendChild(
      el('small', 'd-block text-muted fs-7', isOutOfStock ? 'Sin stock' : stockLeft + ' en stock')
    );
    footer.appendChild(priceBox);

    var button = el('button', 'btn-add-cart text-nowrap');
    button.type = 'button';
    button.appendChild(el('i', 'fa-solid fa-cart-plus me-1'));
    button.appendChild(document.createTextNode(isOutOfStock ? ' Agotado' : ' Agregar'));
    if (isOutOfStock) {
      button.disabled = true;
      button.style.opacity = '0.5';
      button.style.cursor = 'not-allowed';
    } else {
      button.addEventListener('click', function () {
        addToCart(product.id);
      });
    }
    footer.appendChild(button);

    body.appendChild(footer);
    card.appendChild(imageContainer);
    card.appendChild(body);
    column.appendChild(card);

    return column;
  }

  // ---------------------------------------------------------------------
  // Cart
  // ---------------------------------------------------------------------

  /**
   * Persist the cart in localStorage.
   */
  function saveCart() {
    try {
      window.localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(state.cart));
    } catch (error) {
      // Storage unavailable (private mode, disabled cookies): ignore.
    }
  }

  /**
   * Restore the cart from localStorage.
   */
  function loadCart() {
    var raw = null;
    try {
      raw = window.localStorage.getItem(CART_STORAGE_KEY);
    } catch (error) {
      raw = null;
    }
    if (!raw) {
      return;
    }

    var parsed = null;
    try {
      parsed = JSON.parse(raw);
    } catch (error) {
      parsed = null;
    }
    if (!Array.isArray(parsed)) {
      return;
    }

    state.cart = parsed
      .filter(function (item) {
        return (
          item &&
          typeof item.product_id === 'number' &&
          Number(item.quantity) > 0
        );
      })
      .map(function (item) {
        return {
          product_id: item.product_id,
          title: String(item.title || ''),
          price: Number(item.price) || 0,
          image: String(item.image || ''),
          quantity: Number(item.quantity)
        };
      });
  }

  /**
   * Add one unit of a product to the cart.
   *
   * @param {number} productId
   */
  function addToCart(productId) {
    var id = Number(productId);
    var product = state.productById.get(id);

    if (!product) {
      return;
    }

    var stock = stockFor(id);
    var inCart = cartQty(id);

    if (inCart >= stock) {
      alert(
        '⚠️ Stock agotado para "' + product.title + '". Máximo disponible: ' + stock + ' unidades.'
      );
      return;
    }

    var existing = null;
    state.cart.forEach(function (item) {
      if (item.product_id === id) {
        existing = item;
      }
    });

    if (existing) {
      existing.quantity += 1;
    } else {
      state.cart.push({
        product_id: product.id,
        title: product.title,
        price: Number(product.price) || 0,
        image: product.image,
        quantity: 1
      });
    }

    saveCart();
    refreshAll();
    openCartDrawer();
  }

  /**
   * Change the quantity of a cart line. A quantity of zero removes it.
   *
   * @param {number} productId
   * @param {number} delta
   */
  function changeQty(productId, delta) {
    var id = Number(productId);
    var item = null;

    state.cart.forEach(function (candidate) {
      if (candidate.product_id === id) {
        item = candidate;
      }
    });

    if (!item) {
      return;
    }

    if (delta > 0) {
      var stock = stockFor(id);
      if (item.quantity >= stock) {
        alert(
          '⚠️ Stock agotado para "' + item.title + '". Máximo disponible: ' + stock + ' unidades.'
        );
        return;
      }
    }

    item.quantity += delta;

    if (item.quantity <= 0) {
      removeFromCart(id);
      return;
    }

    saveCart();
    refreshAll();
  }

  /**
   * Remove a cart line.
   *
   * @param {number} productId
   */
  function removeFromCart(productId) {
    var id = Number(productId);
    state.cart = state.cart.filter(function (item) {
      return item.product_id !== id;
    });
    saveCart();
    refreshAll();
  }

  /**
   * Empty the cart.
   */
  function clearCart() {
    state.cart = [];
    saveCart();
    refreshAll();
  }

  /**
   * Re-render the grid and the drawer after a cart change. The active
   * filter is preserved because the grid is rendered from the last
   * (already filtered) catalog response.
   */
  function refreshAll() {
    renderGrid();
    updateCartUI();
  }

  /**
   * Render the cart drawer: rows, empty state, totals and counters.
   */
  function updateCartUI() {
    var container = dom.cartItems;
    container.innerHTML = '';

    var subtotal = 0;
    var totalItems = 0;

    if (!state.cart.length) {
      var empty = el('div', 'text-center py-5 text-muted');
      empty.appendChild(el('i', 'fa-solid fa-cart-arrow-down display-3 mb-3 text-secondary opacity-50'));
      empty.appendChild(el('p', 'mb-0 fw-semibold', 'El carrito está vacío'));
      empty.appendChild(el('small', '', '¡Explora el catálogo y añade tus productos!'));
      container.appendChild(empty);
    } else {
      state.cart.forEach(function (item) {
        totalItems += item.quantity;
        subtotal += item.price * item.quantity;
        container.appendChild(buildCartRow(item));
      });
    }

    var tax = subtotal * TAX_RATE;
    var total = subtotal + tax;

    dom.floatingBadge.textContent = totalItems;
    dom.navBadge.textContent = totalItems;
    dom.cartSubtotal.textContent = money(subtotal);
    dom.cartTax.textContent = money(tax);
    dom.cartTotal.textContent = money(total);
  }

  /**
   * Build a single cart row, mirroring the original markup.
   *
   * @param {object} item
   * @returns {HTMLElement}
   */
  function buildCartRow(item) {
    var row = el('div', 'cart-item-row mb-3');
    var wrapper = el('div', 'd-flex align-items-center gap-3');

    var image = document.createElement('img');
    image.src = item.image;
    image.alt = item.title;
    image.className = 'rounded';
    image.style.width = '55px';
    image.style.height = '55px';
    image.style.objectFit = 'cover';
    image.addEventListener('error', function () {
      image.src = PLACEHOLDER_IMAGE + encodeURIComponent(item.title);
    });
    wrapper.appendChild(image);

    var info = el('div', 'flex-grow-1 overflow-hidden');
    info.appendChild(el('h6', 'mb-0 text-truncate fw-bold text-dark fs-6', item.title));
    info.appendChild(el('small', 'text-muted font-monospace', money(item.price) + ' c/u'));

    var available = stockFor(item.product_id) - item.quantity;

    var controls = el('div', 'd-flex align-items-center gap-2 mt-2');
    var group = el('div', 'btn-group btn-group-sm border rounded');

    var decrease = el('button', 'btn btn-light py-0 px-2', '-');
    decrease.type = 'button';
    decrease.addEventListener('click', function () {
      changeQty(item.product_id, -1);
    });

    var quantity = el(
      'span',
      'btn btn-white py-0 px-2 fw-bold font-monospace disabled text-dark',
      String(item.quantity)
    );
    quantity.style.opacity = '1';

    var increase = el('button', 'btn btn-light py-0 px-2', '+');
    increase.type = 'button';
    if (available <= 0) {
      increase.disabled = true;
      increase.style.opacity = '0.4';
      increase.style.cursor = 'not-allowed';
    } else {
      increase.addEventListener('click', function () {
        changeQty(item.product_id, 1);
      });
    }

    group.appendChild(decrease);
    group.appendChild(quantity);
    group.appendChild(increase);
    controls.appendChild(group);
    controls.appendChild(
      el('small', 'text-muted fs-7 ms-1', available > 0 ? available + ' restantes' : 'Sin stock')
    );
    info.appendChild(controls);
    wrapper.appendChild(info);

    var side = el('div', 'text-end');
    side.appendChild(
      el('span', 'fw-bold font-monospace text-dark d-block mb-2', money(item.price * item.quantity))
    );

    var remove = el('button', 'btn btn-link text-danger p-0 border-0');
    remove.type = 'button';
    remove.title = 'Eliminar';
    remove.appendChild(el('i', 'fa-solid fa-trash-can'));
    remove.addEventListener('click', function () {
      removeFromCart(item.product_id);
    });
    side.appendChild(remove);

    wrapper.appendChild(side);
    row.appendChild(wrapper);

    return row;
  }

  // ---------------------------------------------------------------------
  // Checkout
  // ---------------------------------------------------------------------

  /**
   * Open the cart drawer.
   */
  function openCartDrawer() {
    var drawer = document.getElementById('cartOffcanvas');
    if (!drawer || typeof bootstrap === 'undefined') {
      return;
    }
    var instance = bootstrap.Offcanvas.getInstance(drawer) || new bootstrap.Offcanvas(drawer);
    instance.show();
  }

  /**
   * Hide the checkout modal.
   */
  function hideCheckoutModal() {
    var instance = bootstrap.Modal.getInstance(dom.checkoutModal);
    if (instance) {
      instance.hide();
    }
  }

  /**
   * Render the pending order summary shown in the confirm state.
   */
  function renderCheckoutSummary() {
    var container = dom.checkoutSummary;
    container.innerHTML = '';

    var list = el('div', 'border rounded-3 p-3 mb-2');
    var subtotal = 0;

    state.cart.forEach(function (item) {
      var line = el('div', 'd-flex justify-content-between small text-muted mb-1');
      line.appendChild(el('span', '', item.quantity + ' x ' + item.title));
      line.appendChild(el('span', 'font-monospace text-dark', money(item.price * item.quantity)));
      list.appendChild(line);
      subtotal += item.price * item.quantity;
    });

    var tax = subtotal * TAX_RATE;
    var total = subtotal + tax;

    var subtotalRow = el('div', 'd-flex justify-content-between small mb-1');
    subtotalRow.appendChild(el('span', 'text-muted', 'Subtotal'));
    subtotalRow.appendChild(el('span', 'font-monospace fw-bold', money(subtotal)));
    list.appendChild(subtotalRow);

    var taxRow = el('div', 'd-flex justify-content-between small mb-1');
    taxRow.appendChild(el('span', 'text-muted', 'IVA (21%)'));
    taxRow.appendChild(el('span', 'font-monospace fw-bold', money(tax)));
    list.appendChild(taxRow);

    var totalRow = el('div', 'd-flex justify-content-between small');
    totalRow.appendChild(el('span', 'text-dark fw-bold', 'Total'));
    totalRow.appendChild(el('span', 'font-monospace fw-bold text-primary', money(total)));
    list.appendChild(totalRow);

    container.appendChild(list);
  }

  /**
   * Switch the checkout modal between its 'confirm' and 'success' states.
   *
   * @param {string} mode 'confirm' or 'success'
   * @param {string=} orderNumber
   */
  function setCheckoutModalState(mode, orderNumber) {
    state.checkoutState = mode;

    if (mode === 'success') {
      dom.modalIcon.className = 'fa-solid fa-circle-check text-success display-1';
      dom.modalTitle.textContent = '¡Gracias por tu Compra!';
      dom.modalMessage.textContent =
        'Hemos registrado tu pedido correctamente. Recibirás el comprobante con los detalles del envío en tu correo electrónico.';
      dom.orderId.textContent = '#' + (orderNumber || '');
      dom.checkoutSummary.classList.add('d-none');
      dom.primaryIcon.className = 'fa-solid fa-check me-2';
      dom.primaryLabel.textContent = 'Finalizar Compra';
      dom.cancelButton.classList.add('d-none');
      return;
    }

    dom.modalIcon.className = 'fa-solid fa-circle-question text-primary display-1';
    dom.modalTitle.textContent = 'Confirmar Pedido';
    dom.modalMessage.textContent = 'Revisa el resumen de tu pedido antes de confirmar.';
    dom.orderId.textContent = 'Se generará al confirmar';
    renderCheckoutSummary();
    dom.checkoutSummary.classList.remove('d-none');
    dom.primaryIcon.className = 'fa-solid fa-check me-2';
    dom.primaryLabel.textContent = 'Confirmar Pedido';
    dom.cancelButton.classList.remove('d-none');
  }

  /**
   * Open the checkout modal in its confirm state.
   */
  function checkout() {
    if (!state.cart.length) {
      alert('Tu carrito está vacío. Agrega al menos un producto antes de finalizar la compra.');
      return;
    }

    setCheckoutModalState('confirm');
    bootstrap.Modal.getOrCreateInstance(dom.checkoutModal).show();
  }

  /**
   * Dispatch the primary button of the checkout modal.
   */
  function handleCheckoutPrimaryAction() {
    if (state.checkoutState === 'success') {
      finalizePurchase();
      return;
    }
    confirmOrder();
  }

  /**
   * Send the cart to the server and create the order.
   *
   * @returns {Promise<void>}
   */
  function confirmOrder() {
    if (!state.cart.length) {
      alert('Tu carrito está vacío. Agrega al menos un producto antes de finalizar la compra.');
      return Promise.resolve();
    }

    var payload = {
      items: state.cart.map(function (item) {
        return { product_id: item.product_id, quantity: item.quantity };
      })
    };

    dom.primaryButton.disabled = true;

    return requestJson(API_CHECKOUT, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload)
    })
      .catch(function () {
        return { ok: false, status: 0, payload: {} };
      })
      .then(function (result) {
        dom.primaryButton.disabled = false;

        if (result.status === 201) {
          setCheckoutModalState('success', result.payload.order_number);
          return loadStockIndex();
        }

        if (result.status === 409) {
          alert(result.payload.error || 'No hay stock suficiente para completar el pedido.');
          hideCheckoutModal();
          return loadStockIndex();
        }

        alert(
          result.payload.error ||
            'No se pudo procesar el pedido. Revisá tu carrito e intentá de nuevo.'
        );
        return undefined;
      });
  }

  /**
   * Close the modal and empty the cart after a successful order.
   */
  function finalizePurchase() {
    state.cart = [];
    saveCart();
    hideCheckoutModal();
    refreshAll();
  }

  /**
   * Close the modal without creating an order. The cart is preserved.
   */
  function cancelPurchase() {
    hideCheckoutModal();
  }

  // ---------------------------------------------------------------------
  // Events and bootstrap
  // ---------------------------------------------------------------------

  /**
   * Wire the filter controls.
   */
  function bindEvents() {
    dom.searchInput.addEventListener('input', function () {
      state.filters.q = dom.searchInput.value;
      window.clearTimeout(state.searchTimer);
      state.searchTimer = window.setTimeout(function () {
        loadCatalog();
      }, SEARCH_DEBOUNCE_MS);
    });

    dom.categoryFilter.addEventListener('change', function () {
      state.filters.category = dom.categoryFilter.value;
      loadCatalog();
    });

    dom.priceMin.addEventListener('input', function () {
      state.filters.minPrice = dom.priceMin.value;
      loadCatalog();
    });

    dom.priceMax.addEventListener('input', function () {
      state.filters.maxPrice = dom.priceMax.value;
      loadCatalog();
    });
  }

  /**
   * Wire the microphone button to the Web Speech API so the user can search
   * by voice. Gracefully degrades: the button is hidden when the browser
   * does not support speech recognition.
   */
  function setupVoiceSearch() {
    var SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
    if (!SpeechRecognition || !dom.voiceSearchBtn) {
      if (dom.voiceSearchBtn) {
        dom.voiceSearchBtn.classList.add('d-none');
      }
      return;
    }

    var recognition = new SpeechRecognition();
    recognition.lang = 'es-AR';
    recognition.interimResults = false;
    recognition.maxAlternatives = 1;
    recognition.continuous = false;

    var listening = false;

    function setListening(state) {
      listening = state;
      var icon = dom.voiceSearchBtn.querySelector('i');
      if (state) {
        dom.voiceSearchBtn.classList.remove('btn-light');
        dom.voiceSearchBtn.classList.add('btn-danger');
        if (icon) {
          icon.className = 'fa-solid fa-microphone-lines';
        }
        dom.searchInput.placeholder = 'Escuchando... hablá ahora';
      } else {
        dom.voiceSearchBtn.classList.remove('btn-danger');
        dom.voiceSearchBtn.classList.add('btn-light');
        if (icon) {
          icon.className = 'fa-solid fa-microphone';
        }
        dom.searchInput.placeholder = 'Buscar por título o descripción (ej. Rotulador, Cuaderno, Escuadra)...';
      }
    }

    recognition.onresult = function (event) {
      var transcript = '';
      for (var i = 0; i < event.results.length; i++) {
        transcript += event.results[i][0].transcript;
      }
      transcript = transcript.trim();
      if (transcript) {
        dom.searchInput.value = transcript;
        // Reuse the existing debounced filter path.
        dom.searchInput.dispatchEvent(new Event('input', { bubbles: true }));
      }
    };

    recognition.onerror = function (event) {
      if (event.error === 'not-allowed' || event.error === 'service-not-allowed') {
        alert('No se pudo acceder al micrófono. Revisá los permisos del navegador.');
      } else if (event.error === 'no-speech') {
        // Silent: the user simply did not speak.
      } else if (event.error !== 'aborted') {
        alert('Error de reconocimiento de voz: ' + event.error);
      }
      setListening(false);
    };

    recognition.onend = function () {
      setListening(false);
    };

    dom.voiceSearchBtn.addEventListener('click', function () {
      if (listening) {
        try { recognition.stop(); } catch (e) { /* ignore */ }
        setListening(false);
        return;
      }
      try {
        recognition.start();
        setListening(true);
      } catch (e) {
        // Recognition may already be running; ignore.
        setListening(false);
      }
    });
  }

  /**
   * Cache the DOM references used across the application.
   */
  function cacheDom() {
    dom.productsGrid = byId('products-grid');
    dom.noProducts = byId('no-products');
    dom.cartItems = byId('cart-items-container');
    dom.cartSubtotal = byId('cart-subtotal');
    dom.cartTax = byId('cart-tax');
    dom.cartTotal = byId('cart-total');
    dom.navBadge = byId('nav-cart-badge');
    dom.floatingBadge = byId('floating-cart-badge');
    dom.searchInput = byId('search-input');
    dom.voiceSearchBtn = byId('voice-search-btn');
    dom.categoryFilter = byId('category-filter');
    dom.priceMin = byId('price-min');
    dom.priceMax = byId('price-max');
    dom.checkoutModal = byId('checkoutModal');
    dom.modalIcon = byId('checkout-modal-icon');
    dom.modalTitle = byId('checkout-modal-title');
    dom.modalMessage = byId('checkout-modal-message');
    dom.orderId = byId('order-id');
    dom.checkoutSummary = byId('checkout-summary');
    dom.primaryButton = byId('checkout-primary-button');
    dom.primaryIcon = byId('checkout-primary-icon');
    dom.primaryLabel = byId('checkout-primary-label');
    dom.cancelButton = byId('checkout-cancel-button');
  }

  /**
   * Application entry point.
   */
  function init() {
    cacheDom();
    loadCart();
    bindEvents();
    setupVoiceSearch();
    updateCartUI();
    loadCategories();
    loadCatalog();
  }

  // Expose the handlers used by the inline `onclick` attributes.
  window.addToCart = addToCart;
  window.changeQty = changeQty;
  window.removeFromCart = removeFromCart;
  window.clearCart = clearCart;
  window.checkout = checkout;
  window.confirmOrder = confirmOrder;
  window.finalizePurchase = finalizePurchase;
  window.cancelPurchase = cancelPurchase;
  window.handleCheckoutPrimaryAction = handleCheckoutPrimaryAction;

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
