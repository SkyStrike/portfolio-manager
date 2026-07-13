// State Management
let selectedPortfolioId = null; // null means My Net Worth (Combined)
let selectedPortfolioName = "My Net Worth";
let portfoliosList = [];
let tickersList = [];
let exchangeRates = { USD: 1.35, CAD: 1.0, SGD: 1.0 }; // Fallback
let currentHoldings = [];
let sortColumn = "value_sgd";
let sortDirection = "desc";
let dashboardViewMode = localStorage.getItem("dashboardViewMode") || "cards";
let cachedTickers = []; // for ticker settings tab search
let cachedUnderlyingAssets = [];
let cachedTransactions = [];
let cachedDividends = [];
let cachedCapitalEntries = [];
let cachedDailyCashHistory = [];

// Pagination State
let currentTradesPage = 1;
let currentDividendsPage = 1;
let currentCapitalPage = 1;
let currentTickersPage = 1;
let currentDailyCashPage = 1;
const PAGE_SIZE = 100;

// Chart instances
let allocationChart = null;
let dividendChart = null;

// Currency Formatter Helpers
function formatCurrency(val, currency = "SGD") {
    const sym = currency === "USD" ? "USD " : (currency === "CAD" ? "CAD " : "S$");
    return sym + Number(val).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function formatPercent(val) {
    const prefix = val >= 0 ? "+" : "";
    return `${prefix}${Number(val).toFixed(2)}%`;
}

// Generic function to update client-side pagination UI controls (handles both top and bottom)
function updatePaginationControls(selector, currentPage, totalItems, onPageChange) {
    const containers = document.querySelectorAll(selector);
    containers.forEach(container => {
        if (!container) return;

        const prevBtn = container.querySelector(".btn-prev");
        const nextBtn = container.querySelector(".btn-next");
        const pageInfo = container.querySelector(".page-info");

        const totalPages = Math.max(1, Math.ceil(totalItems / PAGE_SIZE));

        if (pageInfo) {
            pageInfo.textContent = `Page ${currentPage} of ${totalPages}`;
        }

        if (prevBtn) {
            prevBtn.disabled = currentPage <= 1;
            const newPrevBtn = prevBtn.cloneNode(true);
            newPrevBtn.disabled = currentPage <= 1;
            newPrevBtn.addEventListener("click", () => onPageChange(currentPage - 1));
            prevBtn.replaceWith(newPrevBtn);
        }

        if (nextBtn) {
            nextBtn.disabled = currentPage >= totalPages;
            const newNextBtn = nextBtn.cloneNode(true);
            newNextBtn.disabled = currentPage >= totalPages;
            newNextBtn.addEventListener("click", () => onPageChange(currentPage + 1));
            nextBtn.replaceWith(newNextBtn);
        }
    });
}

// Toast Notification
function showToast(message, type = "success") {
    const container = document.getElementById("toast-container");
    const toast = document.createElement("div");
    toast.className = "toast";
    if (type === "error") {
        toast.style.borderLeftColor = "var(--color-loss)";
    }
    toast.textContent = message;
    container.appendChild(toast);
    
    setTimeout(() => {
        toast.style.opacity = "0";
        toast.style.transform = "translateY(-10px)";
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// Modal management helpers
window.openModal = function(id) {
    document.getElementById(id).classList.add("show");
};

window.closeModal = function(id) {
    document.getElementById(id).classList.remove("show");
};

// Document Ready
document.addEventListener("DOMContentLoaded", () => {
    initApp();
});

async function initApp() {
    setupNavigation();
    setupDropdownEvents();
    setupFormSubmissions();
    setupAutocomplete();
    setupTableSorting();
    setupCustomAppEvents();
    
    // Initialize transaction modal calculation bindings
    setupTransactionModalCalculation();
    
    // Load initial reference data concurrently
    await Promise.all([loadPortfolios(), loadTickersList()]);
    
    // Detect page route for default tabs and redirect constraints
    const isControlCenterPage = window.location.pathname.includes("control-center");
    const controlCenterTabs = ["settings", "import", "imports", "capital", "dailycash", "maintenance"];
    const tradesTabs = ["transactions", "trades", "dividends", "tickers"];
    
    // Check URL parameters for quick add request, portfolio action, or tab selection on load
    const urlParams = new URLSearchParams(window.location.search);
    const addParam = urlParams.get("add");
    const actionParam = urlParams.get("action");
    const tabParam = urlParams.get("tab");

    // Perform cross-page redirects if parameters belong to the other page
    if (tabParam) {
        const normalizedTab = tabParam.toLowerCase();
        if (isControlCenterPage && tradesTabs.includes(normalizedTab)) {
            const basePath = window.BASE_PATH || "";
            window.location.href = `${basePath}/trades?tab=${tabParam}`;
            return;
        } else if (!isControlCenterPage && controlCenterTabs.includes(normalizedTab)) {
            const basePath = window.BASE_PATH || "";
            window.location.href = `${basePath}/control-center?tab=${tabParam}`;
            return;
        }
    }
    
    if (addParam) {
        if (isControlCenterPage && (addParam === "trades" || addParam === "incomes" || addParam === "expenses")) {
            const basePath = window.BASE_PATH || "";
            window.location.href = `${basePath}/trades?add=${addParam}`;
            return;
        } else if (!isControlCenterPage && (addParam === "capital" || addParam === "cash-metrics" || addParam === "dailycash")) {
            const basePath = window.BASE_PATH || "";
            window.location.href = `${basePath}/control-center?add=${addParam}`;
            return;
        }
    }

    let initialNav = isControlCenterPage ? "nav-settings" : "nav-transactions";
    let initialSec = isControlCenterPage ? "section-settings" : "section-transactions";

    if (tabParam) {
        if (tabParam === "settings") {
            initialNav = "nav-settings";
            initialSec = "section-settings";
        } else if (tabParam === "import" || tabParam === "imports") {
            initialNav = "nav-import";
            initialSec = "section-import";
        } else if (tabParam === "tickers") {
            initialNav = "nav-tickers";
            initialSec = "section-tickers";
        } else if (tabParam === "dividends") {
            initialNav = "nav-dividends";
            initialSec = "section-dividends";
        } else if (tabParam === "capital") {
            initialNav = "nav-capital";
            initialSec = "section-capital";
        } else if (tabParam === "dailycash") {
            initialNav = "nav-dailycash";
            initialSec = "section-dailycash";
        } else if (tabParam === "maintenance") {
            initialNav = "nav-maintenance";
            initialSec = "section-maintenance";
        }
    }
    
    if (addParam) {
        if (addParam === "trades" || addParam === "incomes" || addParam === "expenses") {
            openTransactionModal(addParam);
        } else if (addParam === "capital") {
            initialNav = "nav-capital";
            initialSec = "section-capital";
            setTimeout(() => {
                openCapitalAddModal();
            }, 100);
        } else if (addParam === "cash-metrics" || addParam === "dailycash") {
            initialNav = "nav-dailycash";
            initialSec = "section-dailycash";
            setTimeout(() => {
                openCashMetricsModal("MOOMOO");
            }, 100);
        } else {
            openTransactionModal("trades");
        }

        
        // Clean up URL query parameters without page refresh
        const cleanUrl = window.location.pathname;
        window.history.replaceState({}, document.title, cleanUrl);
    } else if (actionParam) {
        if (actionParam === "add_portfolio") {
            const form = document.getElementById("portfolio-add-form");
            if (form) form.reset();
            openModal("portfolio-add-modal");
        } else if (actionParam === "manage_portfolios") {
            renderManagePortfolios();
            openModal("portfolio-manage-modal");
        }
        
        // Clean up URL query parameters without page refresh
        const cleanUrl = window.location.pathname;
        window.history.replaceState({}, document.title, cleanUrl);
    } else if (tabParam) {
        // Clean up URL query parameters without page refresh if tab param was supplied
        const cleanUrl = window.location.pathname;
        window.history.replaceState({}, document.title, cleanUrl);
    }
    
    // Load initial view
    switchView(initialNav, initialSec);
}

/* 1. Header Navigation Router */
const navs = [
    { navId: "nav-transactions", secId: "section-transactions", callback: loadTransactions },
    { navId: "nav-dividends", secId: "section-dividends", callback: loadDividends },
    { navId: "nav-tickers", secId: "section-tickers", callback: loadTickers },
    { navId: "nav-capital", secId: "section-capital", callback: loadCapitalEntries },
    { navId: "nav-dailycash", secId: "section-dailycash", callback: loadDailyCashHistory },
    { navId: "nav-import", secId: "section-import", callback: loadImportWizard },
    { navId: "nav-settings", secId: "section-settings", callback: loadSettingsEditor },
    { navId: "nav-maintenance", secId: "section-maintenance", callback: loadMaintenanceTab }
];

function setupNavigation() {
    const logoBtn = document.getElementById("logo-btn");
    if (logoBtn) {
        logoBtn.addEventListener("click", () => {
            const basePath = window.BASE_PATH || "";
            window.location.href = basePath + "/";
        });
    }
    
    navs.forEach(nav => {
        const el = document.getElementById(nav.navId);
        if (el) {
            el.addEventListener("click", () => {
                switchView(nav.navId, nav.secId);
            });
        }
    });
}

function switchView(navId, secId) {
    // Toggle active link
    navs.forEach(nav => {
        const navEl = document.getElementById(nav.navId);
        const secEl = document.getElementById(nav.secId);
        if (navEl) navEl.classList.remove("active");
        if (secEl) secEl.style.display = "none";
    });
    const targetNav = document.getElementById(navId);
    const targetSec = document.getElementById(secId);
    if (targetNav) targetNav.classList.add("active");
    if (targetSec) targetSec.style.display = "block";
    
    // Run appropriate callback
    const activeNav = navs.find(n => n.navId === navId);
    if (activeNav && activeNav.callback) {
        activeNav.callback();
    }
}

/* 2. Dropdown Header Selector Events */
function setupDropdownEvents() {
    const selectBtn = document.getElementById("portfolio-select-btn");
    const dropdown = document.getElementById("portfolio-dropdown-menu");
    
    if (selectBtn && dropdown) {
        selectBtn.addEventListener("click", (e) => {
            e.stopPropagation();
            dropdown.classList.toggle("show");
            
            // Close other dropdowns
            const otherDropdowns = ["nav-perf-dropdown", "nav-tools-dropdown", "nav-add-dropdown", "nav-services-dropdown"];
            otherDropdowns.forEach(id => {
                const m = document.getElementById(id);
                if (m) m.classList.remove("show");
            });
        });
        
        document.addEventListener("click", () => {
            dropdown.classList.remove("show");
        });
        
        dropdown.addEventListener("click", (e) => {
            e.stopPropagation();
        });
    }

    // Modal buttons triggers
    const addPortBtn = document.getElementById("add-portfolio-trigger-btn");
    if (addPortBtn) {
        addPortBtn.addEventListener("click", (e) => {
            e.preventDefault();
            if (dropdown) dropdown.classList.remove("show");
            const form = document.getElementById("portfolio-add-form");
            if (form) form.reset();
            openModal("portfolio-add-modal");
        });
    }
    
    const managePortBtn = document.getElementById("manage-portfolios-trigger-btn");
    if (managePortBtn) {
        managePortBtn.addEventListener("click", (e) => {
            e.preventDefault();
            if (dropdown) dropdown.classList.remove("show");
            renderManagePortfolios();
            openModal("portfolio-manage-modal");
        });
    }
}

// Retrieve portfolios from server
async function loadPortfolios() {
    try {
        const res = await fetch("/api/portfolios");
        portfoliosList = await res.json();
        renderPortfolioSelector();
        
        // Seed select inputs in forms
        updatePortfolioSelectInputs();
    } catch (e) {
        showToast("Error loading portfolios: " + e.message, "error");
    }
}

function renderPortfolioSelector() {
    const listWrapper = document.getElementById("portfolio-dropdown-list");
    listWrapper.innerHTML = "";
    
    // Combined View Row
    const combinedItem = document.createElement("div");
    combinedItem.className = `portfolio-item ${selectedPortfolioId === null ? "selected" : ""}`;
    combinedItem.innerHTML = `
        <div class="icon">💰</div>
        <span>My Net Worth</span>
    `;
    combinedItem.addEventListener("click", () => {
        selectPortfolio(null, "My Net Worth");
    });
    listWrapper.appendChild(combinedItem);
    
    // Individual Portfolios
    portfoliosList.forEach(p => {
        const item = document.createElement("div");
        item.className = `portfolio-item ${selectedPortfolioId === p.id ? "selected" : ""}`;
        item.innerHTML = `
            <div class="icon">💼</div>
            <span>${p.name}</span>
        `;
        item.addEventListener("click", () => {
            selectPortfolio(p.id, p.name);
        });
        listWrapper.appendChild(item);
    });
}

function selectPortfolio(id, name) {
    selectedPortfolioId = id;
    selectedPortfolioName = name;
    
    // Update display button text
    document.getElementById("current-portfolio-display").textContent = id === null ? "💰 My Net Worth" : `💼 ${name}`;
    document.getElementById("portfolio-dropdown-menu").classList.remove("show");
    
    // Refresh portfolio selector selected class
    renderPortfolioSelector();
    
    // Refresh current active view
    const activeNav = navs.find(n => document.getElementById(n.navId).classList.contains("active"));
    if (activeNav && activeNav.callback) {
        activeNav.callback();
    }
}

function updatePortfolioSelectInputs() {
    const selectTxs = document.getElementById("tx-portfolio");
    const selectImport = document.getElementById("import-portfolio-select");
    
    const optionsHtml = portfoliosList.map(p => `<option value="${p.id}">${p.name}</option>`).join("");
    
    if (selectTxs) selectTxs.innerHTML = optionsHtml;
    if (selectImport) selectImport.innerHTML = '<option value="">-- Create Portfolio Name below --</option>' + optionsHtml;
}

/* 3. Dashboard View Calculations & rendering */
async function loadDashboard() {
    try {
        const url = selectedPortfolioId !== null 
            ? `/api/dashboard/summary?portfolio_id=${selectedPortfolioId}`
            : "/api/dashboard/summary";
            
        const res = await fetch(url);
        const data = await res.json();
        
        // Renders KPI values
        document.getElementById("kpi-value-worth").textContent = formatCurrency(data.total_value_sgd);
        document.getElementById("kpi-subtext-worth").textContent = "Cost basis: " + formatCurrency(data.total_cost_sgd);
        
        const dailyCardVal = document.getElementById("kpi-value-daily");
        const dailyCardSub = document.getElementById("kpi-subtext-daily");
        dailyCardVal.textContent = formatCurrency(data.total_daily_pl_sgd);
        dailyCardVal.className = `kpi-value ${data.total_daily_pl_sgd >= 0 ? "text-gain" : "text-loss"}`;
        dailyCardSub.textContent = formatPercent(data.total_daily_pl_pct);
        dailyCardSub.className = `kpi-subtext ${data.total_daily_pl_pct >= 0 ? "text-gain" : "text-loss"}`;
        
        const unrealizedVal = document.getElementById("kpi-value-unrealized");
        const unrealizedSub = document.getElementById("kpi-subtext-unrealized");
        unrealizedVal.textContent = formatCurrency(data.total_unrealized_pl_sgd);
        unrealizedVal.className = `kpi-value ${data.total_unrealized_pl_sgd >= 0 ? "text-gain" : "text-loss"}`;
        unrealizedSub.textContent = formatPercent(data.total_unrealized_pl_pct);
        unrealizedSub.className = `kpi-subtext ${data.total_unrealized_pl_pct >= 0 ? "text-gain" : "text-loss"}`;
        
        document.getElementById("kpi-value-dividends").textContent = formatCurrency(data.total_dividends_net_sgd);
        document.getElementById("kpi-subtext-dividends").textContent = "Gross: " + formatCurrency(data.total_dividends_gross_sgd);
        
        const profitVal = document.getElementById("kpi-value-profit");
        profitVal.textContent = (data.total_profit_sgd >= 0 ? "+" : "") + formatCurrency(data.total_profit_sgd);
        profitVal.className = `kpi-value ${data.total_profit_sgd >= 0 ? "text-gain" : "text-loss"}`;
        
        const profitPct = data.total_cost_sgd > 0 ? (data.total_profit_sgd / data.total_cost_sgd * 100) : 0.0;
        const profitSub = document.getElementById("kpi-subtext-profit");
        profitSub.textContent = formatPercent(profitPct);
        profitSub.className = `kpi-subtext ${profitPct >= 0 ? "text-gain" : "text-loss"}`;
        
        // Populate Tooltip Elements
        const capGain = data.total_unrealized_pl_sgd;
        const capGainEl = document.getElementById("tooltip-capital-gain");
        capGainEl.textContent = (capGain >= 0 ? "+" : "-") + formatCurrency(Math.abs(capGain));
        capGainEl.className = "tooltip-value " + (capGain >= 0 ? "text-gain" : "text-loss");
        
        const realizedPl = data.total_realized_pl_sgd;
        const realizedPlEl = document.getElementById("tooltip-realized-pl");
        realizedPlEl.textContent = (realizedPl >= 0 ? "+" : "-") + formatCurrency(Math.abs(realizedPl));
        realizedPlEl.className = "tooltip-value " + (realizedPl >= 0 ? "text-gain" : "text-loss");
        
        const divGross = data.total_dividends_gross_sgd;
        const divGrossEl = document.getElementById("tooltip-dividends-gross");
        divGrossEl.textContent = "+" + formatCurrency(divGross);
        divGrossEl.className = "tooltip-value text-gain";
        
        const divTax = data.total_dividend_taxes_sgd;
        const divTaxEl = document.getElementById("tooltip-dividends-tax");
        divTaxEl.textContent = "-" + formatCurrency(divTax);
        divTaxEl.className = "tooltip-value text-loss";
        
        const feesPaid = data.total_fees_sgd;
        const feesPaidEl = document.getElementById("tooltip-fees-paid");
        feesPaidEl.textContent = "-" + formatCurrency(feesPaid);
        feesPaidEl.className = "tooltip-value text-loss";
        
        const totalProfit = data.total_profit_sgd;
        const totalProfitEl = document.getElementById("tooltip-total-profit");
        totalProfitEl.textContent = (totalProfit >= 0 ? "+" : "-") + formatCurrency(Math.abs(totalProfit));
        totalProfitEl.className = "tooltip-value " + (totalProfit >= 0 ? "text-gain" : "text-loss");
        
        // Render Holdings Table
        currentHoldings = data.holdings || [];
        renderHoldingsTable(currentHoldings);
        
        // Render Charts
        renderCharts(data);
        
    } catch (e) {
        showToast("Error loading dashboard: " + e.message, "error");
    }
}

function renderHoldingsTable(holdings) {
    const tableWrapper = document.getElementById("holdings-table-wrapper");
    const cardsWrapper = document.getElementById("holdings-cards-wrapper");
    const tbody = document.getElementById("holdings-table-body");
    
    // Safety check in case elements aren't initialized yet
    if (!tbody || !tableWrapper || !cardsWrapper) return;
    
    tbody.innerHTML = "";
    cardsWrapper.innerHTML = "";
    
    if (!holdings || holdings.length === 0) {
        tbody.innerHTML = `<tr><td colspan="9" style="text-align: center; color: var(--text-muted); padding: 2rem;">No holdings found. Upload transactions to start.</td></tr>`;
        cardsWrapper.innerHTML = `<div style="text-align: center; color: var(--text-muted); padding: 3rem; background: var(--card-bg); border: 1px solid var(--card-border); border-radius: 12px; width: 100%;">No holdings found. Upload transactions to start.</div>`;
        return;
    }
    
    // Toggle element displays based on mode
    if (dashboardViewMode === "table") {
        tableWrapper.style.display = "block";
        cardsWrapper.style.setProperty("display", "none", "important");
    } else {
        tableWrapper.style.setProperty("display", "none", "important");
        cardsWrapper.style.display = "flex";
    }
    
    // Initialize collapsedGroups store if not already present
    window.collapsedGroups = window.collapsedGroups || {};
    
    const totalValSgd = holdings.reduce((sum, h) => sum + h.value_sgd, 0);
    
    holdings.forEach(h => {
        h.allocation_pct = totalValSgd > 0 ? (h.value_sgd / totalValSgd) * 100 : 0.0;
    });
    
    // Group holdings by underlying
    const groupsMap = {};
    holdings.forEach(h => {
        const und = h.underlying || h.name || h.symbol;
        if (!groupsMap[und]) {
            groupsMap[und] = {
                underlying: und,
                holdings: [],
                value_sgd: 0,
                total_pl_sgd: 0,
                daily_pl_sgd: 0,
                cost_sgd: 0,
                prev_close_sgd: 0,
                allocation_pct: 0
            };
        }
        groupsMap[und].holdings.push(h);
    });

    // Calculate aggregated metrics for each group
    const groups = Object.values(groupsMap);
    groups.forEach(g => {
        g.holdings.forEach(h => {
            const cost = h.value_sgd - h.total_pl_sgd;
            const prevClose = h.value_sgd - h.daily_pl_sgd;
            
            g.value_sgd += h.value_sgd;
            g.total_pl_sgd += h.total_pl_sgd;
            g.daily_pl_sgd += h.daily_pl_sgd;
            g.cost_sgd += cost;
            g.prev_close_sgd += prevClose;
            g.allocation_pct += h.allocation_pct;
        });
        
        g.total_pl_pct = g.cost_sgd > 0 ? (g.total_pl_sgd / g.cost_sgd) * 100 : 0.0;
        g.daily_pl_pct = g.prev_close_sgd > 0 ? (g.daily_pl_sgd / g.prev_close_sgd) * 100 : 0.0;
    });
    
    // Sort groups based on sortColumn and sortDirection
    groups.sort((a, b) => {
        let valA, valB;
        if (sortColumn === "symbol") {
            valA = a.underlying || "";
            valB = b.underlying || "";
        } else if (sortColumn === "name") {
            valA = a.underlying || "";
            valB = b.underlying || "";
        } else if (sortColumn === "shares" || sortColumn === "avg_cost" || sortColumn === "price") {
            // Default groups sorting to value_sgd for properties that don't apply to the parent group level
            valA = a.value_sgd || 0;
            valB = b.value_sgd || 0;
        } else if (sortColumn === "value_sgd" || sortColumn === "allocation") {
            valA = a.value_sgd || 0;
            valB = b.value_sgd || 0;
        } else if (sortColumn === "total_pl_sgd") {
            valA = a.total_pl_sgd || 0;
            valB = b.total_pl_sgd || 0;
        } else if (sortColumn === "daily_pl_sgd") {
            valA = a.daily_pl_sgd || 0;
            valB = b.daily_pl_sgd || 0;
        } else {
            valA = a.value_sgd || 0;
            valB = b.value_sgd || 0;
        }
        
        if (typeof valA === "string") {
            return sortDirection === "asc" ? valA.localeCompare(valB) : valB.localeCompare(valA);
        } else {
            return sortDirection === "asc" ? valA - valB : valB - valA;
        }
    });
    
    // Sort child holdings within each group
    groups.forEach(g => {
        g.holdings.sort((a, b) => {
            let valA, valB;
            if (sortColumn === "symbol") {
                valA = a.symbol || "";
                valB = b.symbol || "";
            } else if (sortColumn === "name") {
                valA = a.name || "";
                valB = b.name || "";
            } else if (sortColumn === "shares") {
                valA = a.shares || 0;
                valB = b.shares || 0;
            } else if (sortColumn === "avg_cost") {
                valA = a.avg_cost_native || 0;
                valB = b.avg_cost_native || 0;
            } else if (sortColumn === "price") {
                valA = a.current_price_native || 0;
                valB = b.current_price_native || 0;
            } else if (sortColumn === "value_sgd") {
                valA = a.value_sgd || 0;
                valB = b.value_sgd || 0;
            } else if (sortColumn === "allocation") {
                valA = a.allocation_pct || 0;
                valB = b.allocation_pct || 0;
            } else if (sortColumn === "total_pl_sgd") {
                valA = a.total_pl_sgd || 0;
                valB = b.total_pl_sgd || 0;
            } else if (sortColumn === "daily_pl_sgd") {
                valA = a.daily_pl_sgd || 0;
                valB = b.daily_pl_sgd || 0;
            } else {
                valA = a.value_sgd || 0;
                valB = b.value_sgd || 0;
            }
            
            if (typeof valA === "string") {
                return sortDirection === "asc" ? valA.localeCompare(valB) : valB.localeCompare(valA);
            } else {
                return sortDirection === "asc" ? valA - valB : valB - valA;
            }
        });
    });
    
    if (dashboardViewMode === "table") {
        // Render groups and their children as table rows
        groups.forEach(g => {
            const isCollapsed = window.collapsedGroups[g.underlying] === true;
            const chevron = isCollapsed ? "▶" : "▼";
            
            // Group Header Row
            const trGroup = document.createElement("tr");
            trGroup.className = "group-header";
            trGroup.style.cursor = "pointer";
            
            const groupPlClass = g.total_pl_sgd >= 0 ? "text-gain" : "text-loss";
            const groupDailyClass = g.daily_pl_sgd >= 0 ? "text-gain" : "text-loss";
            
            const holdingsCountText = g.holdings.length === 1 ? "1 holding" : `${g.holdings.length} holdings`;
            
            trGroup.innerHTML = `
                <td style="font-weight: bold; color: var(--accent-primary, #8b5cf6);"><span class="group-chevron">${chevron}</span>${g.underlying}</td>
                <td style="color: var(--text-secondary); font-style: italic; font-size: 0.85rem;">(${holdingsCountText})</td>
                <td style="color: var(--text-muted);">-</td>
                <td style="color: var(--text-muted);">-</td>
                <td style="color: var(--text-muted);">-</td>
                <td style="font-weight: 600;">
                    <div>${formatCurrency(g.value_sgd)}</div>
                </td>
                <td style="font-weight: 600; text-align: right;">
                    ${g.allocation_pct.toFixed(2)}%
                </td>
                <td class="${groupPlClass}" style="font-weight: 600;">
                    <div>${formatCurrency(g.total_pl_sgd)}</div>
                    <div style="font-size: 0.8rem;">(${formatPercent(g.total_pl_pct)})</div>
                </td>
                <td class="${groupDailyClass}" style="font-weight: 600;">
                    <div>${formatCurrency(g.daily_pl_sgd)}</div>
                    <div style="font-size: 0.8rem;">(${formatPercent(g.daily_pl_pct)})</div>
                </td>
            `;
            
            // Toggle collapse on click
            trGroup.addEventListener("click", () => {
                window.collapsedGroups[g.underlying] = !isCollapsed;
                renderHoldingsTable(holdings);
            });
            
            tbody.appendChild(trGroup);
            
            // Render child holdings if not collapsed
            if (!isCollapsed) {
                g.holdings.forEach(h => {
                    const tr = document.createElement("tr");
                    tr.className = "child-row";
                    
                    const plPctClass = h.total_pl_sgd >= 0 ? "text-gain" : "text-loss";
                    const dailyClass = h.daily_pl_sgd >= 0 ? "text-gain" : "text-loss";
                    
                    tr.innerHTML = `
                        <td style="font-weight: 600; color: #38bdf8; padding-left: 2rem;">↳ ${h.symbol}</td>
                        <td>${h.name}</td>
                        <td>${h.shares}</td>
                        <td>${formatCurrency(h.avg_cost_native, h.currency)}</td>
                        <td>${formatCurrency(h.current_price_native, h.currency)}</td>
                        <td style="font-weight: 500;">
                            <div>${formatCurrency(h.value_native, h.currency)}</div>
                            <div style="font-size: 0.8rem; color: var(--text-secondary);">${formatCurrency(h.value_sgd)}</div>
                        </td>
                        <td style="font-weight: 500; text-align: right;">
                            ${h.allocation_pct.toFixed(2)}%
                        </td>
                        <td class="${plPctClass}" style="font-weight: 500;">
                            <div>${formatCurrency(h.total_pl_native, h.currency)}</div>
                            <div style="font-size: 0.8rem;">${formatCurrency(h.total_pl_sgd)} (${formatPercent(h.total_pl_pct)})</div>
                        </td>
                        <td class="${dailyClass}" style="font-weight: 500;">
                            <div>${formatCurrency(h.daily_pl_native, h.currency)}</div>
                            <div style="font-size: 0.8rem;">${formatCurrency(h.daily_pl_sgd)} (${formatPercent(h.daily_pl_pct)})</div>
                        </td>
                    `;
                    tbody.appendChild(tr);
                });
            }
        });
        
        updateSortHeaders();
    } else {
        // Render groups and their children as Cards (adapting active dashboard layout style outright)
        groups.forEach(g => {
            const isCollapsed = window.collapsedGroups[g.underlying] === true;
            const chevron = isCollapsed ? "▶" : "▼";
            
            const groupDiv = document.createElement("div");
            groupDiv.className = "underlying-group-card";
            groupDiv.style = "background: rgba(22, 28, 45, 0.4); border: 1px solid var(--card-border); border-radius: 12px; padding: 1.5rem; display: flex; flex-direction: column; gap: 1rem; transition: all 0.3s ease;";
            
            const groupPlClass = g.total_pl_sgd >= 0 ? "text-gain" : "text-loss";
            const groupDailyClass = g.daily_pl_sgd >= 0 ? "text-gain" : "text-loss";
            const holdingsCountText = g.holdings.length === 1 ? "1 holding" : `${g.holdings.length} holdings`;
            
            // Group header part
            const groupHeader = document.createElement("div");
            groupHeader.style = "display: flex; justify-content: space-between; align-items: center; border-bottom: 1px solid rgba(255, 255, 255, 0.06); padding-bottom: 0.75rem; cursor: pointer; user-select: none;";
            groupHeader.innerHTML = `
                <div>
                    <h3 style="font-family: var(--font-heading); font-size: 1.25rem; font-weight: 700; color: var(--accent-primary); margin: 0; display: flex; align-items: center; gap: 0.5rem;">
                        <span style="color: #38bdf8; font-size: 0.9rem;">${chevron}</span>${g.underlying}
                    </h3>
                    <span style="font-size: 0.8rem; color: var(--text-secondary); margin-left: 1.4rem;">(${holdingsCountText})</span>
                </div>
                <div style="text-align: right;">
                    <div style="font-size: 1.2rem; font-weight: 700; color: var(--text-primary);">${formatCurrency(g.value_sgd)}</div>
                    <div style="font-size: 0.8rem; color: var(--text-secondary);">Allocation: ${g.allocation_pct.toFixed(2)}%</div>
                </div>
            `;
            
            groupHeader.addEventListener("click", () => {
                window.collapsedGroups[g.underlying] = !isCollapsed;
                renderHoldingsTable(holdings);
            });
            
            groupDiv.appendChild(groupHeader);
            
            if (!isCollapsed) {
                // Summary KPI Grid inside the group (just like underlying_active.html)
                const statsGrid = document.createElement("div");
                statsGrid.style = "display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 1rem; background: rgba(0, 0, 0, 0.15); padding: 1rem; border-radius: 8px; margin-bottom: 0.5rem;";
                statsGrid.innerHTML = `
                    <div>
                        <span style="display: block; font-size: 0.7rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.25rem;">Total Invested</span>
                        <span style="font-size: 1.05rem; font-weight: 700; color: var(--text-primary);">${formatCurrency(g.cost_sgd)} SGD</span>
                    </div>
                    <div>
                        <span style="display: block; font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.25rem;">Current Value</span>
                        <span style="font-size: 1.05rem; font-weight: 700; color: var(--text-primary);">${formatCurrency(g.value_sgd)} SGD</span>
                    </div>
                    <div>
                        <span style="display: block; font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.25rem;">Total Profit</span>
                        <span style="font-size: 1.05rem; font-weight: 700;" class="${groupPlClass}">
                            ${formatCurrency(g.total_pl_sgd)} (${formatPercent(g.total_pl_pct)})
                        </span>
                    </div>
                    <div>
                        <span style="display: block; font-size: 0.75rem; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.05em; margin-bottom: 0.25rem;">Daily Change</span>
                        <span style="font-size: 1.05rem; font-weight: 700;" class="${groupDailyClass}">
                            ${formatCurrency(g.daily_pl_sgd)} (${formatPercent(g.daily_pl_pct)})
                        </span>
                    </div>
                `;
                groupDiv.appendChild(statsGrid);
                
                // Symbol cards list (symbol_card.html equivalent)
                const symbolGrid = document.createElement("div");
                symbolGrid.style = "display: grid; grid-template-columns: repeat(auto-fit, minmax(320px, 1fr)); gap: 1rem;";
                
                g.holdings.forEach(h => {
                    const hCard = document.createElement("div");
                    hCard.style = "background: rgba(255, 255, 255, 0.012); border: 1px solid rgba(255, 255, 255, 0.05); border-radius: 8px; padding: 1.25rem; display: flex; flex-direction: column; gap: 0.75rem; transition: border-color 0.2s;";
                    hCard.addEventListener("mouseenter", () => hCard.style.borderColor = "var(--accent-primary)");
                    hCard.addEventListener("mouseleave", () => hCard.style.borderColor = "rgba(255, 255, 255, 0.05)");
                    
                    const plPctClass = h.total_pl_sgd >= 0 ? "text-gain" : "text-loss";
                    const dailyClass = h.daily_pl_sgd >= 0 ? "text-gain" : "text-loss";
                    
                    hCard.innerHTML = `
                        <div style="display: flex; justify-content: space-between; align-items: flex-start; border-bottom: 1px solid rgba(255, 255, 255, 0.04); padding-bottom: 0.5rem;">
                            <div>
                                <span style="font-size: 1.2rem; font-weight: 700; color: #38bdf8;">${h.symbol}</span>
                                <span style="display: block; font-size: 0.8rem; color: var(--text-secondary); max-width: 190px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${h.name}">${h.name}</span>
                            </div>
                            <div style="text-align: right;">
                                <span style="font-size: 1.1rem; font-weight: 700; color: var(--text-primary);">${formatCurrency(h.value_sgd)}</span>
                                <span style="display: block; font-size: 0.75rem; color: var(--text-secondary);">${h.allocation_pct.toFixed(2)}% alloc</span>
                            </div>
                        </div>
                        
                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; font-size: 0.85rem;">
                            <div>
                                <span style="color: var(--text-muted); display: block; font-size: 0.7rem; text-transform: uppercase; margin-bottom: 0.15rem;">Position</span>
                                <strong style="color: var(--text-primary);">${h.shares}</strong>
                                <span style="display: block; color: var(--text-secondary); font-size: 0.75rem; margin-top: 0.1rem;">Avg Cost: ${formatCurrency(h.avg_cost_native, h.currency)}</span>
                            </div>
                            <div>
                                <span style="color: var(--text-muted); display: block; font-size: 0.7rem; text-transform: uppercase; margin-bottom: 0.15rem;">Current Price</span>
                                <strong style="color: var(--text-primary);">${formatCurrency(h.current_price_native, h.currency)}</strong>
                                <span style="display: block; color: var(--text-secondary); font-size: 0.75rem; margin-top: 0.1rem;">Val: ${formatCurrency(h.value_native, h.currency)}</span>
                            </div>
                        </div>

                        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0.75rem; font-size: 0.85rem; border-top: 1px solid rgba(255, 255, 255, 0.04); padding-top: 0.5rem; margin-top: 0.25rem;">
                            <div>
                                <span style="color: var(--text-muted); display: block; font-size: 0.7rem; text-transform: uppercase; margin-bottom: 0.15rem;">Total Profit</span>
                                <span class="${plPctClass}" style="font-weight: 700; font-size: 0.95rem;">${formatCurrency(h.total_pl_sgd)}</span>
                                <span class="${plPctClass}" style="display: block; font-size: 0.75rem;">(${formatPercent(h.total_pl_pct)})</span>
                            </div>
                            <div>
                                <span style="color: var(--text-muted); display: block; font-size: 0.7rem; text-transform: uppercase; margin-bottom: 0.15rem;">Daily Change</span>
                                <span class="${dailyClass}" style="font-weight: 700; font-size: 0.95rem;">${formatCurrency(h.daily_pl_sgd)}</span>
                                <span class="${dailyClass}" style="display: block; font-size: 0.75rem;">(${formatPercent(h.daily_pl_pct)})</span>
                            </div>
                        </div>
                    `;
                    symbolGrid.appendChild(hCard);
                });
                groupDiv.appendChild(symbolGrid);
            }
            cardsWrapper.appendChild(groupDiv);
        });
    }
}


function renderCharts(data) {
    // 1. Allocation Doughnut Chart
    const allocCtx = document.getElementById("allocation-chart").getContext("2d");
    if (allocationChart) {
        allocationChart.destroy();
    }
    
    const labels = data.holdings.map(h => h.symbol);
    const values = data.holdings.map(h => h.value_sgd);
    
    const colors = [
        '#6366f1', '#8b5cf6', '#38bdf8', '#10b981', '#f59e0b', 
        '#f43f5e', '#ec4899', '#14b8a6', '#06b6d4', '#84cc16'
    ];
    
    allocationChart = new Chart(allocCtx, {
        type: 'doughnut',
        data: {
            labels: labels,
            datasets: [{
                data: values,
                backgroundColor: colors.slice(0, labels.length),
                borderWidth: 0,
                hoverOffset: 4
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'right',
                    labels: {
                        color: '#94a3b8',
                        font: { family: 'Inter', size: 11 }
                    }
                }
            }
        }
    });
    
    // 2. Real bar chart representing dividends collected chronologically with secondary Yield on Cost line
    const divCtx = document.getElementById("dividend-chart").getContext("2d");
    if (dividendChart) {
        dividendChart.destroy();
    }
    
    const divLabels = Object.keys(data.monthly_dividends).map(monthKey => {
        const [year, month] = monthKey.split("-");
        const date = new Date(year, parseInt(month) - 1, 1);
        return date.toLocaleDateString('en-US', { month: 'short', year: '2-digit' });
    });
    const divValues = Object.values(data.monthly_dividends);
    const yieldValues = divValues.map(v => data.total_cost_sgd > 0 ? (v * 12 / data.total_cost_sgd) * 100 : 0.0);
    
    dividendChart = new Chart(divCtx, {
        data: {
            labels: divLabels,
            datasets: [
                {
                    type: 'bar',
                    label: 'Dividends (SGD)',
                    data: divValues,
                    backgroundColor: 'rgba(56, 189, 248, 0.45)',
                    borderColor: '#38bdf8',
                    borderWidth: 1.5,
                    borderRadius: 4,
                    yAxisID: 'y'
                },
                {
                    type: 'line',
                    label: 'Yield on Cost (%)',
                    data: yieldValues,
                    borderColor: '#10b981',
                    borderWidth: 2,
                    tension: 0.3,
                    yAxisID: 'y1',
                    fill: false
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    display: true,
                    position: 'top',
                    labels: {
                        color: '#94a3b8',
                        font: { family: 'Inter', size: 11 }
                    }
                }
            },
            scales: {
                y: {
                    type: 'linear',
                    display: true,
                    position: 'left',
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#64748b', font: { family: 'Inter', size: 10 } },
                    title: {
                        display: true,
                        text: 'Dividends (SGD)',
                        color: '#64748b',
                        font: { family: 'Inter', size: 10, weight: 'bold' }
                    }
                },
                y1: {
                    type: 'linear',
                    display: true,
                    position: 'right',
                    grid: { display: false },
                    ticks: {
                        color: '#10b981',
                        font: { family: 'Inter', size: 10 },
                        callback: function(value) { return value.toFixed(1) + '%'; }
                    },
                    title: {
                        display: true,
                        text: 'Yield on Cost (%)',
                        color: '#10b981',
                        font: { family: 'Inter', size: 10, weight: 'bold' }
                    }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#64748b', font: { family: 'Inter', size: 10 } }
                }
            }
        }
    });
}

// Refresh prices request triggers background fetch
const refreshBtn = document.getElementById("refresh-prices-btn");
if (refreshBtn) {
    refreshBtn.addEventListener("click", async () => {
        try {
            refreshBtn.disabled = true;
            refreshBtn.textContent = "Requesting refresh...";
            
            const res = await fetch("/api/prices/refresh", { method: "POST" });
            const data = await res.json();
            
            if (res.ok) {
                showToast("Price updates triggered in background! Refreshing table shortly...");
                // Polling refresh dashboard in 4 seconds
                setTimeout(() => {
                    loadDashboard();
                    refreshBtn.disabled = false;
                    refreshBtn.textContent = "Refresh Prices";
                }, 4000);
            } else {
                showToast(data.detail || "Refresh rejected.", "error");
                refreshBtn.disabled = false;
                refreshBtn.textContent = "Refresh Prices";
            }
        } catch (e) {
            showToast("Error updating prices: " + e.message, "error");
            refreshBtn.disabled = false;
            refreshBtn.textContent = "Refresh Prices";
        }
    });
}

/* 4. Trades/Transactions View Log */
async function loadTransactions(keepFilter = false) {
    try {
        const url = selectedPortfolioId !== null
            ? `/api/transactions?portfolio_id=${selectedPortfolioId}`
            : "/api/transactions";
            
        const res = await fetch(url);
        const data = await res.json();
        
        cachedTransactions = data;
        
        const searchInput = document.getElementById("transaction-search-input");
        if (searchInput && !keepFilter) {
            searchInput.value = "";
        }
        
        if (!keepFilter) {
            currentTradesPage = 1;
        }
        
        const query = (searchInput && keepFilter) ? searchInput.value.trim().toLowerCase() : "";
        if (query) {
            const filtered = data.filter(t => 
                t.symbol.toLowerCase().includes(query) ||
                t.action.toLowerCase().includes(query) ||
                t.portfolio_name.toLowerCase().includes(query) ||
                (t.notes && t.notes.toLowerCase().includes(query)) ||
                t.date.includes(query)
            );
            renderTransactionsTable(filtered);
        } else {
            renderTransactionsTable(data);
        }
    } catch (e) {
        showToast("Error loading transactions: " + e.message, "error");
    }
}

function renderTransactionsTable(data) {
    const tbody = document.getElementById("transactions-table-body");
    tbody.innerHTML = "";
    
    updatePaginationControls(".pagination-trades", currentTradesPage, data.length, (newPage) => {
        currentTradesPage = newPage;
        renderTransactionsTable(data);
    });
    
    if (data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="12" style="text-align: center; color: var(--text-muted); padding: 2rem;">No transactions recorded. Click + Add Transaction to record your first trade.</td></tr>`;
        return;
    }
    
    const start = (currentTradesPage - 1) * PAGE_SIZE;
    const paginatedData = data.slice(start, start + PAGE_SIZE);
    
    paginatedData.forEach(t => {
        const tr = document.createElement("tr");
        const actionClass = t.action === "BUY" ? "text-gain" : (t.action === "SELL" ? "text-loss" : "text-muted");
        
        tr.innerHTML = `
            <td style="color: var(--text-secondary);">${t.date}</td>
            <td style="font-weight: 600; color: #38bdf8;">${t.symbol}</td>
            <td class="${actionClass}" style="font-weight: 700;">${t.action}</td>
            <td>${formatCurrency(t.price, t.currency)}</td>
            <td>${t.quantity}</td>
            <td>${t.currency}</td>
            <td>${formatCurrency(t.commission, t.currency)}</td>
            <td>${t.cost_basis_after ? formatCurrency(t.cost_basis_after, t.currency) : "-"}</td>
            <td class="${t.realized_pl >= 0 ? "text-gain" : "text-loss"}" style="font-weight: 500;">
                ${t.realized_pl ? formatCurrency(t.realized_pl, t.currency) : "-"}
            </td>
            <td style="color: var(--text-secondary); font-size: 0.85rem;">${t.portfolio_name}</td>
            <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-muted);">${t.notes || ""}</td>
            <td>
                <button class="btn btn-secondary" style="padding: 0.25rem 0.5rem; font-size: 0.75rem;" onclick="editTransaction(${JSON.stringify(t).replace(/"/g, '&quot;')})">Edit</button>
                <button class="btn btn-danger" style="padding: 0.25rem 0.5rem; font-size: 0.75rem;" onclick="deleteTransaction(this, ${t.id})">Delete</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

window.editTransaction = function(t) {
    if (t.action === "FEE") {
        openTransactionModal("expenses", t);
    } else {
        openTransactionModal("trades", t);
    }
};

window.deleteTransaction = async function(btnOrId, possibleId) {
    let id = possibleId;
    let btn = null;
    if (typeof btnOrId === "number" || typeof btnOrId === "string") {
        id = btnOrId;
    } else {
        btn = btnOrId;
    }
    
    if (confirm("Are you sure you want to delete this transaction? Cost basis will be re-calculated.")) {
        let originalText = "";
        if (btn) {
            btn.disabled = true;
            originalText = btn.innerHTML;
            btn.innerHTML = "Deleting...";
        }
        try {
            const res = await fetch(`/api/transactions/${id}`, { method: "DELETE" });
            if (res.ok) {
                showToast("Transaction deleted successfully.");
                currentModalPortfolioId = null; // Clear cached holdings
                loadTransactions(true);
            }
        } catch (e) {
            showToast("Delete failed: " + e.message, "error");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }
    }
};

/* 5. Dividends Log View */
async function loadDividends(keepFilter = false) {
    try {
        const url = selectedPortfolioId !== null
            ? `/api/dividends?portfolio_id=${selectedPortfolioId}`
            : "/api/dividends";
            
        const res = await fetch(url);
        const data = await res.json();
        
        cachedDividends = data;
        
        const searchInput = document.getElementById("dividend-search-input");
        if (searchInput && !keepFilter) {
            searchInput.value = "";
        }
        
        if (!keepFilter) {
            currentDividendsPage = 1;
        }
        
        const query = (searchInput && keepFilter) ? searchInput.value.trim().toLowerCase() : "";
        if (query) {
            const filtered = data.filter(d => 
                d.symbol.toLowerCase().includes(query) ||
                d.portfolio_name.toLowerCase().includes(query) ||
                (d.notes && d.notes.toLowerCase().includes(query)) ||
                d.date.includes(query)
            );
            renderDividendsTable(filtered);
        } else {
            renderDividendsTable(data);
        }
    } catch (e) {
        showToast("Error loading dividends: " + e.message, "error");
    }
}

function renderDividendsTable(data) {
    const tbody = document.getElementById("dividends-table-body");
    tbody.innerHTML = "";
    
    updatePaginationControls(".pagination-dividends", currentDividendsPage, data.length, (newPage) => {
        currentDividendsPage = newPage;
        renderDividendsTable(data);
    });
    
    if (data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="11" style="text-align: center; color: var(--text-muted); padding: 2rem;">No dividends received. Click + Record Dividend to log cash flows.</td></tr>`;
        return;
    }
    
    const start = (currentDividendsPage - 1) * PAGE_SIZE;
    const paginatedData = data.slice(start, start + PAGE_SIZE);
    
    paginatedData.forEach(d => {
        const tr = document.createElement("tr");
        const netReceived = d.amount - d.tax;
        
        const qtyStr = d.qty ? Number(d.qty).toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 4 }) : "-";
        const netPerShareStr = d.qty ? (d.currency === "USD" ? "USD " : (d.currency === "CAD" ? "CAD " : "S$")) + Number(netReceived / d.qty).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 4 }) : "-";
        
        tr.innerHTML = `
            <td style="color: var(--text-secondary);">${d.date}</td>
            <td style="font-weight: 600; color: #38bdf8;">${d.symbol}</td>
            <td>${qtyStr}</td>
            <td style="font-weight: 500;">${formatCurrency(d.amount, d.currency)}</td>
            <td>${d.currency}</td>
            <td style="color: var(--color-loss);">${formatCurrency(d.tax, d.currency)}</td>
            <td class="text-gain" style="font-weight: 600;">${formatCurrency(netReceived, d.currency)}</td>
            <td>${netPerShareStr}</td>
            <td style="color: var(--text-secondary); font-size: 0.85rem;">${d.portfolio_name}</td>
            <td style="max-width: 150px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--text-muted);">${d.notes || ""}</td>
            <td>
                <button class="btn btn-secondary" style="padding: 0.25rem 0.5rem; font-size: 0.75rem;" onclick="editDividend(${JSON.stringify(d).replace(/"/g, '&quot;')})">Edit</button>
                <button class="btn btn-danger" style="padding: 0.25rem 0.5rem; font-size: 0.75rem;" onclick="deleteDividend(this, ${d.id})">Delete</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

window.editDividend = function(d) {
    openTransactionModal("incomes", d);
};

window.deleteDividend = async function(btnOrId, possibleId) {
    let id = possibleId;
    let btn = null;
    if (typeof btnOrId === "number" || typeof btnOrId === "string") {
        id = btnOrId;
    } else {
        btn = btnOrId;
    }
    
    if (confirm("Are you sure you want to delete this dividend entry?")) {
        let originalText = "";
        if (btn) {
            btn.disabled = true;
            originalText = btn.innerHTML;
            btn.innerHTML = "Deleting...";
        }
        try {
            const res = await fetch(`/api/dividends/${id}`, { method: "DELETE" });
            if (res.ok) {
                showToast("Dividend entry deleted.");
                currentModalPortfolioId = null; // Clear cached holdings
                loadDividends(true);
            }
        } catch (e) {
            showToast("Delete failed: " + e.message, "error");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }
    }
};

/* 6. Tickers settings view */
async function loadTickers() {
    try {
        const res = await fetch("/api/tickers");
        cachedTickers = await res.json();
        currentTickersPage = 1;
        renderTickersTable(cachedTickers);
        populateUnderlyingDatalist(cachedTickers);
    } catch (e) {
        showToast("Error loading tickers: " + e.message, "error");
    }
}

function populateUnderlyingDatalist(tickers) {
    const underlyings = new Set();
    tickers.forEach(t => {
        if (t.underlying && t.underlying.trim() && t.shares > 0.0001) {
            underlyings.add(t.underlying.trim());
        }
    });
    cachedUnderlyingAssets = Array.from(underlyings).sort();
    renderUnderlyingDatalist("");
}

function renderUnderlyingDatalist(query) {
    const datalist = document.getElementById("underlying-assets-list");
    if (!datalist) return;
    datalist.innerHTML = "";
    
    const normalizedQuery = (query || "").trim().toLowerCase();
    const matches = cachedUnderlyingAssets.filter(val => 
        val.toLowerCase().includes(normalizedQuery)
    );
    
    // Sort alphabetically and add options (max 10 matches)
    matches.slice(0, 10).forEach(val => {
        const option = document.createElement("option");
        option.value = val;
        datalist.appendChild(option);
    });
}

function renderTickersTable(tickers) {
    const tbody = document.getElementById("tickers-table-body");
    if (!tbody) return;
    tbody.innerHTML = "";
    
    const activeToggle = document.getElementById("ticker-active-toggle");
    const activeOnly = activeToggle ? activeToggle.checked : false;
    
    const filtered = tickers.filter(t => {
        if (activeOnly && !(t.shares > 0.0001)) {
            return false;
        }
        return true;
    });
    
    updatePaginationControls(".pagination-tickers", currentTickersPage, filtered.length, (newPage) => {
        currentTickersPage = newPage;
        renderTickersTable(tickers);
    });
    
    const start = (currentTickersPage - 1) * PAGE_SIZE;
    const paginated = filtered.slice(start, start + PAGE_SIZE);
    
    paginated.forEach(t => {
        const tr = document.createElement("tr");
        const deleteBtn = (!(t.shares > 0.0001))
            ? ` <button class="btn btn-danger" style="padding: 0.25rem 0.5rem; font-size: 0.75rem; margin-left: 0.25rem;" onclick="deleteTicker(this, ${t.id})">Delete</button>`
            : '';
        tr.innerHTML = `
            <td style="font-weight: 600; color: #38bdf8;">${t.symbol}</td>
            <td style="font-weight: 500;">${t.friendly_name || t.symbol}</td>
            <td style="color: var(--text-secondary); font-size: 0.9rem;">${t.underlying || ""}</td>
            <td>${(t.tax_rate * 100).toFixed(0)}%</td>
            <td style="color: var(--text-secondary); font-size: 0.85rem;">${t.exchange || "US"}</td>
            <td style="color: var(--text-secondary); font-size: 0.85rem;">${t.category || t.subclass || "Other"}</td>
            <td style="color: var(--text-muted);">${t.notes || ""}</td>
            <td>
                <button class="btn btn-secondary" style="padding: 0.25rem 0.5rem; font-size: 0.75rem;" onclick="editTicker(${JSON.stringify(t).replace(/"/g, '&quot;')})">Edit</button>
                ${deleteBtn}
            </td>
        `;
        tbody.appendChild(tr);
    });
}

window.editTicker = function(t) {
    document.getElementById("ticker-id").value = t.id;
    document.getElementById("ticker-symbol").value = t.symbol;
    document.getElementById("ticker-name").value = t.friendly_name || t.symbol;
    document.getElementById("ticker-underlying").value = t.underlying || "";
    document.getElementById("ticker-tax").value = t.tax_rate;
    document.getElementById("ticker-category").value = t.category || t.subclass || "Other";
    document.getElementById("ticker-notes").value = t.notes || "";
    document.getElementById("ticker-exchange").value = t.exchange || "US";
    
    openModal("ticker-modal");
};

window.deleteTicker = async function(btnOrId, possibleId) {
    let id = possibleId;
    let btn = null;
    if (typeof btnOrId === "number" || typeof btnOrId === "string") {
        id = btnOrId;
    } else {
        btn = btnOrId;
    }
    
    if (!confirm("Are you sure you want to delete this ticker?")) return;
    
    let originalText = "";
    if (btn) {
        btn.disabled = true;
        originalText = btn.innerHTML;
        btn.innerHTML = "Deleting...";
    }
    
    try {
        const res = await fetch(`/api/tickers/${id}`, { method: "DELETE" });
        if (res.ok) {
            showToast("Ticker deleted.");
            await loadTickers();
        } else {
            const err = await res.json();
            showToast("Failed to delete: " + err.detail, "error");
        }
    } catch (e) {
        showToast("Error: " + e.message, "error");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = originalText;
        }
    }
};

