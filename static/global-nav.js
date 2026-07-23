(function() {
    const path = window.location.pathname;
    const filename = path.split('/').pop();
    const headerLinks = document.querySelectorAll('.header-nav a');

    // Get current price mode context
    // ?price_mode= in the URL acts as a one-time override (e.g. shared links);
    // normal navigation relies solely on localStorage.
    const urlParams = new URLSearchParams(window.location.search);
    const urlMode = urlParams.get('price_mode');
    const storedMode = localStorage.getItem("price_mode") || "intraday";
    const currentMode = urlMode || storedMode;

    if (urlMode && urlMode !== storedMode) {
        // Persist the URL override to storage, then strip the param from the address bar
        localStorage.setItem("price_mode", urlMode);
        const cleanUrl = new URL(window.location.href);
        cleanUrl.searchParams.delete("price_mode");
        window.history.replaceState(null, "", cleanUrl.toString());
    }

    // Setup Price Mode select and Force Refresh button listeners
    const priceModeSelect = document.getElementById("price-mode-select");
    if (priceModeSelect) {
        priceModeSelect.value = currentMode;
        priceModeSelect.addEventListener("change", (e) => {
            const newMode = e.target.value;
            localStorage.setItem("price_mode", newMode);
            window.location.reload();
        });
    }

    const forceRefreshBtn = document.getElementById("force-refresh-btn");
    const refreshIcon = document.getElementById("refresh-icon");
    if (forceRefreshBtn) {
        forceRefreshBtn.addEventListener("click", async () => {
            if (refreshIcon) refreshIcon.style.animation = "spin 1s linear infinite";
            forceRefreshBtn.disabled = true;
            document.body.style.cursor = "wait";
            forceRefreshBtn.style.opacity = "0.6";
            try {
                const res = await fetch("/api/prices/refresh?force=true", { method: "POST" });
                if (res.ok) {
                    window.location.reload();
                } else {
                    alert("Failed to refresh prices. Cooldown may be active.");
                }
            } catch (err) {
                console.error("Refresh failed:", err);
                alert("Error connecting to server.");
            } finally {
                forceRefreshBtn.disabled = false;
                if (refreshIcon) refreshIcon.style.animation = "";
                document.body.style.cursor = "default";
                forceRefreshBtn.style.opacity = "1";
            }
        });
    }

    const rebuildBtn = document.getElementById("rebuild-btn");
    const rebuildIcon = document.getElementById("rebuild-icon");
    if (rebuildBtn) {
        rebuildBtn.addEventListener("click", async () => {
            if (rebuildIcon) rebuildIcon.style.animation = "spin 1s linear infinite";
            rebuildBtn.disabled = true;
            document.body.style.cursor = "wait";
            rebuildBtn.style.opacity = "0.6";
            try {
                const res = await fetch("/api/dashboard/rebuild?sync=true", { method: "POST" });
                if (res.ok) {
                    window.location.reload();
                } else {
                    alert("Failed to rebuild dashboard.");
                }
            } catch (err) {
                console.error("Rebuild failed:", err);
                alert("Error connecting to server.");
            } finally {
                rebuildBtn.disabled = false;
                if (rebuildIcon) rebuildIcon.style.animation = "";
                document.body.style.cursor = "default";
                rebuildBtn.style.opacity = "1";
            }
        });
    }

    // Lazy-load transaction dropdowns
    document.querySelectorAll(".tx-details-wrapper").forEach(details => {
        details.addEventListener("toggle", async () => {
            if (details.open && !details.dataset.loaded) {
                const symbol = details.dataset.symbol;
                const year = details.dataset.year;
                const portfolioId = details.dataset.portfolioId;
                const currency = details.dataset.currency;
                const currentPrice = parseFloat(details.dataset.currentPrice) || 0;
                const isClosed = details.dataset.isClosed === "true";
                const contentDiv = details.querySelector(".details-content");

                try {
                    let url = `/api/transactions?symbol=${encodeURIComponent(symbol)}`;
                    if (portfolioId) {
                        url += `&portfolio_id=${portfolioId}`;
                    }
                    const res = await fetch(url);
                    if (!res.ok) throw new Error("HTTP error");
                    const transactions = await res.json();

                    // Filter transactions by year
                    const filtered = transactions.filter(t => t.date && t.date.substring(0, 4) === year);
                    
                    if (filtered.length === 0) {
                        contentDiv.innerHTML = '<div style="padding: 10px 0; color: var(--text-secondary); font-size: 0.9rem;">No transactions found.</div>';
                        details.dataset.loaded = "true";
                        return;
                    }

                    const formatCommas = (val, prec = 2) => {
                        if (val === null || val === undefined) return "0.00";
                        return parseFloat(val).toLocaleString(undefined, { minimumFractionDigits: prec, maximumFractionDigits: prec });
                    };

                    const formatQty = (val) => {
                        if (val === null || val === undefined) return "0";
                        const f = parseFloat(val);
                        return f % 1 === 0 ? parseInt(val).toString() : f.toString();
                    };

                    let html = '<ul style="list-style: none; padding: 0; margin: 0;">';
                    filtered.forEach(t => {
                        const qty = parseFloat(t.quantity) || 0;
                        const price = parseFloat(t.price) || 0;
                        const fee = parseFloat(t.commission) || 0;
                        const action = t.action || "Buy";
                        const dateOnly = t.date ? t.date.substring(0, 10) : "";
                        const actionUpper = action.toUpperCase();
                        const actionLower = action.toLowerCase();

                        const t_net = actionUpper === "BUY" ? (qty * price + fee) : (qty * price - fee);

                        let itemHtml = `<li class="tx-item" style="padding: 5px 0; font-family: monospace; font-size: 0.9rem; border-bottom: 1px solid rgba(255,255,255,0.08); color: var(--text-primary);">
                            <span class="${actionLower}" style="font-weight: bold; color: ${actionUpper === 'BUY' ? '#2ecc71' : '#e74c3c'}">[${actionUpper}]</span>
                            [${dateOnly}] 
                            ${formatQty(qty)} @ ${formatCommas(price, 4)} ${currency}, 
                            Fees: ${formatCommas(fee)} 
                            (${formatCommas(t_net)} ${currency})`;

                        if (actionUpper === "BUY" && !isClosed) {
                            const c_val = qty * currentPrice;
                            const g_pct = price > 0 ? ((c_val / (qty * price)) - 1) * 100 : 0;
                            const sign = g_pct > 0 ? "+" : "";
                            const colorClass = g_pct < 0 ? "neg-val" : "pos-val";
                            const colorStyle = g_pct < 0 ? "color: #e74c3c;" : "color: #2ecc71;";

                            itemHtml += ` <span class="metadata" style="color: var(--text-secondary); font-size: 0.85rem;">
                                (Current Value: ${formatCommas(c_val)} ${currency}, 
                                <span class="${colorClass}" style="${colorStyle}">${sign}${g_pct.toFixed(2)}%, ${sign}${formatCommas(c_val - t_net)} ${currency}</span>)
                            </span>`;
                        }

                        itemHtml += `</li>`;
                        html += itemHtml;
                    });
                    html += '</ul>';

                    contentDiv.innerHTML = html;
                    details.dataset.loaded = "true";
                } catch (err) {
                    console.error("Failed to load transactions:", err);
                    contentDiv.innerHTML = '<div style="padding: 10px 0; color: #e74c3c; font-size: 0.9rem;">Failed to load transactions. Click to retry.</div>';
                }
            }
        });
    });

    // --- Classification Dropdown & Highlighting Logic ---
    // 1. Determine current classification slug
    let currentSlug = 'all';
    const filterParam = urlParams.get('filter');
    if (filterParam) {
        currentSlug = filterParam;
    }

    // 2. Setup toggle behavior for all dropdown menus (Classification, Analytics, Portfolio, Add)
    const dropdownsList = [
        { btnId: "nav-perf-toggle", menuId: "nav-perf-dropdown" },
        { btnId: "nav-tools-main", menuId: "nav-tools-dropdown" },
        { btnId: "nav-add-toggle", menuId: "nav-add-dropdown" },
        { btnId: "nav-services-toggle", menuId: "nav-services-dropdown" },
        { btnId: "portfolio-select-btn", menuId: "portfolio-dropdown-menu" },
        { btnId: "classification-select-btn", menuId: "classification-dropdown-menu" }
    ];

    dropdownsList.forEach(({ btnId, menuId }) => {
        const btn = document.getElementById(btnId);
        const menu = document.getElementById(menuId);
        if (btn && menu) {
            if (btnId !== "portfolio-select-btn") {
                btn.addEventListener("click", (e) => {
                    e.preventDefault();
                    e.stopPropagation();
                    
                    // Close all other dropdowns
                    dropdownsList.forEach(d => {
                        if (d.menuId !== menuId) {
                            const m = document.getElementById(d.menuId);
                            if (m) m.classList.remove("show");
                        }
                    });
                    
                    menu.classList.toggle("show");
                });
                
                document.addEventListener("click", () => {
                    menu.classList.remove("show");
                });
                
                menu.addEventListener("click", (e) => {
                    // Only stop propagation if we did NOT click an anchor link
                    if (e.target.closest('a')) {
                        menu.classList.remove("show");
                    } else {
                        e.stopPropagation();
                    }
                });
            }
        }
    });

    const dropdown = document.getElementById("classification-dropdown-menu");

    // 3. Highlight selected option and update dropdown button display text
    if (dropdown) {
        const activeItem = dropdown.querySelector(`.portfolio-item[data-slug="${currentSlug}"]`);
        if (activeItem) {
            activeItem.classList.add('selected');
            const displaySpan = document.getElementById('current-classification-display');
            if (displaySpan) {
                const name = activeItem.querySelector('span').textContent;
                const icon = activeItem.querySelector('.icon').textContent;
                displaySpan.innerHTML = `${icon} ${name}`;
            }
        }
    }


    // 4. Highlight global header nav links
    const basePath = window.BASE_PATH || "";
    headerLinks.forEach(link => {
        if (link.classList.contains('nav-dropdown-toggle') || link.getAttribute('href') === '#') {
            link.classList.remove('active');
            return;
        }
        if (link.closest('.nav-add-container') || link.search.includes('add=')) {
            link.classList.remove('active');
            return;
        }
        let linkPath = link.pathname;

        // Normalize linkPath by removing basePath prefix if present
        if (basePath && linkPath.startsWith(basePath)) {
            linkPath = linkPath.substring(basePath.length);
        }
        // Also normalize the current window path by removing basePath prefix
        let normPath = path;
        if (basePath && normPath.startsWith(basePath)) {
            normPath = normPath.substring(basePath.length);
        }

        let isActive = false;
        
        if (linkPath === '/admin') {
            const hasTabSettings = link.search.includes('tab=settings');
            const currentHasTabSettings = window.location.search.includes('tab=settings');
            if (hasTabSettings) {
                isActive = (normPath === '/admin' || normPath === '/manage') && currentHasTabSettings;
            } else {
                isActive = (normPath === '/admin' || normPath === '/manage') && !currentHasTabSettings;
            }
        } else if (linkPath === '/' || linkPath === '/active') {
            isActive = (normPath === '/' || normPath === '/active');
        } else if (linkPath === '/closed') {
            isActive = (normPath === '/closed');
        } else if (linkPath === '/history') {
            isActive = (normPath === '/history');
        } else if (linkPath.includes('charts')) {
            isActive = (normPath === '/charts');
        } else if (linkPath.includes('performance')) {
            isActive = (normPath === '/performance');
        } else {
            isActive = (normPath === linkPath);
        }

        if (isActive) {
            link.classList.add('active');
        } else {
            link.classList.remove('active');
        }
    });

    // Highlight "Portfolio" and "Analytics" parent link if any child sub-link is active
    const toolsBtn = document.getElementById("nav-tools-main");
    if (toolsBtn) {
        let normPath2 = path;
        if (basePath && normPath2.startsWith(basePath)) {
            normPath2 = normPath2.substring(basePath.length);
        }
        const isAdminActive = (normPath2 === '/admin' || normPath2 === '/manage');
        if (isAdminActive) {
            toolsBtn.classList.add('active');
        } else {
            toolsBtn.classList.remove('active');
        }
    }

    const perfBtn = document.getElementById("nav-perf-toggle");
    if (perfBtn) {
        let normPath2 = path;
        if (basePath && normPath2.startsWith(basePath)) {
            normPath2 = normPath2.substring(basePath.length);
        }
        const isClosedActive = (normPath2 === '/closed');
        const isChartsActive = (normPath2 === '/charts');
        const isPerfActive = (normPath2 === '/performance');
        const isHistoryActive = (normPath2 === '/history');
        if (isClosedActive || isChartsActive || isPerfActive || isHistoryActive) {
            perfBtn.classList.add('active');
        } else {
            perfBtn.classList.remove('active');
        }
    }

    // Mobile menu hamburger toggle logic
    const menuToggleBtn = document.getElementById("menu-toggle-btn");
    const navContainer = document.getElementById("header-nav-container");
    if (menuToggleBtn && navContainer) {
        menuToggleBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            menuToggleBtn.classList.toggle("active");
            navContainer.classList.toggle("show");
        });

        // Close menu when clicking outside
        document.addEventListener("click", (e) => {
            if (!navContainer.contains(e.target) && !menuToggleBtn.contains(e.target)) {
                menuToggleBtn.classList.remove("active");
                navContainer.classList.remove("show");
            }
        });
    }

})();