async function loadTickersList() {
    try {
        const res = await fetch("/api/tickers");
        tickersList = await res.json();
    } catch (e) {}
}

function loadImportWizard() {
    const select = document.getElementById("import-portfolio-select");
    if (select) {
        select.innerHTML = '<option value="">-- Create Portfolio Name below --</option>' + 
            portfoliosList.map(p => `<option value="${p.name}">${p.name}</option>`).join("");
    }

    const ibkrSelect = document.getElementById("ibkr-import-portfolio");
    if (ibkrSelect) {
        ibkrSelect.innerHTML = portfoliosList.map(p => `<option value="${p.name}">${p.name}</option>`).join("");
        const incFactory = portfoliosList.find(p => p.name.toLowerCase() === "income factory");
        if (incFactory) {
            ibkrSelect.value = incFactory.name;
        } else if (portfoliosList.length > 0) {
            ibkrSelect.value = portfoliosList[0].name;
        }
    }
}

function setupAutocomplete() {
    bindAutocomplete("tx-ticker", "tx-ticker-suggestions");
    bindAutocomplete("div-ticker", "div-ticker-suggestions");
    
    const underlyingInput = document.getElementById("ticker-underlying");
    if (underlyingInput) {
        underlyingInput.addEventListener("input", (e) => {
            renderUnderlyingDatalist(e.target.value);
        });
    }
}

function bindAutocomplete(inputId, suggestionBoxId) {
    const input = document.getElementById(inputId);
    const box = document.getElementById(suggestionBoxId);
    if (!input || !box) return;
    
    input.addEventListener("input", () => {
        const query = input.value.trim().toUpperCase();
        
        checkExistingTicker(input.value, inputId);
        
        box.innerHTML = "";
        
        if (!query) {
            box.classList.remove("show");
            return;
        }
        
        const matches = tickersList.filter(t => 
            t.symbol.toUpperCase().includes(query) || 
            (t.friendly_name && t.friendly_name.toUpperCase().includes(query)) ||
            (t.notes && t.notes.toUpperCase().includes(query))
        );
        
        if (matches.length === 0) {
            box.classList.remove("show");
            return;
        }
        
        matches.slice(0, 5).forEach(m => {
            const div = document.createElement("div");
            div.className = "suggestion-item";
            
            let label = `${m.friendly_name || m.symbol}`;
            if (m.notes && m.notes.toUpperCase().includes(query)) {
                label += ` (${m.notes.substring(0, 20)}...)`;
            }
            
            div.innerHTML = `<strong>${m.symbol}</strong> - <span style="font-size:0.8rem; color: var(--text-secondary);">${label}</span>`;
            div.addEventListener("click", () => {
                input.value = m.symbol;
                box.classList.remove("show");
                
                checkExistingTicker(m.symbol, inputId);
                if (inputId === "tx-ticker") {
                    updateTradeModalCalculations();
                }
            });
            box.appendChild(div);
        });
        
        box.classList.add("show");
    });
    
    document.addEventListener("click", (e) => {
        if (e.target !== input) {
            box.classList.remove("show");
        }
    });
}

function setupFormSubmissions() {
    const addTxBtn = document.getElementById("add-transaction-btn");
    if (addTxBtn) {
        addTxBtn.addEventListener("click", () => {
            openTransactionModal("trades");
        });
    }
    
    const addDivBtn = document.getElementById("add-dividend-btn");
    if (addDivBtn) {
        addDivBtn.addEventListener("click", () => {
            openTransactionModal("incomes");
        });
    }

    const tickerForm = document.getElementById("ticker-form");
    if (tickerForm) {
        tickerForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const id = document.getElementById("ticker-id").value;
            const payload = {
                friendly_name: document.getElementById("ticker-name").value,
                underlying: document.getElementById("ticker-underlying").value,
                tax_rate: parseFloat(document.getElementById("ticker-tax").value),
                category: document.getElementById("ticker-category").value,
                subclass: document.getElementById("ticker-category").value,
                notes: document.getElementById("ticker-notes").value,
                exchange: document.getElementById("ticker-exchange").value
            };
            
            try {
                const res = await fetch(`/api/tickers/${id}`, {
                    method: "PUT",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                
                if (res.ok) {
                    showToast("Ticker settings updated.");
                    closeModal("ticker-modal");
                    loadTickers();
                }
            } catch (err) {
                showToast("Update failed: " + err.message, "error");
            }
        });
    }
    
    const portAddForm = document.getElementById("portfolio-add-form");
    if (portAddForm) {
        portAddForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const name = document.getElementById("new-portfolio-name").value;
            const classification = document.getElementById("new-portfolio-classification").value;
            const broker = document.getElementById("new-portfolio-broker").value;
            try {
                const res = await fetch("/api/portfolios", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ name: name, classification: classification, broker: broker })
                });
                if (res.ok) {
                    showToast("Portfolio created.");
                    closeModal("portfolio-add-modal");
                    await loadPortfolios();
                }
            } catch (err) {
                showToast("Create failed: " + err.message, "error");
            }
        });
    }
    
    const importForm = document.getElementById("import-form");
    if (importForm) {
        importForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        
        const dropdownName = document.getElementById("import-portfolio-select").value;
        const inputName = document.getElementById("import-new-portfolio-name").value.trim();
        const targetPortfolio = inputName || dropdownName;
        
        if (!targetPortfolio) {
            showToast("Please specify a target portfolio name.", "error");
            return;
        }
        
        const holdingsFile = document.getElementById("import-holdings-file").files[0];
        const transactionsFile = document.getElementById("import-transactions-file").files[0];
        
        const formData = new FormData();
        formData.append("portfolio_name", targetPortfolio);
        formData.append("holdings_file", holdingsFile);
        formData.append("transactions_file", transactionsFile);
        
        try {
            showToast("Starting import... This may take a moment while fetching yfinance data.");
            const res = await fetch("/api/import", {
                method: "POST",
                body: formData
            });
            
            const data = await res.json();
            if (res.ok) {
                showToast(data.message);
                document.getElementById("import-form").reset();
                await loadPortfolios();
                await loadTickersList();
                
                const found = portfoliosList.find(p => p.name.toLowerCase() === targetPortfolio.toLowerCase());
                if (found) {
                    selectPortfolio(found.id, found.name);
                } else {
                    selectPortfolio(null, "My Net Worth");
                }
                switchView("nav-transactions", "section-transactions");
            } else {
                showToast("Import error: " + data.detail, "error");
            }
        } catch (err) {
            showToast("Import upload failed: " + err.message, "error");
        }
    });
    }

    // Import sub-tabs switching logic
    const btnIbkr = document.getElementById("btn-import-tab-ibkr");
    const btnSnowball = document.getElementById("btn-import-tab-snowball");
    const btnCapital = document.getElementById("btn-import-tab-capital");
    
    const tabIbkr = document.getElementById("import-tab-ibkr-content");
    const tabSnowball = document.getElementById("import-tab-snowball-content");
    const tabCapital = document.getElementById("import-tab-capital-content");

    if (btnIbkr && btnSnowball && btnCapital) {
        const tabs = [
            { btn: btnIbkr, tab: tabIbkr },
            { btn: btnSnowball, tab: tabSnowball },
            { btn: btnCapital, tab: tabCapital }
        ];
        
        tabs.forEach(t => {
            t.btn.addEventListener("click", () => {
                tabs.forEach(x => {
                    x.btn.classList.remove("active");
                    x.tab.style.display = "none";
                });
                t.btn.classList.add("active");
                t.tab.style.display = "block";
            });
        });
    }

    // Base Capital CSV Upload Form wiring
    const capitalUploadForm = document.getElementById("capital-upload-form");
    if (capitalUploadForm) {
        capitalUploadForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const fileInput = document.getElementById("capital-upload-file");
            if (!fileInput.files || fileInput.files.length === 0) return;
            
            const formData = new FormData();
            formData.append("file", fileInput.files[0]);
            
            try {
                showToast("Importing Capital CSV...");
                const res = await fetch("/api/settings/capital/import", {
                    method: "POST",
                    body: formData
                });
                const json = await res.json();
                if (res.ok) {
                    showToast("Base Capital CSV processed and imported successfully!");
                    capitalUploadForm.reset();
                } else {
                    showToast("Import failed: " + (json.detail || "Error"), "error");
                }
            } catch (err) {
                showToast("Upload failed: " + err.message, "error");
            }
        });
    }

    // Daily Cash Metrics Form wiring
    const cashMetricsForm = document.getElementById("cash-metrics-form");
    if (cashMetricsForm) {
        cashMetricsForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const date = document.getElementById("cash-metrics-date").value;
            const broker = document.getElementById("cash-metrics-broker").value;
            const liqVal = parseFloat(document.getElementById("cash-metrics-liq").value);
            const stockVal = parseFloat(document.getElementById("cash-metrics-stock").value);
            const cashVal = parseFloat(document.getElementById("cash-metrics-cash").value);
            
            try {
                showToast("Saving daily cash metrics...");
                const res = await fetch("/api/settings/cash-metrics", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({
                        date: date,
                        broker: broker,
                        liquidation_value: liqVal,
                        total_stock_value: stockVal,
                        cash_on_hand: cashVal
                    })
                });
                
                if (res.ok) {
                    showToast(`${broker} metrics recorded successfully!`);
                    closeModal("cash-metrics-modal");
                    loadDailyCashHistory();
                } else {
                    const json = await res.json();
                    showToast("Failed to save metrics: " + (json.detail || "Error"), "error");
                }
            } catch (err) {
                showToast("Failed to save metrics: " + err.message, "error");
            }
        });
    }

    // Helper to open daily cash metrics modal and pre-populate fields
    window.openCashMetricsModal = async function(broker) {
        const title = broker === 'MOOMOO' ? '🐮 Record MooMoo Daily Cash Metrics' : '🦅 Record IBKR Daily Cash Metrics';
        document.getElementById("cash-metrics-modal-title").innerText = title;
        document.getElementById("cash-metrics-broker").value = broker;
        
        // Set date to today (SGT / local time)
        const today = new Date().toISOString().split('T')[0];
        document.getElementById("cash-metrics-date").value = today;
        
        // Clear inputs initially while loading
        document.getElementById("cash-metrics-liq").value = "";
        document.getElementById("cash-metrics-stock").value = "";
        document.getElementById("cash-metrics-cash").value = "";
        
        try {
            showToast(`Loading last ${broker} metrics...`);
            const res = await fetch(`/api/settings/cash-metrics/last?broker=${broker}`);
            if (res.ok) {
                const data = await res.json();
                if (data && data.date) {
                    document.getElementById("cash-metrics-liq").value = data.liquidation_value !== undefined ? data.liquidation_value : "";
                    document.getElementById("cash-metrics-stock").value = data.total_stock_value !== undefined ? data.total_stock_value : "";
                    document.getElementById("cash-metrics-cash").value = data.cash_on_hand !== undefined ? data.cash_on_hand : "";
                    showToast(`Loaded last metrics from ${data.date}.`);
                } else {
                    showToast("No previous metrics found for this broker.");
                }
            }
        } catch (e) {
            console.error("Failed to load last cash metrics", e);
            showToast("Failed to load last metrics", "error");
        }
        
        openModal("cash-metrics-modal");
    }

    // Base Capital Injections Quick Add Form wiring
    window.openCapitalAddModal = function() {
        const form = document.getElementById("capital-add-form");
        if (form) form.reset();
        
        // Set date to today
        const dateInput = document.getElementById("cap-add-date");
        if (dateInput) {
            const today = new Date().toISOString().split('T')[0];
            dateInput.value = today;
        }
        
        openModal("capital-add-modal");
    };

    const capitalAddForm = document.getElementById("capital-add-form");
    if (capitalAddForm) {
        capitalAddForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const date = document.getElementById("cap-add-date").value;
            const broker = document.getElementById("cap-add-broker").value;
            const amount = parseFloat(document.getElementById("cap-add-amount").value);
            const remarks = document.getElementById("cap-add-remarks").value;
            
            try {
                showToast("Adding capital entry...");
                const res = await fetch("/api/settings/capital", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ date, broker, amount, remarks })
                });
                if (res.ok) {
                    showToast("Capital entry added successfully.");
                    capitalAddForm.reset();
                    closeModal("capital-add-modal");
                    await loadCapitalEntries();
                } else {
                    const json = await res.json();
                    showToast("Failed to add entry: " + (json.detail || "Error"), "error");
                }
            } catch (err) {
                showToast("Error adding capital entry: " + err.message, "error");
            }
        });
    }

    // IBKR XML Import form wiring
    const ibkrForm = document.getElementById("ibkr-import-form");
    if (ibkrForm) {
        ibkrForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const fileInput = document.getElementById("ibkr-import-file");
            if (!fileInput.files || fileInput.files.length === 0) {
                showToast("Please select a dividend-ytd.xml file.", "error");
                return;
            }
            const file = fileInput.files[0];
            const startDate = document.getElementById("ibkr-import-start-date").value;
            const endDate = document.getElementById("ibkr-import-end-date").value;
            const portfolio = document.getElementById("ibkr-import-portfolio").value;

            const importData = new FormData();
            importData.append("file", file);

            try {
                showToast("Importing dividends... please wait.");
                const importRes = await fetch(`/api/dividends/import-ibkr?start_date=${startDate}&end_date=${endDate}&portfolio=${encodeURIComponent(portfolio)}`, {
                    method: "POST",
                    body: importData
                });
                const importJson = await importRes.json();
                if (importRes.ok) {
                    const msg = `Import complete: ${importJson.inserted} inserted, ${importJson.updated} updated, ${importJson.skipped} skipped.`;
                    showToast(msg, "success");
                    ibkrForm.reset();
                    await loadPortfolios();
                    const activeP = portfoliosList.find(p => p.name === portfolio) || portfoliosList[0];
                    if (activeP) {
                        selectPortfolio(activeP.id, activeP.name);
                    }
                    switchView("nav-dividends", "section-dividends");
                } else {
                    showToast("Import error: " + (importJson.detail || "Unknown error"), "error");
                }
            } catch (err) {
                showToast("Request failed: " + err.message, "error");
            }
        });
    }

    // Add exchange/currency dynamic link listener
    const txCurrency = document.getElementById("tx-currency");
    if (txCurrency) {
        txCurrency.addEventListener("change", () => {
            const txExchange = document.getElementById("tx-exchange");
            if (txExchange && !txExchange.disabled) {
                const curr = txCurrency.value;
                if (curr === "CAD") {
                    txExchange.value = "TO";
                } else if (curr === "SGD") {
                    txExchange.value = "SG";
                } else {
                    txExchange.value = "US";
                }
                updateQuantityStepAndMin();
            }
        });
    }

    const txExchange = document.getElementById("tx-exchange");
    if (txExchange) {
        txExchange.addEventListener("change", updateQuantityStepAndMin);
    }

    // Settings form submission wiring
    const settingsForm = document.getElementById("settings-form");
    if (settingsForm) {
        settingsForm.addEventListener("submit", async (e) => {
            e.preventDefault();
            const priorityStr = document.getElementById("settings-classification-priority").value;
            const priority = priorityStr.split(",").map(s => s.trim()).filter(s => s.length > 0);
            const optionsUrl = document.getElementById("settings-options-tracker-url").value.trim();
            const backtesterUrl = document.getElementById("settings-backtester-url").value.trim();
            const metricsRunHourVal = parseInt(document.getElementById("settings-metrics-run-hour").value.trim());
            const metricsRunHour = isNaN(metricsRunHourVal) ? 6 : metricsRunHourVal;
            
            const payload = {
                "sorting.classification_priority": priority,
                "external_services.options_tracker_url": optionsUrl,
                "external_services.backtester_url": backtesterUrl,
                "cron.metrics_run_hour": metricsRunHour
            };
            
            const saveBtn = document.getElementById("settings-save-btn");
            if (saveBtn) {
                saveBtn.disabled = true;
                saveBtn.textContent = "Saving...";
            }
            
            try {
                const res = await fetch("/api/settings", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify(payload)
                });
                
                if (res.ok) {
                    showToast("Settings updated successfully.");
                } else {
                    const errData = await res.json();
                    showToast("Failed to save settings: " + (errData.detail || "Unknown error"), "error");
                }
            } catch (err) {
                showToast("Request failed: " + err.message, "error");
            } finally {
                if (saveBtn) {
                    saveBtn.disabled = false;
                    saveBtn.textContent = "Save settings";
                }
            }
        });
    }
}

async function loadSettingsEditor() {
    try {
        const res = await fetch("/api/settings");
        if (res.ok) {
            const settings = await res.json();
            
            // Classification priority
            const priorityList = (settings.sorting && settings.sorting.classification_priority) || [];
            document.getElementById("settings-classification-priority").value = priorityList.join(", ");
            
            // Options tracker URL
            const optionsUrl = (settings.external_services && settings.external_services.options_tracker_url) || "";
            document.getElementById("settings-options-tracker-url").value = optionsUrl;
            
            // Backtester URL
            const backtesterUrl = (settings.external_services && settings.external_services.backtester_url) || "";
            document.getElementById("settings-backtester-url").value = backtesterUrl;
            
            // Metrics Run Hour
            const metricsRunHour = (settings.cron && settings.cron.metrics_run_hour !== undefined) ? settings.cron.metrics_run_hour : 6;
            document.getElementById("settings-metrics-run-hour").value = metricsRunHour;
        } else {
            showToast("Failed to load settings.", "error");
        }
        
        // Fetch and load capital entries
        await loadCapitalEntries();
        
    } catch (err) {
        showToast("Error loading settings: " + err.message, "error");
    }
}

async function loadDailyCashHistory() {
    try {
        const res = await fetch("/api/settings/cash-metrics/history");
        if (res.ok) {
            cachedDailyCashHistory = await res.json();
            currentDailyCashPage = 1;
            renderDailyCashHistoryTable(cachedDailyCashHistory);
        }
    } catch (err) {
        const tbody = document.getElementById("daily-cash-history-body");
        if (tbody) {
            tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-negative);">Error: ${err.message}</td></tr>`;
        }
    }
}

function renderDailyCashHistoryTable(data) {
    const tbody = document.getElementById("daily-cash-history-body");
    if (!tbody) return;
    tbody.innerHTML = "";
    
    updatePaginationControls(".pagination-dailycash", currentDailyCashPage, data.length, (newPage) => {
        currentDailyCashPage = newPage;
        renderDailyCashHistoryTable(data);
    });
    
    if (data.length === 0) {
        tbody.innerHTML = `<tr><td colspan="6" style="text-align: center; color: var(--text-secondary);">No records found.</td></tr>`;
        return;
    }
    
    const start = (currentDailyCashPage - 1) * PAGE_SIZE;
    const paginated = data.slice(start, start + PAGE_SIZE);
    
    tbody.innerHTML = paginated.map(r => {
        const formattedLiq = (r.liquidation_value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        const formattedCap = (r.base_capital || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        const formattedStock = (r.total_stock_value || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        const formattedCash = (r.cash_on_hand || 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        
        return `
            <tr>
                <td>${r.date}</td>
                <td>${r.broker}</td>
                <td>${formattedLiq} SGD</td>
                <td>${formattedCap} SGD</td>
                <td>${formattedStock} SGD</td>
                <td>${formattedCash} SGD</td>
            </tr>
        `;
    }).join("");
}
async function triggerIbkrAutoIngest() {
    const btn = document.getElementById("btn-ibkr-auto-ingest");
    if (btn) {
        btn.disabled = true;
        btn.innerHTML = `<span>⏳</span> Ingesting...`;
    }
    try {
        const res = await fetch("/api/settings/cash-metrics/ingest-file?rebuild=true", {
            method: "POST"
        });
        const data = await res.json();
        if (res.ok) {
            showToast("IBKR Cash metrics successfully updated from file.", "success");
            await loadDailyCashHistory();
        } else {
            showToast("Failed to auto ingest cash metrics: " + (data.detail || res.statusText), "error");
        }
    } catch (err) {
        showToast("Error during auto ingestion: " + err.message, "error");
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.innerHTML = `<span>⚡</span> Auto Update IBKR from File`;
        }
    }
}


async function loadCapitalEntries() {
    try {
        const res = await fetch("/api/settings/capital");
        if (res.ok) {
            cachedCapitalEntries = await res.json();
            currentCapitalPage = 1;
            renderCapitalTable(cachedCapitalEntries);
        }
    } catch (e) {
        console.error("Failed to load capital entries", e);
    }
}

function renderCapitalTable(entries) {
    const tbody = document.getElementById("capital-entries-tbody");
    if (!tbody) return;
    tbody.innerHTML = "";
    
    updatePaginationControls(".pagination-capital", currentCapitalPage, entries.length, (newPage) => {
        currentCapitalPage = newPage;
        renderCapitalTable(entries);
    });
    
    if (entries.length === 0) {
        tbody.innerHTML = `<tr><td colspan="5" style="text-align: center; color: var(--text-muted); padding: 2rem;">No capital entries recorded.</td></tr>`;
        return;
    }
    
    const start = (currentCapitalPage - 1) * PAGE_SIZE;
    const paginated = entries.slice(start, start + PAGE_SIZE);
    
    paginated.forEach(entry => {
        const tr = document.createElement("tr");
        tr.innerHTML = `
            <td>${entry.date}</td>
            <td style="font-weight: 600;">${entry.broker}</td>
            <td style="color: var(--text-secondary); font-size: 0.9em;">${entry.remarks || ""}</td>
            <td style="text-align: right; font-weight: 500; color: ${entry.amount >= 0 ? 'var(--color-gain)' : 'var(--color-loss)'};">
                ${entry.amount >= 0 ? '+' : ''}${formatCurrency(entry.amount)}
            </td>
            <td style="text-align: center;">
                <button class="btn btn-danger" style="padding: 0.2rem 0.4rem; font-size: 0.75rem;" onclick="deleteCapitalEntry(${entry.id})">&times;</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

window.deleteCapitalEntry = async function(id) {
    if (!confirm("Are you sure you want to delete this capital entry?")) return;
    try {
        const res = await fetch(`/api/settings/capital/${id}`, { method: "DELETE" });
        if (res.ok) {
            showToast("Capital entry deleted successfully.");
            await loadCapitalEntries();
        } else {
            showToast("Failed to delete capital entry.", "error");
        }
    } catch (e) {
        showToast("Error: " + e.message, "error");
    }
}

async function renderManagePortfolios() {
    const tbody = document.getElementById("manage-portfolios-list");
    tbody.innerHTML = "";
    
    portfoliosList.forEach((p, idx) => {
        const tr = document.createElement("tr");
        
        const upBtn = idx > 0 
            ? `<button class="btn btn-secondary" style="padding: 0.2rem 0.4rem; font-size: 0.75rem;" onclick="movePortfolio(${idx}, -1)">▲</button>` 
            : `<button class="btn btn-secondary" style="padding: 0.2rem 0.4rem; font-size: 0.75rem; opacity: 0.3; cursor: not-allowed;" disabled>▲</button>`;
            
        const downBtn = idx < portfoliosList.length - 1 
            ? `<button class="btn btn-secondary" style="padding: 0.2rem 0.4rem; font-size: 0.75rem;" onclick="movePortfolio(${idx}, 1)">▼</button>` 
            : `<button class="btn btn-secondary" style="padding: 0.2rem 0.4rem; font-size: 0.75rem; opacity: 0.3; cursor: not-allowed;" disabled>▼</button>`;
            
        const currentClass = p.classification || "";
        const currentBroker = p.broker || "";
        
        let brokersList = ["IBKR", "MOOMOO"];
        const activeBrokersEl = document.getElementById('active-brokers-data');
        if (activeBrokersEl) {
            try {
                brokersList = JSON.parse(activeBrokersEl.textContent);
            } catch (e) {
                console.error("Failed to parse active brokers", e);
            }
        }
        let brokerFound = false;
        let brokerOptionsHtml = "";
        brokersList.forEach(br => {
            const isMatch = br.toUpperCase() === currentBroker.toUpperCase();
            if (isMatch) brokerFound = true;
            brokerOptionsHtml += `<option value="${br}" ${isMatch ? "selected" : ""}>${br}</option>`;
        });
        if (!brokerFound && currentBroker) {
            brokerOptionsHtml += `<option value="${currentBroker}" selected>${currentBroker}</option>`;
        }
            
        tr.innerHTML = `
            <td style="font-weight:600;">💼 ${p.name}</td>
            <td>
                <input type="text" value="${currentClass}" onchange="updatePortfolioClassification(${p.id}, this.value)" style="width: 130px; padding: 0.25rem 0.5rem; background: var(--bg-secondary); border: 1px solid var(--card-border); border-radius: 4px; color: var(--text-primary); font-family: inherit; font-size: 0.85rem;">
            </td>
            <td>
                <select onchange="updatePortfolioBroker(${p.id}, this.value)" style="width: 100px; padding: 0.25rem 0.5rem; background: var(--bg-secondary); border: 1px solid var(--card-border); border-radius: 4px; color: var(--text-primary); font-family: inherit; font-size: 0.85rem; cursor: pointer;">
                    ${brokerOptionsHtml}
                </select>
            </td>
            <td style="display: flex; gap: 0.35rem; align-items: center; border-bottom: none;">
                ${upBtn}
                ${downBtn}
                  <button class="btn btn-danger" style="padding: 0.25rem 0.5rem; font-size: 0.75rem;" onclick="deletePortfolio(this, ${p.id})">Delete</button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

window.updatePortfolioClassification = async function(id, value) {
    const portfolio = portfoliosList.find(p => p.id === id);
    if (!portfolio) return;
    try {
        const res = await fetch(`/api/portfolios/${id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: portfolio.name,
                classification: value,
                broker: portfolio.broker || ""
            })
        });
        if (res.ok) {
            showToast("Portfolio classification updated.");
            portfolio.classification = value;
            await loadPortfolios();
            renderManagePortfolios();
        } else {
            showToast("Failed to update classification.", "error");
        }
    } catch (e) {
        showToast("Error: " + e.message, "error");
    }
};

window.updatePortfolioBroker = async function(id, value) {
    const portfolio = portfoliosList.find(p => p.id === id);
    if (!portfolio) return;
    try {
        const res = await fetch(`/api/portfolios/${id}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                name: portfolio.name,
                classification: portfolio.classification || "",
                broker: value
            })
        });
        if (res.ok) {
            showToast("Portfolio broker updated.");
            portfolio.broker = value;
            await loadPortfolios();
            renderManagePortfolios();
        } else {
            showToast("Failed to update broker.", "error");
        }
    } catch (e) {
        showToast("Error: " + e.message, "error");
    }
};

window.movePortfolio = async function(idx, direction) {
    const targetIdx = idx + direction;
    if (targetIdx < 0 || targetIdx >= portfoliosList.length) return;
    
    const temp = portfoliosList[idx];
    portfoliosList[idx] = portfoliosList[targetIdx];
    portfoliosList[targetIdx] = temp;
    
    const sortedIds = portfoliosList.map(p => p.id);
    
    try {
        const res = await fetch("/api/portfolios/reorder", {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ order: sortedIds })
        });
        
        if (res.ok) {
            renderManagePortfolios();
            await loadPortfolios();
        } else {
            showToast("Failed to save reorder", "error");
        }
    } catch (e) {
        showToast("Error reordering: " + e.message, "error");
    }
};

window.deletePortfolio = async function(btnOrId, possibleId) {
    let id = possibleId;
    let btn = null;
    if (typeof btnOrId === "number" || typeof btnOrId === "string") {
        id = btnOrId;
    } else {
        btn = btnOrId;
    }
    
    if (confirm("Are you sure you want to delete this portfolio? This will remove all associated transactions and dividends!")) {
        let originalText = "";
        if (btn) {
            btn.disabled = true;
            originalText = btn.innerHTML;
            btn.innerHTML = "Deleting...";
        }
        try {
            const res = await fetch(`/api/portfolios/${id}`, { method: "DELETE" });
            if (res.ok) {
                showToast("Portfolio deleted.");
                await loadPortfolios();
                
                if (selectedPortfolioId === id) {
                    selectPortfolio(null, "My Net Worth");
                } else {
                    renderManagePortfolios();
                }
            }
        } catch (e) {
            showToast("Delete failed: " + e.message, "error");
        } finally {
            if (btn) {
                btn.disabled = false;
                btn.innerHTML = originalText;
            }
        }
    }
};

/* Unified Modal and Sorting Custom Additions */

function updateQuantityStepAndMin() {
    const exchangeSelect = document.getElementById("tx-exchange");
    const quantityInput = document.getElementById("tx-quantity");
    if (!exchangeSelect || !quantityInput) return;
    
    const exchange = exchangeSelect.value;
    const isCanadianOrSG = (exchange === "TO" || exchange === "V" || exchange === "NE" || exchange === "SG");
    
    if (isCanadianOrSG) {
        quantityInput.step = "100";
        quantityInput.min = "100";
        quantityInput.placeholder = "Shares (Min 100)";
    } else {
        quantityInput.step = "1";
        quantityInput.min = "1";
        quantityInput.placeholder = "Shares";
    }
}

function checkExistingTicker(value, inputId) {
    const symbol = value.trim().toUpperCase();
    const match = tickersList.find(t => t.symbol.toUpperCase() === symbol);
    
    let currencySelect = null;
    let exchangeSelect = null;
    if (inputId === "tx-ticker") {
        currencySelect = document.getElementById("tx-currency");
        exchangeSelect = document.getElementById("tx-exchange");
    } else if (inputId === "div-ticker") {
        currencySelect = document.getElementById("div-currency");
        const taxRateInput = document.getElementById("div-tax-rate");
        if (match && taxRateInput) {
            taxRateInput.value = (match.tax_rate !== null && match.tax_rate !== undefined) ? (match.tax_rate * 100).toFixed(0) : "";
        } else if (taxRateInput) {
            taxRateInput.value = "";
        }
        
        refreshDefaultDividendQty();
    }
    
    const isEditing = !!document.getElementById("tx-id").value;
    
    if (currencySelect) {
        if (match) {
            if (match.currency) {
                currencySelect.value = match.currency;
            }
            if (match.shares > 0.0001 && !isEditing) {
                currencySelect.disabled = true;
                if (exchangeSelect) {
                    exchangeSelect.disabled = true;
                }
            } else {
                currencySelect.disabled = false;
                if (exchangeSelect) {
                    exchangeSelect.disabled = false;
                }
            }
            if (exchangeSelect) {
                exchangeSelect.value = match.exchange || "US";
                updateQuantityStepAndMin();
            }
            
            // Auto-fill price box for new transactions only
            if (inputId === "tx-ticker" && !isEditing && match.price !== undefined && match.price !== null) {
                const parsedPrice = parseFloat(match.price);
                document.getElementById("tx-price").value = isNaN(parsedPrice) ? "" : parsedPrice.toFixed(2);
            }
        } else {
            currencySelect.disabled = false;
            if (exchangeSelect) {
                exchangeSelect.disabled = false;
                // pre-populate based on currency select value
                const curr = currencySelect.value;
                if (curr === "CAD") {
                    exchangeSelect.value = "TO";
                } else if (curr === "SGD") {
                    exchangeSelect.value = "SG";
                } else {
                    exchangeSelect.value = "US";
                }
                updateQuantityStepAndMin();
            }
        }
    }
}

function openTransactionModal(tabName = "trades", editingData = null) {
    editingTransactionData = editingData; // Store original editing data
    const form = document.getElementById("transaction-form");
    form.reset();
    document.getElementById("tx-id").value = "";
    
    const divCalcContainer = document.getElementById("div-calc-container");
    if (divCalcContainer) divCalcContainer.style.display = "block";
    
    const localDateTime = new Date();
    localDateTime.setMinutes(localDateTime.getMinutes() - localDateTime.getTimezoneOffset());
    document.getElementById("tx-date").value = localDateTime.toISOString().substring(0, 16);
    document.getElementById("div-date").value = localDateTime.toISOString().substring(0, 10);
    document.getElementById("exp-date").value = localDateTime.toISOString().substring(0, 10);
    
    document.getElementById("tx-currency").disabled = false;
    document.getElementById("div-currency").disabled = false;
    document.getElementById("exp-currency").disabled = false;
    
    const txExchange = document.getElementById("tx-exchange");
    if (txExchange) {
        txExchange.disabled = false;
        txExchange.value = "US";
        updateQuantityStepAndMin();
    }
    
    const titleEl = document.getElementById("transaction-modal-title");
    if (editingData) {
        titleEl.textContent = `Edit ${tabName === 'trades' ? 'Trade' : (tabName === 'incomes' ? 'Income' : 'Expense')}`;
        populateEditingData(tabName, editingData);
    } else {
        titleEl.textContent = "New transaction";
        // Pre-populate with the current page's selected portfolio
        if (selectedPortfolioId !== null) {
            document.getElementById("tx-portfolio").value = selectedPortfolioId;
        }
    }
    
    switchTab(tabName);
    
    const tabButtons = document.querySelectorAll("#transaction-modal .modal-tab-btn");
    if (editingData) {
        tabButtons.forEach(btn => {
            btn.style.pointerEvents = "none";
            btn.style.opacity = "0.5";
        });
    } else {
        tabButtons.forEach(btn => {
            btn.style.pointerEvents = "auto";
            btn.style.opacity = "1";
        });
    }
    
    // Initialize calculations for Trades tab
    if (tabName === "trades") {
        const currentPortfolioId = document.getElementById("tx-portfolio").value;
        updateModalHoldings(currentPortfolioId).then(() => {
            updateTradeModalCalculations();
        });
    }
    
    openModal("transaction-modal");
}

function switchTab(tabName) {
    document.getElementById("tx-tab").value = tabName;
    
    document.querySelectorAll("#transaction-modal .modal-tab-btn").forEach(btn => {
        if (btn.dataset.tab === tabName) {
            btn.classList.add("active");
        } else {
            btn.classList.remove("active");
        }
    });
    
    document.getElementById("wrapper-trades").style.display = tabName === "trades" ? "block" : "none";
    document.getElementById("wrapper-incomes").style.display = tabName === "incomes" ? "block" : "none";
    document.getElementById("wrapper-expenses").style.display = tabName === "expenses" ? "block" : "none";
    
    if (tabName === "trades") {
        updateTradeModalCalculations();
    }
    
    const isEditing = !!document.getElementById("tx-id").value;
    document.getElementById("btn-save-add-more-transaction").style.display = isEditing ? "none" : "inline-flex";
}

function populateEditingData(tabName, data) {
    document.getElementById("tx-id").value = data.id;
    document.getElementById("tx-portfolio").value = data.portfolio_id;
    document.getElementById("tx-notes").value = data.notes || "";
    
    if (tabName === "trades") {
        document.getElementById("tx-ticker").value = data.symbol;
        document.getElementById("tx-action").value = data.action;
        document.getElementById("tx-date").value = data.date.replace(" ", "T").substring(0, 16);
        const parsedPrice = parseFloat(data.price);
        document.getElementById("tx-price").value = isNaN(parsedPrice) ? "" : parsedPrice.toFixed(2);
        document.getElementById("tx-quantity").value = data.quantity;
        document.getElementById("tx-currency").value = data.currency;
        document.getElementById("tx-commission").value = data.commission || 0.0;
        const txExchange = document.getElementById("tx-exchange");
        if (txExchange) {
            txExchange.value = data.exchange || "US";
            txExchange.disabled = true;
            updateQuantityStepAndMin();
        }
        checkExistingTicker(data.symbol, "tx-ticker");
    } else if (tabName === "incomes") {
        document.getElementById("div-ticker").value = data.symbol;
        document.getElementById("div-date").value = data.date.substring(0, 10);
        document.getElementById("div-amount").value = data.amount;
        document.getElementById("div-currency").value = data.currency;
        document.getElementById("div-tax").value = data.tax;
        document.getElementById("div-qty").value = data.qty !== undefined && data.qty !== null ? data.qty : "";
        checkExistingTicker(data.symbol, "div-ticker");
        updateDividendCalculations();
    } else if (tabName === "expenses") {
        document.getElementById("exp-date").value = data.date.substring(0, 10);
        document.getElementById("exp-amount").value = data.commission;
        document.getElementById("exp-currency").value = data.currency;
    }
}

async function saveTransaction(closeModalOnSuccess = true) {
    const tab = document.getElementById("tx-tab").value;
    const portfolioId = parseInt(document.getElementById("tx-portfolio").value);
    const id = document.getElementById("tx-id").value;
    const notes = document.getElementById("tx-notes").value;
    
    if (!portfolioId) {
        showToast("Please select a portfolio.", "error");
        return;
    }
    
    let url = "";
    let method = "";
    let payload = {};
    
    if (tab === "trades") {
        const symbol = document.getElementById("tx-ticker").value.trim();
        const action = document.getElementById("tx-action").value;
        const date = document.getElementById("tx-date").value;
        const price = parseFloat(document.getElementById("tx-price").value);
        const quantity = parseFloat(document.getElementById("tx-quantity").value);
        const currency = document.getElementById("tx-currency").value;
        const commission = parseFloat(document.getElementById("tx-commission").value || 0.0);
        const exchangeVal = document.getElementById("tx-exchange") ? document.getElementById("tx-exchange").value : "US";
        
        if (!symbol || !date || isNaN(price) || isNaN(quantity)) {
            showToast("Please fill in all required trade fields.", "error");
            return;
        }
        
        if (action === "BUY" || action === "SELL") {
            const isCanadianOrSG = (exchangeVal === "TO" || exchangeVal === "V" || exchangeVal === "NE" || exchangeVal === "SG");
            const minLotSize = isCanadianOrSG ? 100 : 1;
            if (quantity < minLotSize) {
                showToast(`Validation Error: Quantity must be at least ${minLotSize} for ${exchangeVal} exchange.`, "error");
                return;
            }
            if (quantity % minLotSize !== 0) {
                showToast(`Validation Error: Quantity must be a multiple of ${minLotSize} for ${exchangeVal} exchange.`, "error");
                return;
            }
        }
        
        if (action === "SELL") {
            const holding = modalPortfolioHoldings.find(h => h.symbol.toUpperCase() === symbol.toUpperCase());
            let sharesHeld = holding ? holding.shares : 0;
            
            // Adjust if editing the same ticker in the same portfolio
            if (editingTransactionData && 
                editingTransactionData.action === "SELL" && 
                editingTransactionData.symbol.toUpperCase() === symbol.toUpperCase() &&
                editingTransactionData.portfolio_id === portfolioId) {
                sharesHeld += editingTransactionData.quantity;
            }
            
            if (sharesHeld <= 0) {
                showToast(`Validation Error: You do not own any shares of ${symbol} in this portfolio.`, "error");
                return;
            }
            if (quantity > sharesHeld) {
                showToast(`Validation Error: Cannot sell ${quantity} shares. You only own ${sharesHeld} shares of ${symbol} in this portfolio.`, "error");
                return;
            }
        }
        
        url = id ? `/api/transactions/${id}` : "/api/transactions";
        method = id ? "PUT" : "POST";
        payload = {
            portfolio_id: portfolioId,
            ticker: symbol,
            action: action,
            date: date.replace("T", " ") + (date.includes(":") && date.split(":").length === 2 ? ":00" : ""),
            price: price,
            quantity: quantity,
            currency: currency,
            commission: commission,
            exchange: exchangeVal,
            notes: notes
        };
        
    } else if (tab === "incomes") {
        const symbol = document.getElementById("div-ticker").value.trim();
        const date = document.getElementById("div-date").value;
        const amount = parseFloat(document.getElementById("div-amount").value);
        const currency = document.getElementById("div-currency").value;
        const taxVal = document.getElementById("div-tax").value;
        const tax = taxVal ? parseFloat(taxVal) : null;
        const qtyVal = document.getElementById("div-qty").value;
        const qty = qtyVal ? parseFloat(qtyVal) : null;
        
        if (!symbol || !date || isNaN(amount)) {
            showToast("Please fill in all required income fields.", "error");
            return;
        }
        
        url = id ? `/api/dividends/${id}` : "/api/dividends";
        method = id ? "PUT" : "POST";
        payload = {
            portfolio_id: portfolioId,
            ticker: symbol,
            date: date,
            amount: amount,
            currency: currency,
            tax: tax,
            qty: qty,
            notes: notes
        };
        
    } else if (tab === "expenses") {
        const date = document.getElementById("exp-date").value;
        const amount = parseFloat(document.getElementById("exp-amount").value);
        const currency = document.getElementById("exp-currency").value;
        
        if (!date || isNaN(amount)) {
            showToast("Please fill in all required expense fields.", "error");
            return;
        }
        
        url = id ? `/api/transactions/${id}` : "/api/transactions";
        method = id ? "PUT" : "POST";
        payload = {
            portfolio_id: portfolioId,
            ticker: "PORTFOLIO_FEE",
            action: "FEE",
            date: date + " 00:00:00",
            price: 0.0,
            quantity: 0.0,
            currency: currency,
            commission: amount,
            notes: notes
        };
    }
    
    const btnSave = document.getElementById("btn-save-transaction");
    const btnSaveMore = document.getElementById("btn-save-add-more-transaction");
    let originalSaveText = "";
    let originalSaveMoreText = "";
    
    if (btnSave) {
        btnSave.disabled = true;
        originalSaveText = btnSave.innerHTML;
        btnSave.innerHTML = "Saving...";
    }
    if (btnSaveMore) {
        btnSaveMore.disabled = true;
        originalSaveMoreText = btnSaveMore.innerHTML;
        btnSaveMore.innerHTML = "Saving...";
    }
    
    try {
        const res = await fetch(url, {
            method: method,
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload)
        });
        
        if (res.ok) {
            showToast("Saved successfully.");
            currentModalPortfolioId = null; // Clear cached holdings
            
            if (closeModalOnSuccess) {
                closeModal("transaction-modal");
            } else {
                if (tab === "trades") {
                    document.getElementById("tx-ticker").value = "";
                    document.getElementById("tx-price").value = "";
                    document.getElementById("tx-quantity").value = "";
                    document.getElementById("tx-commission").value = "";
                    document.getElementById("tx-currency").disabled = false;
                    const txExchange = document.getElementById("tx-exchange");
                    if (txExchange) {
                        txExchange.value = "US";
                        txExchange.disabled = false;
                    }
                } else if (tab === "incomes") {
                    document.getElementById("div-ticker").value = "";
                    document.getElementById("div-amount").value = "";
                    document.getElementById("div-tax").value = "";
                    document.getElementById("div-currency").disabled = false;
                } else if (tab === "expenses") {
                    document.getElementById("exp-amount").value = "";
                }
                document.getElementById("tx-notes").value = "";
            }
            
            const activeNav = navs.find(n => document.getElementById(n.navId).classList.contains("active"));
            if (activeNav && activeNav.callback) {
                if (activeNav.callback === loadTransactions || activeNav.callback === loadDividends) {
                    activeNav.callback(true);
                } else {
                    activeNav.callback();
                }
            }
            loadTickersList();
        } else {
            const err = await res.json();
            showToast("Error saving: " + err.detail, "error");
        }
    } catch (err) {
        showToast("Failed to save: " + err.message, "error");
    } finally {
        if (btnSave) {
            btnSave.disabled = false;
            btnSave.innerHTML = originalSaveText;
        }
        if (btnSaveMore) {
            btnSaveMore.disabled = false;
            btnSaveMore.innerHTML = originalSaveMoreText;
        }
    }
}

// editTransaction and editDividend are defined above

function setupTableSorting() {
    const table = document.getElementById("holdings-table");
    if (!table) return;
    
    table.querySelectorAll("thead th.sortable").forEach(th => {
        th.addEventListener("click", () => {
            const col = th.dataset.col;
            if (sortColumn === col) {
                sortDirection = sortDirection === "asc" ? "desc" : "asc";
            } else {
                sortColumn = col;
                sortDirection = "desc";
            }
            renderHoldingsTable(currentHoldings);
        });
    });
}

function updateSortHeaders() {
    const table = document.getElementById("holdings-table");
    if (!table) return;
    table.querySelectorAll("thead th.sortable").forEach(th => {
        th.classList.remove("asc", "desc");
        if (th.dataset.col === sortColumn) {
            th.classList.add(sortDirection);
        }
    });
}

function setupCustomAppEvents() {
    const searchInput = document.getElementById("ticker-search-input");
    if (searchInput) {
        searchInput.addEventListener("input", (e) => {
            currentTickersPage = 1;
            const query = e.target.value.trim().toLowerCase();
            if (!query) {
                renderTickersTable(cachedTickers);
                return;
            }
            const filtered = cachedTickers.filter(t => 
                t.symbol.toLowerCase().includes(query) ||
                (t.friendly_name && t.friendly_name.toLowerCase().includes(query)) ||
                (t.notes && t.notes.toLowerCase().includes(query)) || 
                (t.underlying && t.underlying.toLowerCase().includes(query))
            );
            renderTickersTable(filtered);
        });
    }

    const transactionSearchInput = document.getElementById("transaction-search-input");
    if (transactionSearchInput) {
        transactionSearchInput.addEventListener("input", (e) => {
            currentTradesPage = 1;
            const query = e.target.value.trim().toLowerCase();
            if (!query) {
                renderTransactionsTable(cachedTransactions);
                return;
            }
            const filtered = cachedTransactions.filter(t => 
                t.symbol.toLowerCase().includes(query) ||
                t.action.toLowerCase().includes(query) ||
                t.portfolio_name.toLowerCase().includes(query) ||
                (t.notes && t.notes.toLowerCase().includes(query)) ||
                t.date.includes(query)
            );
            renderTransactionsTable(filtered);
        });
    }

    const dividendSearchInput = document.getElementById("dividend-search-input");
    if (dividendSearchInput) {
        dividendSearchInput.addEventListener("input", (e) => {
            currentDividendsPage = 1;
            const query = e.target.value.trim().toLowerCase();
            if (!query) {
                renderDividendsTable(cachedDividends);
                return;
            }
            const filtered = cachedDividends.filter(d => 
                d.symbol.toLowerCase().includes(query) ||
                d.portfolio_name.toLowerCase().includes(query) ||
                (d.notes && d.notes.toLowerCase().includes(query)) ||
                d.date.includes(query)
            );
            renderDividendsTable(filtered);
        });
    }

    const activeToggle = document.getElementById("ticker-active-toggle");
    if (activeToggle) {
        activeToggle.addEventListener("change", () => {
            currentTickersPage = 1;
            const searchInput = document.getElementById("ticker-search-input");
            const query = searchInput ? searchInput.value.trim().toLowerCase() : "";
            if (!query) {
                renderTickersTable(cachedTickers);
            } else {
                const filtered = cachedTickers.filter(t => 
                    t.symbol.toLowerCase().includes(query) ||
                    (t.friendly_name && t.friendly_name.toLowerCase().includes(query)) ||
                    (t.notes && t.notes.toLowerCase().includes(query)) || 
                    (t.underlying && t.underlying.toLowerCase().includes(query))
                );
                renderTickersTable(filtered);
            }
        });
    }

    const tabButtons = document.querySelectorAll("#transaction-modal .modal-tab-btn");
    if (tabButtons) {
        tabButtons.forEach(btn => {
            btn.addEventListener("click", () => {
                switchTab(btn.dataset.tab);
            });
        });
    }

    const saveTxBtn = document.getElementById("btn-save-transaction");
    if (saveTxBtn) {
        saveTxBtn.addEventListener("click", () => {
            saveTransaction(true);
        });
    }

    const saveAddMoreTxBtn = document.getElementById("btn-save-add-more-transaction");
    if (saveAddMoreTxBtn) {
        saveAddMoreTxBtn.addEventListener("click", () => {
            saveTransaction(false);
        });
    }

    const toggleViewBtn = document.getElementById("toggle-dashboard-view-btn");
    if (toggleViewBtn) {
        toggleViewBtn.textContent = dashboardViewMode === "table" ? "View: Cards" : "View: Table";
        toggleViewBtn.addEventListener("click", () => {
            dashboardViewMode = dashboardViewMode === "table" ? "cards" : "table";
            localStorage.setItem("dashboardViewMode", dashboardViewMode);
            toggleViewBtn.textContent = dashboardViewMode === "table" ? "View: Cards" : "View: Table";
            renderHoldingsTable(currentHoldings);
        });
    }

    // Global Database Mutation Event Listener
    window.addEventListener("databaseMutated", async () => {
        // Clear cached entities to prevent display of stale data
        cachedTransactions = [];
        cachedDividends = [];
        cachedTickers = [];

        // If on the Trades Ledger page, automatically reload and re-render tables
        if (window.location.pathname.includes("trades")) {
            await Promise.all([
                loadTransactions(),
                loadDividends(),
                loadTickersList()
            ]);
            showToast("Trades ledger data refreshed from database.", "success");
        } else if (window.location.pathname.includes("control-center")) {
            // Re-fetch core list values for settings drop-downs
            await Promise.all([
                loadPortfolios(),
                loadTickersList()
            ]);
            showToast("Database configuration reloaded.", "success");
        }
    });
}

// 8. Performance & YTD Reports view
let perfGrowthChart = null;

async function loadPerformanceReport() {
    try {
        const response = await fetch("/api/reports/performance");
        const data = await response.json();
        
        // 1. Populate KPI Cards
        const years = data.years;
        if (!years || years.length === 0) {
            return;
        }
        const currentYear = years[years.length - 1];
        
        const latestMonthKey = Object.keys(data.cash_data[currentYear]).sort((a,b) => b-a)[0];
        const latestCash = data.cash_data[currentYear][latestMonthKey];
        
        document.getElementById("perf-kpi-liquid").innerText = formatCurrency(latestCash.liquidation_value);
        
        const mtdPct = latestCash.mtd.liquidation_value_pct;
        const mtdPctText = mtdPct !== null ? formatPercent(mtdPct) + " MTD" : '--';
        const mtdSubEl = document.getElementById("perf-kpi-liquid-sub");
        mtdSubEl.innerText = mtdPctText;
        if (mtdPct >= 0) {
            mtdSubEl.style.color = "var(--color-gain)";
        } else if (mtdPct < 0) {
            mtdSubEl.style.color = "var(--color-loss)";
        }
        
        document.getElementById("perf-kpi-capital").innerText = formatCurrency(latestCash.base_capital);
        
        const ytdData = data.cash_ytd[currentYear] || {};
        const additions = (ytdData.capital_end || 0) - (ytdData.capital_start || 0);
        document.getElementById("perf-kpi-capital-sub").innerText = `YTD additions: ${formatCurrency(additions)}`;
        
        const returns = latestCash.base_capital_gains;
        document.getElementById("perf-kpi-returns").innerText = formatCurrency(returns);
        const ytdGain = ytdData.gains_val || 0;
        const ytdGainPct = ytdData.gains_pct || 0;
        const returnsSubEl = document.getElementById("perf-kpi-returns-sub");
        returnsSubEl.innerText = `${ytdGain >= 0 ? '+' : ''}${formatCurrency(ytdGain)} (${formatPercent(ytdGainPct)} YTD)`;
        if (ytdGain >= 0) {
            returnsSubEl.style.color = "var(--color-gain)";
        } else {
            returnsSubEl.style.color = "var(--color-loss)";
        }
        
        // 2. Populate Year Selector
        const select = document.getElementById("perf-year-select");
        select.innerHTML = "";
        years.forEach(y => {
            const opt = document.createElement("option");
            opt.value = y;
            opt.text = y;
            if (y === currentYear) opt.selected = true;
            select.appendChild(opt);
        });
        
        // Setup listener for chart redraw on year change
        select.onchange = () => {
            renderPerformanceChart(data.chart_data, select.value);
        };
        
        // Render Chart
        renderPerformanceChart(data.chart_data, currentYear);
        
        // 3. Populate YTD table
        const ytdTbody = document.getElementById("perf-ytd-table-body");
        ytdTbody.innerHTML = "";
        years.forEach(y => {
            const yData = data.cash_ytd[y] || {};
            const tr = document.createElement("tr");
            const g = yData.gains_val || 0;
            const pct = yData.gains_pct || 0;
            tr.innerHTML = `
                <td style="font-weight: 600;">${y}</td>
                <td style="color: ${g >= 0 ? 'var(--color-gain)' : 'var(--color-loss)'}; font-weight: 500;">${g >= 0 ? '+' : ''}${formatCurrency(g)}</td>
                <td style="color: ${pct >= 0 ? 'var(--color-gain)' : 'var(--color-loss)'}; font-weight: 600;">${formatPercent(pct)}</td>
            `;
            ytdTbody.appendChild(tr);
        });
        
        // 4. Populate Detailed Monthly Matrix Table
        const mTableTbody = document.getElementById("perf-monthly-table-body");
        mTableTbody.innerHTML = "";
        const monthNames = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
        
        // Loop backward from newest month
        years.slice().reverse().forEach(y => {
            const yData = data.cash_data[y] || {};
            const months = Object.keys(yData).map(Number).sort((a,b) => b-a);
            months.forEach(m => {
                const row = yData[m];
                const tr = document.createElement("tr");
                tr.style.borderBottom = "1px solid var(--card-border)";
                const mtdVal = row.mtd.liquidation_value_val || 0;
                const mtdPct = row.mtd.liquidation_value_pct || 0;
                tr.innerHTML = `
                    <td style="font-weight: 600;">${y} - ${monthNames[m]}</td>
                    <td>${formatCurrency(row.liquidation_value)}</td>
                    <td style="color: var(--text-secondary);">${formatCurrency(row.base_capital)}</td>
                    <td>${formatCurrency(row.total_stock_value)}</td>
                    <td style="color: var(--text-muted);">${formatCurrency(row.cash_on_hand)}</td>
                    <td style="color: ${mtdVal >= 0 ? 'var(--color-gain)' : 'var(--color-loss)'}; font-weight: 500;">${mtdVal >= 0 ? '+' : ''}${formatCurrency(mtdVal)}</td>
                    <td style="color: ${mtdPct >= 0 ? 'var(--color-gain)' : 'var(--color-loss)'}; font-weight: 600;">${formatPercent(mtdPct)}</td>
                `;
                mTableTbody.appendChild(tr);
            });
        });
        
    } catch (err) {
        showToast("Error loading performance report: " + err.message, "error");
    }
}

function renderPerformanceChart(chartData, year) {
    const ctx = document.getElementById("perf-growth-chart").getContext("2d");
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    
    const yearData = chartData.cash[year] || { cumulative: [], mtd_val: [] };
    
    if (perfGrowthChart) {
        perfGrowthChart.destroy();
    }
    
    perfGrowthChart = new Chart(ctx, {
        type: 'line',
        data: {
            labels: months,
            datasets: [
                {
                    label: 'Cumulative Gains (SGD)',
                    data: yearData.cumulative,
                    borderColor: '#38bdf8',
                    backgroundColor: 'rgba(56, 189, 248, 0.1)',
                    borderWidth: 2,
                    tension: 0.25,
                    fill: true
                },
                {
                    label: 'MTD Gains (SGD)',
                    data: yearData.mtd_val,
                    type: 'bar',
                    backgroundColor: yearData.mtd_val.map(v => v >= 0 ? 'rgba(16, 185, 129, 0.45)' : 'rgba(239, 68, 68, 0.45)'),
                    borderColor: yearData.mtd_val.map(v => v >= 0 ? '#10b981' : '#ef4444'),
                    borderWidth: 1
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: {
                    position: 'top',
                    labels: { color: '#e2e8f0' }
                }
            },
            scales: {
                x: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.05)' } },
                y: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.05)' } }
            }
        }
    });
}

// 9. Options Tracker view
let optionsWeeklyChart = null;

async function loadOptionsTracker() {
    try {
        const response = await fetch("/api/reports/options");
        const data = await response.json();
        
        // 1. Populate KPI Cards
        document.getElementById("opt-kpi-realized").innerText = formatCurrency(data.options_profit_sgd);
        document.getElementById("opt-kpi-open-premium").innerText = formatCurrency(data.total_open_potential_return_sgd);
        document.getElementById("opt-kpi-max-loss").innerText = formatCurrency(data.total_open_max_loss_sgd);
        document.getElementById("opt-kpi-assignment").innerText = formatCurrency(data.total_open_assignment_risk_sgd);
        
        const unpl = data.total_open_unrealized_profit_sgd;
        const unplPct = data.total_open_unrealized_profit_pct;
        document.getElementById("opt-kpi-unrealized").innerText = formatCurrency(unpl);
        
        const unplSubEl = document.getElementById("opt-kpi-unrealized-sub");
        unplSubEl.innerText = formatPercent(unplPct);
        if (unpl >= 0) {
            unplSubEl.style.color = "var(--color-gain)";
        } else {
            unplSubEl.style.color = "var(--color-loss)";
        }
        
        // 2. Populate Expiration Risk Breakdown Table
        const breakdownTbody = document.getElementById("opt-breakdown-table-body");
        breakdownTbody.innerHTML = "";
        (data.options_max_loss_breakdown || []).forEach(row => {
            const tr = document.createElement("tr");
            tr.innerHTML = `
                <td style="font-weight: 500;">${row.expiry_date}</td>
                <td>${row.dte} d</td>
                <td>${formatCurrency(row.max_loss_sgd)}</td>
                <td style="color: var(--text-secondary);">${formatCurrency(row.assignment_risk_sgd)}</td>
            `;
            breakdownTbody.appendChild(tr);
        });
        
        // 3. Populate Weekly Closed Profits Chart
        const chartLabels = [];
        const chartValues = [];
        const recentClosed = data.recent_closed || [];
        recentClosed.slice().reverse().forEach(w => {
            chartLabels.push(w.range);
            chartValues.push(w.closed_pnl);
        });
        renderOptionsWeeklyChart(chartLabels, chartValues);
        
        // 4. Populate Open Option Strategies Table
        const openTbody = document.getElementById("opt-open-table-body");
        openTbody.innerHTML = "";
        (data.open_options || []).forEach(grp => {
            const tr = document.createElement("tr");
            tr.style.borderBottom = "1px solid var(--card-border)";
            
            let strategyDetails = "";
            grp.legs.forEach(leg => {
                const positionText = `${leg.initial_type} x${leg.current_quantity} $${leg.strike_price} ${leg.call_put}`;
                strategyDetails += `<div style="font-size: 0.85rem; color: var(--text-secondary); margin-bottom: 2px;">${positionText}</div>`;
            });
            
            const u = grp.unrealized_profit_sgd;
            const uPct = grp.unrealized_profit_pct;
            
            tr.innerHTML = `
                <td style="font-weight: 600; color: #38bdf8;">${grp.symbol}</td>
                <td>${grp.expiry_date}</td>
                <td>${grp.dte} d</td>
                <td>${strategyDetails}</td>
                <td>${formatCurrency(grp.total_cost_sgd)}</td>
                <td>${formatCurrency(grp.max_loss_sgd)}</td>
                <td style="color: ${u >= 0 ? 'var(--color-gain)' : 'var(--color-loss)'}; font-weight: 500;">
                    ${u >= 0 ? '+' : ''}${formatCurrency(u)} (${formatPercent(uPct)})
                </td>
                <td style="font-weight: 600;">${grp.potential_return_pct.toFixed(1)}%</td>
            `;
            openTbody.appendChild(tr);
        });
        
        // 5. Populate Recently Closed Table
        const closedTbody = document.getElementById("opt-closed-table-body");
        closedTbody.innerHTML = "";
        
        recentClosed.forEach(week => {
            week.closed.forEach((grp, idx) => {
                const tr = document.createElement("tr");
                tr.style.borderBottom = "1px solid var(--card-border)";
                
                let legsDetails = "";
                grp.legs.forEach(leg => {
                    legsDetails += `<div style="font-size: 0.85rem; color: var(--text-secondary);">${leg.symbol} ${leg.action} x${leg.original_quantity} $${leg.strike_price} ${leg.call_put}</div>`;
                });
                
                const pnlUsd = grp.realized_pnl_usd;
                const pnlSgd = grp.realized_pnl_sgd;
                
                const weekCol = idx === 0 
                    ? `<td rowspan="${week.closed.length}" style="vertical-align: top; font-weight: 600; background: rgba(255,255,255,0.01); border-right: 1px solid var(--card-border);">${week.range}</td>`
                    : '';
                    
                tr.innerHTML = `
                    ${weekCol}
                    <td>${legsDetails}</td>
                    <td>${grp.date_closed}</td>
                    <td>${grp.max_hold_days} d</td>
                    <td style="color: ${pnlUsd >= 0 ? 'var(--color-gain)' : 'var(--color-loss)'}; font-weight: 500;">${pnlUsd >= 0 ? '+' : ''}$${pnlUsd.toFixed(2)}</td>
                    <td style="color: ${pnlSgd >= 0 ? 'var(--color-gain)' : 'var(--color-loss)'}; font-weight: 600;">${pnlSgd >= 0 ? '+' : ''}${formatCurrency(pnlSgd)}</td>
                `;
                closedTbody.appendChild(tr);
            });
        });
        
    } catch (err) {
        showToast("Error loading options tracker: " + err.message, "error");
    }
}

function renderOptionsWeeklyChart(labels, values) {
    const ctx = document.getElementById("opt-weekly-chart").getContext("2d");
    
    if (optionsWeeklyChart) {
        optionsWeeklyChart.destroy();
    }
    
    optionsWeeklyChart = new Chart(ctx, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [
                {
                    label: 'Realized Income (SGD)',
                    data: values,
                    backgroundColor: values.map(v => v >= 0 ? 'rgba(16, 185, 129, 0.45)' : 'rgba(239, 68, 68, 0.45)'),
                    borderColor: values.map(v => v >= 0 ? '#10b981' : '#ef4444'),
                    borderWidth: 2,
                    borderRadius: 4
                }
            ]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                x: { ticks: { color: '#94a3b8' }, grid: { display: false } },
                y: { ticks: { color: '#94a3b8' }, grid: { color: 'rgba(255,255,255,0.05)' } }
            }
        }
    });
}

// --- Trade Modal Holdings Cache & Calculation Helpers ---
let modalPortfolioHoldings = [];
let currentModalPortfolioId = null;
let editingTransactionData = null;

async function updateModalHoldings(portfolioId) {
    if (!portfolioId) {
        modalPortfolioHoldings = [];
        currentModalPortfolioId = null;
        return;
    }
    const pid = parseInt(portfolioId);
    if (currentModalPortfolioId === pid) {
        return;
    }
    try {
        const res = await fetch(`/api/dashboard/summary?portfolio_id=${pid}`);
        if (res.ok) {
            const data = await res.json();
            modalPortfolioHoldings = data.holdings || [];
            currentModalPortfolioId = pid;
        } else {
            modalPortfolioHoldings = [];
            currentModalPortfolioId = null;
        }
    } catch (e) {
        console.error("Error fetching portfolio summary for modal:", e);
        modalPortfolioHoldings = [];
        currentModalPortfolioId = null;
    }
}

function refreshDefaultDividendQty() {
    const isEditing = !!document.getElementById("tx-id").value;
    if (isEditing) return; // Only default qty for new transactions
    
    const portfolioId = document.getElementById("tx-portfolio").value;
    const symbolInput = document.getElementById("div-ticker");
    if (!symbolInput) return;
    const symbol = symbolInput.value.trim().toUpperCase();
    const date = document.getElementById("div-date").value;
    const qtyInput = document.getElementById("div-qty");
    
    if (portfolioId && symbol && date && qtyInput) {
        fetch(`/api/portfolios/${portfolioId}/shares?ticker=${encodeURIComponent(symbol)}&date=${date}`)
            .then(res => res.json())
            .then(data => {
                if (data && data.shares !== undefined) {
                    qtyInput.value = data.shares;
                    updateDividendCalculations();
                }
            })
            .catch(err => console.error("Error fetching shares:", err));
    }
}

function updateDividendCalculations() {
    const tab = document.getElementById("tx-tab").value;
    if (tab !== "incomes") return;

    const amountInput = document.getElementById("div-amount");
    const qtyInput = document.getElementById("div-qty");
    const taxInput = document.getElementById("div-tax");
    const taxRateInput = document.getElementById("div-tax-rate");
    const divCalcContainer = document.getElementById("div-calc-container");
    const grossShareSpan = document.getElementById("div-calc-gross-share");
    const netShareSpan = document.getElementById("div-calc-net-share");

    if (!amountInput || !qtyInput || !divCalcContainer) return;

    const amount = parseFloat(amountInput.value);
    const qty = parseFloat(qtyInput.value);
    
    if (!isNaN(amount) && !isNaN(qty) && qty > 0) {
        const grossPerShare = amount / qty;
        
        let taxPaid = 0;
        const taxVal = taxInput.value.trim();
        if (taxVal !== "") {
            taxPaid = parseFloat(taxVal);
        } else {
            const taxRateVal = taxRateInput ? taxRateInput.value.trim() : "";
            if (taxRateVal !== "") {
                const taxRate = parseFloat(taxRateVal) / 100;
                taxPaid = amount * taxRate;
            }
        }
        
        if (isNaN(taxPaid)) taxPaid = 0;
        const netAmount = amount - taxPaid;
        const netPerShare = netAmount / qty;

        const currency = document.getElementById("div-currency").value;

        if (grossShareSpan) grossShareSpan.textContent = `${formatCurrency(grossPerShare, currency)}`;
        if (netShareSpan) netShareSpan.textContent = `${formatCurrency(netPerShare, currency)}`;
        divCalcContainer.style.display = "block";
    } else {
        if (grossShareSpan) grossShareSpan.textContent = "-";
        if (netShareSpan) netShareSpan.textContent = "-";
        divCalcContainer.style.display = "block";
    }
}

function updateTradeModalCalculations() {
    const tab = document.getElementById("tx-tab").value;
    if (tab !== "trades") return;

    const action = document.getElementById("tx-action").value;
    const ticker = document.getElementById("tx-ticker").value.trim().toUpperCase();
    const qtyInput = document.getElementById("tx-quantity");
    const priceInput = document.getElementById("tx-price");
    const commissionInput = document.getElementById("tx-commission");
    const currency = document.getElementById("tx-currency").value;

    // 1. Max Position to Sell
    const sharesHelp = document.getElementById("tx-shares-help");
    if (action === "SELL" && ticker) {
        const holding = modalPortfolioHoldings.find(h => h.symbol.toUpperCase() === ticker);
        let sharesHeld = holding ? holding.shares : 0;
        
        // Adjust if editing the same ticker in the same portfolio
        const portfolioId = parseInt(document.getElementById("tx-portfolio").value);
        if (editingTransactionData && 
            editingTransactionData.action === "SELL" && 
            editingTransactionData.symbol.toUpperCase() === ticker &&
            editingTransactionData.portfolio_id === portfolioId) {
            sharesHeld += editingTransactionData.quantity;
        }
        
        sharesHelp.innerHTML = `Max positions to sell: <span id="tx-max-shares-link" style="color: var(--accent-primary, #8b5cf6); cursor: pointer; text-decoration: underline; font-weight: 600;">${sharesHeld}</span>`;
        sharesHelp.style.display = "block";
    } else {
        sharesHelp.style.display = "none";
    }

    // 2. Net Trade Value Calculation
    const tradeValueContainer = document.getElementById("tx-trade-value-container");
    const valNativeSpan = document.getElementById("tx-trade-value-native");
    const valSgdSpan = document.getElementById("tx-trade-value-sgd");

    const qty = parseFloat(qtyInput.value);
    const price = parseFloat(priceInput.value);
    const fee = parseFloat(commissionInput.value || 0.0);

    if (!isNaN(qty) && qty > 0 && !isNaN(price) && price >= 0) {
        let nativeVal = 0;
        if (action === "BUY") {
            // BUY means outflow (negative cash)
            nativeVal = -(qty * price + fee);
        } else if (action === "SELL") {
            // SELL means inflow (positive cash)
            nativeVal = qty * price - fee;
        } else {
            // Stock splits have 0 transaction value
            nativeVal = 0;
        }

        const rate = exchangeRates[currency] || 1.0;
        const sgdVal = nativeVal * rate;

        let nativeText = "";
        let sgdText = "";
        let classColor = "";

        if (nativeVal < 0) {
            nativeText = `- ${formatCurrency(Math.abs(nativeVal), currency)}`;
            sgdText = `- ${formatCurrency(Math.abs(sgdVal), "SGD")}`;
            classColor = "text-loss";
        } else if (nativeVal > 0) {
            nativeText = `+ ${formatCurrency(Math.abs(nativeVal), currency)}`;
            sgdText = `+ ${formatCurrency(Math.abs(sgdVal), "SGD")}`;
            classColor = "text-gain";
        } else {
            nativeText = `${formatCurrency(0, currency)}`;
            sgdText = `${formatCurrency(0, "SGD")}`;
            classColor = "";
        }

        valNativeSpan.textContent = nativeText;
        valNativeSpan.className = classColor;
        
        valSgdSpan.textContent = sgdText;
        valSgdSpan.className = classColor ? "text-muted" : ""; // lighter sub-text
        
        tradeValueContainer.style.display = "block";
    } else {
        valNativeSpan.textContent = "-";
        valNativeSpan.className = "";
        valSgdSpan.textContent = "-";
        valSgdSpan.className = "";
        tradeValueContainer.style.display = "block";
    }
}

function setupTransactionModalCalculation() {
    const fields = ["tx-portfolio", "tx-ticker", "tx-action", "tx-quantity", "tx-price", "tx-commission", "tx-currency"];
    fields.forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        const eventType = el.tagName === "SELECT" ? "change" : "input";
        el.addEventListener(eventType, () => {
            if (id === "tx-portfolio") {
                updateModalHoldings(el.value).then(() => {
                    updateTradeModalCalculations();
                    const tab = document.getElementById("tx-tab").value;
                    if (tab === "incomes") {
                        refreshDefaultDividendQty();
                    }
                });
            } else {
                updateTradeModalCalculations();
            }
        });
    });

    // Incomes tab fields listeners
    const incomeFields = ["div-amount", "div-qty", "div-tax", "div-tax-rate"];
    incomeFields.forEach(id => {
        const el = document.getElementById(id);
        if (el) {
            el.addEventListener("input", updateDividendCalculations);
        }
    });

    const divDateEl = document.getElementById("div-date");
    if (divDateEl) {
        divDateEl.addEventListener("change", () => {
            refreshDefaultDividendQty();
        });
    }

    const divCurrencyEl = document.getElementById("div-currency");
    if (divCurrencyEl) {
        divCurrencyEl.addEventListener("change", () => {
            updateDividendCalculations();
        });
    }

    // Intercept quick-add menu options in SPA mode
    const addTradeLink = document.getElementById("nav-add-trade");
    if (addTradeLink) {
        addTradeLink.addEventListener("click", (e) => {
            e.preventDefault();
            const isTradesPage = !window.location.pathname.includes("control-center");
            if (isTradesPage) {
                openTransactionModal("trades");
            } else {
                const basePath = window.BASE_PATH || "";
                window.location.href = `${basePath}/trades?add=trades`;
            }
            const addMenu = document.getElementById("nav-add-dropdown");
            if (addMenu) addMenu.classList.remove("show");
        });
    }
    const addIncomeLink = document.getElementById("nav-add-income");
    if (addIncomeLink) {
        addIncomeLink.addEventListener("click", (e) => {
            e.preventDefault();
            const isTradesPage = !window.location.pathname.includes("control-center");
            if (isTradesPage) {
                openTransactionModal("incomes");
            } else {
                const basePath = window.BASE_PATH || "";
                window.location.href = `${basePath}/trades?add=incomes`;
            }
            const addMenu = document.getElementById("nav-add-dropdown");
            if (addMenu) addMenu.classList.remove("show");
        });
    }

    const addCapitalLink = document.getElementById("nav-add-capital");
    if (addCapitalLink) {
        addCapitalLink.addEventListener("click", (e) => {
            e.preventDefault();
            const isControlCenter = window.location.pathname.includes("control-center");
            if (isControlCenter) {
                const tabBtn = document.getElementById("nav-capital");
                if (tabBtn) tabBtn.click();
                openCapitalAddModal();
            } else {
                const basePath = window.BASE_PATH || "";
                window.location.href = `${basePath}/control-center?add=capital`;
            }
            const addMenu = document.getElementById("nav-add-dropdown");
            if (addMenu) addMenu.classList.remove("show");
        });
    }

    const addCashMetricsLink = document.getElementById("nav-add-cash-metrics");
    if (addCashMetricsLink) {
        addCashMetricsLink.addEventListener("click", (e) => {
            e.preventDefault();
            const isControlCenter = window.location.pathname.includes("control-center");
            if (isControlCenter) {
                const tabBtn = document.getElementById("nav-dailycash");
                if (tabBtn) tabBtn.click();
                openCashMetricsModal("MOOMOO");
            } else {
                const basePath = window.BASE_PATH || "";
                window.location.href = `${basePath}/control-center?add=cash-metrics`;
            }
            const addMenu = document.getElementById("nav-add-dropdown");
            if (addMenu) addMenu.classList.remove("show");
        });
    }


    // Delegate click events on the max positions link
    const sharesHelp = document.getElementById("tx-shares-help");
    if (sharesHelp) {
        sharesHelp.addEventListener("click", (e) => {
            if (e.target && e.target.id === "tx-max-shares-link") {
                e.preventDefault();
                const qtyInput = document.getElementById("tx-quantity");
                qtyInput.value = e.target.textContent;
                updateTradeModalCalculations();
            }
        });
    }

    // Database Backup Creation Button
    const backupBtn = document.getElementById("btn-db-backup");
    if (backupBtn) {
        backupBtn.addEventListener("click", async () => {
            const input = document.getElementById("db-backup-name");
            const backupName = input.value.trim();
            if (!backupName) {
                showToast("Please enter a backup name.", "error");
                return;
            }

            backupBtn.disabled = true;
            backupBtn.textContent = "Backing up...";

            try {
                const res = await fetch("/api/database/backup", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ backup_name: backupName })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(data.message || "Backup completed.");
                    input.value = "";
                    await loadDatabaseBackups();
                } else {
                    showToast(data.detail || "Backup failed.", "error");
                }
            } catch (e) {
                showToast("Backup request failed: " + e.message, "error");
            } finally {
                backupBtn.disabled = false;
                backupBtn.textContent = "Create Backup";
            }
        });
    }

    // Database Restore Button
    const restoreBtn = document.getElementById("btn-db-restore");
    if (restoreBtn) {
        restoreBtn.addEventListener("click", async () => {
            const select = document.getElementById("db-restore-select");
            const backupName = select.value;
            if (!backupName) {
                showToast("No backup file selected.", "error");
                return;
            }

            if (!confirm(`🚨 WARNING: Are you sure you want to restore "${backupName}" over the active database? This will overwrite all current data!`)) {
                return;
            }

            restoreBtn.disabled = true;
            restoreBtn.textContent = "Restoring...";

            try {
                const res = await fetch("/api/database/restore", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ backup_name: backupName, target_name: "portfolio.db" })
                });
                const data = await res.json();
                if (res.ok) {
                    showToast(data.message || "Database restored successfully!", "success");
                    await Promise.all([loadPortfolios(), loadTickersList()]);
                    window.dispatchEvent(new Event("databaseMutated"));
                } else {
                    showToast(data.detail || "Restore failed.", "error");
                }
            } catch (e) {
                showToast("Restore request failed: " + e.message, "error");
            } finally {
                restoreBtn.disabled = false;
                restoreBtn.textContent = "Restore Selected Backup";
            }
        });
    }

    // Patch Select Dropdown Change
    const patchSelect = document.getElementById("patch-select");
    if (patchSelect) {
        patchSelect.addEventListener("change", (e) => {
            const patchId = e.target.value;
            const descCard = document.getElementById("patch-desc-card");
            const descText = document.getElementById("patch-desc-text");
            const paramsForm = document.getElementById("patch-params-form");
            const paramsFields = document.getElementById("patch-params-fields");
            const executeBtn = document.getElementById("btn-patch-execute");

            if (!patchId) {
                descCard.style.display = "none";
                paramsForm.style.display = "none";
                executeBtn.disabled = true;
                return;
            }

            const patch = cachedPatches.find(p => p.id === patchId);
            if (!patch) return;

            descText.textContent = patch.description || "No description provided.";
            descCard.style.display = "block";

            paramsFields.innerHTML = "";
            const params = patch.parameters || [];
            
            if (params.length > 0) {
                params.forEach(param => {
                    const group = document.createElement("div");
                    group.className = "form-group";
                    group.style.marginBottom = "1rem";

                    const label = document.createElement("label");
                    label.textContent = param.label + (param.required ? " *" : "");
                    label.style.display = "block";
                    label.style.fontWeight = "600";
                    label.style.marginBottom = "0.3rem";
                    label.style.fontSize = "0.9rem";
                    group.appendChild(label);

                    let input;
                    if (param.type === "select") {
                        input = document.createElement("select");
                        input.className = "modal-exchange-select";
                        input.style.width = "100%";
                        input.style.padding = "0.5rem";
                        const options = param.options || [];
                        input.innerHTML = options.map(opt => `<option value="${opt}">${opt}</option>`).join("");
                    } else if (param.type === "boolean") {
                        const container = document.createElement("div");
                        container.style.display = "flex";
                        container.style.alignItems = "center";
                        container.style.gap = "8px";
                        
                        input = document.createElement("input");
                        input.type = "checkbox";
                        input.id = `param-${param.name}`;
                        input.checked = param.default || false;
                        
                        const checkLabel = document.createElement("label");
                        checkLabel.htmlFor = input.id;
                        checkLabel.textContent = "Yes";
                        checkLabel.style.fontSize = "0.9rem";
                        
                        container.appendChild(input);
                        container.appendChild(checkLabel);
                        group.appendChild(container);
                        paramsFields.appendChild(group);
                        return;
                    } else {
                        input = document.createElement("input");
                        input.type = param.type === "number" ? "number" : (param.type === "date" ? "date" : "text");
                        input.className = "modal-exchange-select";
                        input.style.width = "100%";
                        input.style.padding = "0.5rem";
                        if (param.default !== undefined) input.value = param.default;
                        if (param.placeholder) input.placeholder = param.placeholder;
                        if (param.required) input.required = true;
                    }

                    input.id = `param-${param.name}`;
                    input.name = param.name;
                    group.appendChild(input);
                    paramsFields.appendChild(group);
                });
                paramsForm.style.display = "block";
            } else {
                paramsForm.style.display = "none";
            }

            executeBtn.disabled = false;
        });
    }

    // Execute Patch Button Click
    const executeBtn = document.getElementById("btn-patch-execute");
    if (executeBtn) {
        executeBtn.addEventListener("click", async () => {
            const patchSelect = document.getElementById("patch-select");
            const patchId = patchSelect.value;
            if (!patchId) return;

            const patch = cachedPatches.find(p => p.id === patchId);
            if (!patch) return;

            const parameters = {};
            const params = patch.parameters || [];
            
            const form = document.getElementById("patch-params-form");
            if (form && params.length > 0 && !form.checkValidity()) {
                form.reportValidity();
                return;
            }

            params.forEach(param => {
                const el = document.getElementById(`param-${param.name}`);
                if (el) {
                    if (param.type === "boolean") {
                        parameters[param.name] = el.checked;
                    } else if (param.type === "number") {
                        parameters[param.name] = el.value === "" ? null : parseFloat(el.value);
                    } else {
                        parameters[param.name] = el.value;
                    }
                }
            });

            executeBtn.disabled = true;
            executeBtn.textContent = "Executing...";
            const consolePre = document.getElementById("patch-console-pre");
            consolePre.textContent = "Executing patch script, please wait...\n";

            try {
                const res = await fetch("/api/patches/execute", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ patch_id: patchId, parameters: parameters })
                });
                
                const data = await res.json();
                if (res.ok) {
                    consolePre.textContent = data.logs || "Execution completed with no logs.";
                    if (data.success) {
                        showToast("Patch executed successfully!");
                        await Promise.all([loadPortfolios(), loadTickersList()]);
                        window.dispatchEvent(new Event("databaseMutated"));
                    } else {
                        showToast("Patch execution failed. See logs.", "error");
                    }
                } else {
                    consolePre.textContent = `Error: ${data.detail || "Server error occurred."}`;
                    showToast("Execution request failed.", "error");
                }
            } catch (e) {
                consolePre.textContent = `Network Error: ${e.message}`;
                showToast("Failed to connect to executor.", "error");
            } finally {
                executeBtn.disabled = false;
                executeBtn.textContent = "Execute Patch";
            }
        });
    }
}

let cachedPatches = [];

async function loadMaintenanceTab() {
    await Promise.all([loadDatabaseBackups(), loadPatchesList()]);
}

async function loadDatabaseBackups() {
    const listContainer = document.getElementById("db-backups-list");
    const restoreSelect = document.getElementById("db-restore-select");
    if (!listContainer || !restoreSelect) return;

    try {
        const res = await fetch("/api/database/backups");
        if (res.ok) {
            const backups = await res.json();
            
            restoreSelect.innerHTML = backups.map(b => `<option value="${b}">${b}</option>`).join("");
            if (backups.length === 0) {
                restoreSelect.innerHTML = '<option value="">-- No backups available --</option>';
            }

            if (backups.length === 0) {
                listContainer.innerHTML = '<div style="color: var(--text-secondary); font-size: 0.9rem; text-align: center; padding: 1rem;">No backups found.</div>';
                return;
            }

            listContainer.innerHTML = backups.map(b => `
                <div style="display: flex; justify-content: space-between; align-items: center; padding: 0.5rem; border-bottom: 1px solid rgba(255,255,255,0.05); font-family: monospace; font-size: 0.9rem;">
                    <span style="color: var(--text-primary);">${b}</span>
                    <div style="display: flex; gap: 8px;">
                        <a href="/api/database/download/${b}" class="btn" style="padding: 0.2rem 0.5rem; font-size: 0.75rem; background: var(--bg-card); border: 1px solid var(--card-border); color: var(--text-primary); text-decoration: none; border-radius: 4px;" download>Download</a>
                        <button class="btn btn-danger" style="padding: 0.2rem 0.5rem; font-size: 0.75rem;" onclick="deleteBackupFile('${b}')">Delete</button>
                    </div>
                </div>
            `).join("");
        }
    } catch (e) {
        showToast("Error loading backups: " + e.message, "error");
    }
}

window.deleteBackupFile = async function(filename) {
    if (!confirm(`Are you sure you want to delete backup file "${filename}"?`)) return;
    try {
        const res = await fetch(`/api/database/delete/${filename}`, { method: "DELETE" });
        const data = await res.json();
        if (res.ok) {
            showToast(data.message || "Backup deleted.");
            await loadDatabaseBackups();
        } else {
            showToast(data.detail || "Delete failed.", "error");
        }
    } catch (e) {
        showToast("Delete request failed: " + e.message, "error");
    }
};

async function loadPatchesList() {
    const patchSelect = document.getElementById("patch-select");
    if (!patchSelect) return;

    try {
        const res = await fetch("/api/patches");
        if (res.ok) {
            cachedPatches = await res.json();
            let html = '<option value="">-- Select a patch to load --</option>';
            html += cachedPatches.map(p => `<option value="${p.id}">${p.id} - ${p.name}</option>`).join("");
            patchSelect.innerHTML = html;
        }
    } catch (e) {
        showToast("Error loading patches: " + e.message, "error");
    }
}
