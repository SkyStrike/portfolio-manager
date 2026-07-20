const APP_CONFIG = Object.assign({
    ui_font_size: "14px",
    ui_mobile_font_size: "12px",
    color_invested: "#8b5cf6",
    color_current: "#3498db",
    color_returns: "#2ecc71",
    color_income: "#2ecc71",
    color_positive: "#3498db",
    color_negative: "#e74c3c"
}, window.APP_CONFIG || {});

const chartInstances = {};
window.chartInstances = chartInstances;
const chartDataStore = {};
const monthNames = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

function expandAll() { document.querySelectorAll('details').forEach(d => d.open = true); }
function collapseAll() { document.querySelectorAll('details').forEach(d => d.open = false); }

const desktopFontSize = APP_CONFIG.ui_font_size;
const mobileFontSize = APP_CONFIG.ui_mobile_font_size;


/**
 * Unified Y-Axis configuration to ensure desktop/mobile alignment.
 */
function getYAxisConfig(mode, isMobile, isDaily = false) {
    let formatter;
    if (mode === 'pct') {
        formatter = (v) => Math.round(v) + '%';
    } else {
        formatter = (v) => '$' + Math.round(v).toLocaleString();
    }
    
    return {
        title: { text: '' },
        labels: {
            style: { fontSize: isMobile ? mobileFontSize : desktopFontSize },
            formatter: formatter
        }
    };
}

/**
 * Common responsive rules to maintain y-axis alignment across breakpoints.
 */
function getResponsiveConfig(mode, isDaily = false) {
    return [{
        breakpoint: 1200,
        options: {
            yaxis: getYAxisConfig(mode, false, isDaily),
            xaxis: { labels: { style: { fontSize: desktopFontSize } } },
            legend: { fontSize: desktopFontSize }
        }
    }, {
        breakpoint: 768,
        options: {
            yaxis: getYAxisConfig(mode, true, isDaily),
            xaxis: { labels: { style: { fontSize: mobileFontSize } } },
            legend: { fontSize: mobileFontSize }
        }
    }];
}

const commonOptions = {
    chart: { 
        type: 'bar', 
        height: '100%', 
        toolbar: { show: false }, 
        background: 'transparent'
    },
    theme: { mode: 'dark' },
    plotOptions: { 
        bar: { 
            horizontal: false, 
            columnWidth: '55%', 
            borderRadius: 4 
        } 
    },
    dataLabels: { enabled: false },
    stroke: { 
        show: true, 
        width: 2, 
        colors: ['transparent'] 
    },
    fill: { opacity: 1 },
    yaxis: getYAxisConfig('val', false),
    legend: {
        fontSize: desktopFontSize,
        height: 35,
        offsetY: -10
    },
    responsive: getResponsiveConfig('val')
};

const labelOptions = {
    fontSize: desktopFontSize
}

function safeRender(selector, renderFn) {
    const el = document.querySelector(selector);
    if (el) {
        el.innerHTML = '';
        renderFn(el);
    }
}

/**
 * Toggles between List View and Table View for the Table of Contents.
 * Persists the preference in localStorage.
 */
function toggleTOCView(view) {
    const listDiv = document.getElementById('toc-list-view');
    const tableDiv = document.getElementById('toc-table-view');
    const btnList = document.getElementById('btn-list-view');
    const btnTable = document.getElementById('btn-table-view');

    if (!listDiv || !tableDiv) return;

    if (view === 'table') {
        listDiv.style.display = 'none';
        tableDiv.style.display = 'block';
        btnList.classList.remove('active');
        btnTable.classList.add('active');
    } else {
        listDiv.style.display = 'block';
        tableDiv.style.display = 'none';
        btnList.classList.add('active');
        btnTable.classList.remove('active');
    }

    localStorage.setItem('toc_view_preference', view);
}

function renderBarChart(selector, id, title, categories, series, roi) {
    safeRender(selector, (el) => {
        // Use taller height for full-width containers
        const isFullWidth = el.classList.contains('full-width') || el.parentElement.classList.contains('full-width');
        const chartHeight = isFullWidth ? 450 : 350;

        const options = { 
            ...commonOptions, 
            chart: { ...commonOptions.chart, height: chartHeight },
            series, 
            xaxis: { 
                categories, 
                labels: { 
                    rotate: categories.length > 5 ? -45 : 0, 
                    style: { ...labelOptions } 
                }
            }, 
            title: { 
                text: title + ' (SGD)', 
                align: 'left' 
            }, 
            tooltip: { 
                y: { 
                    formatter: (val) => '$' + Math.round(val).toLocaleString() 
                } 
            },
            legend: { 
                ...labelOptions,
                height: 35,
                offsetY: -10
            }
        };
        
        if (series.length === 3) {
            options.colors = [APP_CONFIG.color_invested, APP_CONFIG.color_current, APP_CONFIG.color_returns]; 
        } else if (series.length === 2) {
            options.colors = [APP_CONFIG.color_invested, APP_CONFIG.color_current];
        }
        
        const chart = new ApexCharts(el, options);
        chart.render();
        chartInstances[id] = chart;
        chartDataStore[id] = { originalSeries: series, roi, categories, title };
    });
}

function renderPieChart(selector, title, labels, series) {
    safeRender(selector, (el) => {
        const options = { 
            chart: { 
                type: 'pie', 
                height: 340, // Slightly less than 380 to account for padding
                background: 'transparent' 
            }, 
            theme: { mode: 'dark' }, 
            series, 
            labels, 
            title: { 
                text: title, 
                align: 'left' 
            }, 
            legend: { 
                ...labelOptions,
                position: 'bottom',
                height: 35,
                offsetY: -10
            }, 
            tooltip: { 
                y: { 
                    formatter: (val) => '$' + Math.round(val).toLocaleString() 
                } 
            },
            responsive: [{
                breakpoint: 1200,
                options: {
                    legend: { fontSize: desktopFontSize }
                }
            }]
        };
        const chart = new ApexCharts(el, options);
        chart.render();
        if (typeof chartInstances !== 'undefined') {
            chartInstances[selector] = chart;
        }
    });
}

function toggleChartMode(id, mode, btn) {
    const chart = chartInstances[id] || symbolCharts[id.replace('und-', '')];
    const data = chartDataStore[id];
    if (!chart || !data) return;
    btn.parentElement.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    
    // If we are coming back from a 'Performance' view (Flow/Income), restore full options
    const isRestoring = chart.opts?.title?.text?.includes('Performance') || !chart.opts?.xaxis?.categories?.includes(data.categories[0]);

    if (mode === 'pct') {
        chart.updateOptions({ 
            series: [{ name: 'ROI %', data: data.roi }], 
            xaxis: { 
                categories: data.categories,
                labels: { rotate: data.categories.length > 5 ? -45 : 0, style: { fontSize: desktopFontSize } }
            },
            yaxis: getYAxisConfig('pct', false), 
            tooltip: { 
                y: { formatter: (val) => Math.round(val) + '%' } 
            }, 
            dataLabels: { 
                enabled: data.categories.length < 24,
                formatter: (v) => Math.round(v) + '%',
                style: { fontSize: desktopFontSize }
            },
            colors: [APP_CONFIG.color_positive], 
            plotOptions: { 
                bar: { 
                    colors: { 
                        ranges: [
                            { from: -999, to: -0.01, color: APP_CONFIG.color_negative }, 
                            { from: 0, to: 999, color: APP_CONFIG.color_positive }
                        ] 
                    } 
                } 
            },
            title: { text: data.title + ' (%)' },
            responsive: getResponsiveConfig('pct')
        });
    } else {
        const colors = data.originalSeries.length === 3 
            ? [APP_CONFIG.color_invested, APP_CONFIG.color_current, APP_CONFIG.color_returns] 
            : [APP_CONFIG.color_invested, APP_CONFIG.color_current];
        
        chart.updateOptions({ 
            series: data.originalSeries, 
            xaxis: { 
                categories: data.categories,
                labels: { rotate: data.categories.length > 5 ? -45 : 0, style: { fontSize: desktopFontSize } }
            },
            yaxis: getYAxisConfig('val', false), 
            tooltip: { 
                y: { formatter: (val) => '$' + Math.round(val).toLocaleString() } 
            }, 
            dataLabels: { 
                enabled: false, 
                formatter: (v) => '$' + Math.round(v).toLocaleString(),
                style: { fontSize: desktopFontSize }
            },
            colors: colors, 
            plotOptions: { 
                bar: { 
                    colors: { ranges: [] } 
                } 
            },
            title: { text: data.title + ' (SGD)' },
            responsive: getResponsiveConfig('val')
        });
    }
}

function updateUnderlyingChart(slug, type, grouping, btn) {
    const id = `und-${slug}`;
    const chart = chartInstances[id];
    const container = document.getElementById(`chart-${id}`);
    if (!chart || !container) return;

    btn.parentElement.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    const symbols = JSON.parse(container.dataset.symbolsData || '[]');
    const { categories, values } = processAggregatedTimeSeries(symbols, type, grouping);

    chart.updateOptions({
        series: [{ name: type === 'flow' ? 'Net Flow' : 'Income', data: values }],
        xaxis: { categories, labels: { rotate: -45, style: { fontSize: desktopFontSize } } },
        yaxis: getYAxisConfig('val', false),
        tooltip: { y: { formatter: (val) => '$' + Math.round(val).toLocaleString() } },
        dataLabels: { 
            enabled: (type === 'flow' && grouping === 'month') ? false : (categories.length < 24), 
            formatter: (v) => '$' + Math.round(v).toLocaleString(),
            style: { fontSize: desktopFontSize }
        },
        colors: [type === 'flow' ? '#3498db' : '#2ecc71'],
        plotOptions: {
            bar: {
                colors: {
                    ranges: [
                        { from: -99999999, to: -0.01, color: '#e74c3c' },
                        { from: 0, to: 99999999, color: '#2ecc71' }
                    ]
                }
            }
        },
        title: { text: `Aggregated Performance (${type === 'flow' ? 'Flow' : 'Income'} - ${grouping}) (SGD)` },
        responsive: getResponsiveConfig('val')
    });
}

function toggleIncomeView(mode, btn) {
    const chart = chartInstances['portfolio-income'];
    const data = chartDataStore['portfolio-income'];
    if (!chart || !data) return;
    btn.parentElement.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');
    
    if (mode === 'monthly') { 
        let lastYear = "";
        const compactLabels = data.monthly.labels.map(label => {
            // Handle both 'YYYY-MM' and 'Month YYYY' formats
            let year, month;
            if (label.includes('-')) {
                [year, month] = label.split('-');
            } else {
                const parts = label.split(' ');
                year = parts[1];
                month = monthNames.indexOf(parts[0].substring(0, 3)) + 1;
            }
            
            const monthName = monthNames[parseInt(month) - 1];
            if (year !== lastYear) { 
                lastYear = year; 
                return `${monthName} ${year}`; 
            }
            return monthName;
        });

        chart.updateOptions({ 
            series: [{ name: 'Monthly Income', data: data.monthly.values }], 
            xaxis: { 
                categories: compactLabels,
                labels: { rotateAlways: true, rotate: -45, style: { ...labelOptions } } 
            } 
        }); 
    } else { 
        chart.updateOptions({ 
            series: [{ name: 'Yearly Income', data: data.yearly.values }], 
            xaxis: { 
                categories: data.yearly.labels,
                labels: { rotateAlways: false, rotate: data.yearly.labels.length > 5 ? -45 : 0, style: { ...labelOptions } }
            } 
        }); 
    }
}

function toggleDailyChart(slug, mode, btn) {
    const chart = chartInstances[`daily-perf-${slug}`];
    const data = chartDataStore[`daily-perf-${slug}`];
    if (!chart || !data) return;

    btn.parentElement.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    const seriesData = mode === 'val' ? data.val : data.pct;
    const name = mode === 'val' ? 'Daily Value Change' : 'Daily % Change';
    const formatter = mode === 'val' ? (v) => '$' + Math.round(v).toLocaleString() : (v) => Math.round(v) + '%';

    chart.updateOptions({
        series: [{ name, data: seriesData }],
        yaxis: getYAxisConfig(mode === 'val' ? 'val' : 'pct', false, true),
        tooltip: { y: { formatter } },
        responsive: getResponsiveConfig(mode === 'val' ? 'val' : 'pct', true)
    });
}

function toggleTopPerformers(type, mode, btn) {
    const chart = chartInstances[`top-${type}`];
    const data = chartDataStore[`top-${type}`];
    if (!chart || !data) return;

    btn.parentElement.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    const key = `${type}_${mode}`;
    const seriesData = data[key].values;
    const labels = data[key].labels;
    const name = mode === 'val' ? 'Daily Value Change' : 'Daily % Change';
    const formatter = mode === 'val' ? (v) => '$' + Math.round(v).toLocaleString() : (v) => Math.round(v) + '%';

    chart.updateOptions({
        series: [{ name, data: seriesData }],
        xaxis: { categories: labels },
        yaxis: getYAxisConfig(mode === 'val' ? 'val' : 'pct', false, true),
        tooltip: { y: { formatter } },
        responsive: getResponsiveConfig(mode === 'val' ? 'val' : 'pct', true)
    });
}

function initCharts(chartData) {
    if (!chartData) return;
    // New Daily Performance Charts
    Object.entries(chartData.daily_performance || {}).forEach(([slug, data]) => {
        safeRender(`#chart-daily-perf-${slug}`, (el) => {
            const options = {
                ...commonOptions,
                chart: { ...commonOptions.chart, height: 400 },
                series: [{ name: 'Daily % Change', data: data.pct }],
                xaxis: { 
                    categories: data.labels,
                    labels: { 
                        rotate: -45,
                        rotateAlways: true,
                        style: { ...labelOptions } 
                    }
                },
                yaxis: getYAxisConfig('pct', false, true),
                tooltip: { 
                    ...commonOptions.tooltip,
                    y: { 
                        formatter: (v) => Math.round(v) + '%'
                    } 
                },
                title: { text: `Daily Performance (%)`, align: 'left' },
                colors: ['#3498db'],
                responsive: getResponsiveConfig('pct', true),
                plotOptions: {
                    bar: {
                        ...commonOptions.plotOptions.bar,
                        colors: {
                            ranges: [
                                { from: -9999999, to: -0.001, color: '#e74c3c' },
                                { from: 0, to: 9999999, color: '#2ecc71' }
                            ]
                        }
                    }
                }
            };
            const chart = new ApexCharts(el, options);
            chart.render();
            chartInstances[`daily-perf-${slug}`] = chart;
            chartDataStore[`daily-perf-${slug}`] = data;
        });
    });

    // Top Gainers / Losers
    if (chartData.top_performers) {
        const renderTop = (type, title) => {
            safeRender(`#chart-top-${type}`, (el) => {
                const dataKey = `${type}_pct`;
                const options = {
                    ...commonOptions,
                    chart: { ...commonOptions.chart, height: 350 },
                    series: [{ name: 'Daily % Change', data: chartData.top_performers[dataKey].values }],
                    xaxis: { 
                        categories: chartData.top_performers[dataKey].labels,
                        labels: { 
                            rotate: -45,
                            rotateAlways: true,
                            style: { ...labelOptions } 
                        }
                    },
                    yaxis: getYAxisConfig('pct', false, true),
                    tooltip: { 
                        ...commonOptions.tooltip,
                        y: { 
                            formatter: (v) => Math.round(v) + '%'
                        } 
                    },
                    title: { text: title + ' (%)', align: 'left' },
                    colors: [type === 'gainers' ? '#2ecc71' : '#e74c3c'],
                    responsive: getResponsiveConfig('pct', true)
                };
                const chart = new ApexCharts(el, options);
                chart.render();
                chartInstances[`top-${type}`] = chart;
                chartDataStore[`top-${type}`] = chartData.top_performers;
            });
        };
        renderTop('gainers', 'Top 10 Gainers');
        renderTop('losers', 'Top 10 Losers');
    }

    const catData = chartData.categories || chartData.subclasses || [];
    renderPieChart(
        "#chart-category-curr-pie", 
        "Category Current Value Allocation", 
        catData.map(s => s.name), 
        catData.map(s => s.curr)
    );
    renderPieChart(
        "#chart-category-inv-pie", 
        "Category Invested Value Allocation", 
        catData.map(s => s.name), 
        catData.map(s => s.inv)
    );
    const countryData = chartData.countries || [];
    renderPieChart(
        "#chart-country-pie", 
        "Country Value Allocation", 
        countryData.map(c => c.name), 
        countryData.map(c => c.value)
    );


    safeRender("#chart-portfolio-income", (el) => {
        let lastYear = "";
        const compactLabels = chartData.portfolio_income.monthly.labels.map(label => {
            // Handle raw YYYY-MM from Python
            const [year, month] = label.split('-');
            const monthName = monthNames[parseInt(month) - 1];
            if (year !== lastYear) { lastYear = year; return `${monthName} ${year}`; }
            return monthName;
        });

        const incOptions = { 
            ...commonOptions, 
            series: [{ 
                name: 'Monthly Income', 
                data: chartData.portfolio_income.monthly.values 
            }], 
            dataLabels: {
                enabled: true,
                offsetY: -20,
                style: {
                    fontSize: desktopFontSize,
                    colors: ["#fff"]
                },
                formatter: (val) => val ? '$' + Math.round(val).toLocaleString() : ''
            },
            plotOptions: {
                bar: {
                    ...commonOptions.plotOptions.bar,
                    dataLabels: {
                        position: 'top',
                    },
                }
            },
            xaxis: { 
                categories: compactLabels, 
                labels: { 
                    rotateAlways: true, 
                    rotate: -45,
                    style: { 
                        ...labelOptions
                    }
                }  
            }, 
            title: { 
                text: 'Portfolio Passive Income (SGD)', 
                align: 'left' 
            }, 
            colors: [APP_CONFIG.color_income]
        };
        const incChart = new ApexCharts(el, incOptions);
        incChart.render();
        chartInstances['portfolio-income'] = incChart;
        chartDataStore['portfolio-income'] = chartData.portfolio_income;
    });

    renderBarChart(
        "#chart-category", 
        "category", 
        "By Category (Global)", 
        catData.map(s => s.name), 
        [
            {name: 'Invested', data: catData.map(s => s.inv)}, 
            {name: 'Current', data: catData.map(s => s.curr)}, 
            {name: 'Total Returns', data: catData.map(s => s.ret)}
        ], 
        catData.map(s => s.roi)
    );
    
    renderBarChart(
        "#chart-growth-strat", 
        "growth-strat", 
        "Growth Strategy Assets", 
        chartData.growth_strategy.labels, 
        [
            {name: 'Invested', data: chartData.growth_strategy.invested}, 
            {name: 'Total Returns', data: chartData.growth_strategy.returns}
        ], 
        chartData.growth_strategy.roi
    );
    
    renderBarChart(
        "#chart-income-strat", 
        "income-strat", 
        "Income Strategy Assets", 
        chartData.income_strategy.labels, 
        [
            {name: 'Invested', data: chartData.income_strategy.invested}, 
            {name: 'Current', data: chartData.income_strategy.current}, 
            {name: 'Total Returns', data: chartData.income_strategy.returns}
        ], 
        chartData.income_strategy.roi
    );

    chartData.classifications.forEach(c => {
        if (c.show_summary) {
            safeRender(`#chart-sum-${c.slug}`, (el) => {
                const options = {
                    ...commonOptions,
                    chart: { ...commonOptions.chart, height: 350 },
                    series: c.summary_series,
                    xaxis: {
                        categories: [c.name],
                        labels: { style: { ...labelOptions } }
                    },
                    dataLabels: {
                        enabled: false,
                        offsetY: -20,
                        style: {
                            fontSize: desktopFontSize,
                            colors: ["#fff"]
                        },
                        formatter: (val) => val ? '$' + Math.round(val).toLocaleString() : ''
                    },
                    plotOptions: {
                        ...commonOptions.plotOptions,
                        bar: {
                            ...commonOptions.plotOptions.bar,
                            dataLabels: {
                                position: 'top',
                            },
                        }
                    },
                    title: { 
                        text: `${c.name} Summary (SGD)`, 
                        align: 'left' 
                    },
                    tooltip: { 
                        y: { 
                            formatter: (val) => '$' + Math.round(val).toLocaleString() 
                        } 
                    },
                    colors: [APP_CONFIG.color_invested, APP_CONFIG.color_current, APP_CONFIG.color_returns],
                    yaxis: getYAxisConfig('val', false),
                    responsive: getResponsiveConfig('val')
                };
                const chart = new ApexCharts(el, options);
                chart.render();
                chartInstances[`sum-${c.slug}`] = chart;
                chartDataStore[`sum-${c.slug}`] = { originalSeries: c.summary_series, roi: [c.roi], categories: [c.name], title: `${c.name} Summary` };
            });
        }
        
        renderBarChart(
            `#chart-und-${c.slug}`, 
            `und-${c.slug}`, 
            `${c.name} Underlyings`, 
            c.underlying.labels, 
            c.underlying_series, 
            c.underlying.roi
        );

        // Render individual underlying charts if they have multiple tickers
        Object.entries(c.underlying_raw || {}).forEach(([uName, uData]) => {
            const slug = uName.toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
            const categories = uData.symbols.map(s => s.symbol);
            const series = [
                { name: 'Invested', data: uData.symbols.map(s => Math.round(s.sgd_metrics.invested_sgd)) },
                { name: 'Current', data: uData.symbols.map(s => Math.round(s.sgd_metrics.current_sgd)) },
                { name: 'Total Returns', data: uData.symbols.map(s => Math.round(s.sgd_metrics.total_returns_sgd)) }
            ];
            renderBarChart(
                `#chart-und-${slug}`, 
                `und-${slug}`, 
                `${uName} Stats`, 
                categories, 
                series, 
                uData.symbols.map(s => s.metrics.roi_pct)
            );
        });
    });
}

/**
 * Logic to process multiple symbols into a single aggregated time-series.
 */
function processAggregatedTimeSeries(symbols, type, grouping) {
    const dataMap = {};
    
    symbols.forEach(s => {
        const rate = parseFloat(s.rate || '1.0');
        const records = (type === 'flow') ? s.transactions : s.income;
        
        records.forEach(r => {
            const key = grouping === 'year' ? r.date.substring(0, 4) : r.date.substring(0, 7);
            let val = 0;
            if (type === 'flow') {
                const flow = (r.qty * r.price + (r.action === 'Buy' ? r.fee : -r.fee)) * rate;
                val = r.action === 'Buy' ? flow : -flow;
            } else {
                val = r.net * rate;
            }
            dataMap[key] = (dataMap[key] || 0) + val;
        });
    });

    let sortedKeys = Object.keys(dataMap).sort();
    
    // Limit to last 12 months
    if (grouping === 'month' && sortedKeys.length > 12) {
        sortedKeys = sortedKeys.slice(-12);
    }

    let lastYear = "";
    const categories = sortedKeys.map(k => {
        if (grouping === 'year') return k;
        const [y, m] = k.split('-');
        const monthName = monthNames[parseInt(m)-1];
        if (y !== lastYear) {
            lastYear = y;
            return `${monthName} ${y}`;
        }
        return monthName;
    });
    const values = sortedKeys.map(k => Math.round(dataMap[k]));

    return { categories, values };
}

const symbolCharts = {};
window.symbolCharts = symbolCharts;

/**
 * Shared logic to process transactions or income into time-series data for charts.
 */
function processTimeSeriesData(records, type, grouping, rate = 1.0) {
    const dataMap = {};
    
    records.forEach(r => {
        const key = grouping === 'year' ? r.date.substring(0, 4) : r.date.substring(0, 7);
        let value = 0;
        
        if (type === 'flow') {
            const flow = (r.qty * r.price + (r.action === 'Buy' ? r.fee : -r.fee)) * rate;
            value = r.action === 'Buy' ? flow : -flow;
        } else {
            value = r.net * rate;
        }
        dataMap[key] = (dataMap[key] || 0) + value;
    });

    let sortedKeys = Object.keys(dataMap).sort();
    
    // Limit to last 12 months
    if (grouping === 'month' && sortedKeys.length > 12) {
        sortedKeys = sortedKeys.slice(-12);
    }

    let lastYear = "";
    const categories = sortedKeys.map(k => {
        if (grouping === 'year') return k;
        const [y, m] = k.split('-');
        const monthName = monthNames[parseInt(m)-1];
        if (y !== lastYear) {
            lastYear = y;
            return `${monthName} ${y}`;
        }
        return monthName;
    });
    const values = sortedKeys.map(k => Math.round(dataMap[k]));

    return { categories, values };
}

function updateSymbolChart(symbol, type, grouping, btn) {
    const slug = symbol.toLowerCase().replace(/[^a-z0-9]/g, '-').replace(/-+/g, '-').replace(/^-|-$/g, '');
    const container = document.getElementById(`chart-${slug}`);
    if (!container) return;

    if (btn) {
        btn.parentElement.querySelectorAll('.toggle-btn').forEach(b => b.classList.remove('active'));
        btn.classList.add('active');
    }

    const txs = JSON.parse(container.dataset.txs || '[]');
    const income = JSON.parse(container.dataset.income || '[]');
    const rate = parseFloat(container.dataset.rate || '1.0');

    const records = (type === 'flow') ? txs : income;
    const { categories, values } = processTimeSeriesData(records, type, grouping, rate);

    if (!symbolCharts[slug]) {
        const options = {
            chart: { type: 'bar', height: 350, background: 'transparent', toolbar: { show: false } },
            theme: { mode: 'dark' },
            series: [{ name: type === 'flow' ? 'Net Flow' : 'Income', data: values }],
            xaxis: { categories, labels: { rotate: -45, style: { fontSize: desktopFontSize } } },
            yaxis: getYAxisConfig('val', false),
            tooltip: { y: { formatter: (val) => '$' + Math.round(val).toLocaleString() } },
            dataLabels: { 
                enabled: values.length < 24, 
                formatter: (v) => '$' + Math.round(v).toLocaleString(), 
                style: { fontSize: desktopFontSize } 
            },
            legend: { fontSize: desktopFontSize },
            colors: [type === 'flow' ? '#3498db' : '#2ecc71'],
            plotOptions: {
                bar: {
                    colors: {
                        ranges: [
                            { from: -99999999, to: -0.01, color: '#e74c3c' },
                            { from: 0, to: 99999999, color: '#2ecc71' }
                        ]
                    }
                }
            },
            title: { text: `${symbol} Performance (${type === 'flow' ? 'Flow' : 'Income'}) (SGD)` },
            responsive: getResponsiveConfig('val')
        };
        symbolCharts[slug] = new ApexCharts(container, options);
        symbolCharts[slug].render();
    } else {
        symbolCharts[slug].updateOptions({
            series: [{ name: type === 'flow' ? 'Net Flow' : 'Income', data: values }],
            xaxis: { categories },
            yaxis: getYAxisConfig('val', false),
            tooltip: { y: { formatter: (val) => '$' + Math.round(val).toLocaleString() } },
            colors: [type === 'flow' ? '#3498db' : '#2ecc71'],
            dataLabels: { 
                enabled: values.length < 24,
                formatter: (v) => '$' + Math.round(v).toLocaleString()
            },
            title: { text: `${symbol} Performance (${type === 'flow' ? 'Flow' : 'Income'}) (SGD)` },
            responsive: getResponsiveConfig('val')
        });
    }
}

// TOC Interaction
document.addEventListener('DOMContentLoaded', () => {
    // Restore TOC view preference
    const savedView = localStorage.getItem('toc_view_preference');
    if (savedView === 'table') {
        toggleTOCView('table');
    }

    // Auto-expand the first month in the closed positions TOC
    const firstMonth = document.querySelector('.toc-month');
    if (firstMonth) firstMonth.classList.add('active');

    // memory-efficient lazy loading: Render on enter, Destroy on exit
    const observer = new IntersectionObserver((entries) => {
        entries.forEach(entry => {
            const container = entry.target;
            const slug = container.id.replace('chart-', '');
            const rawSymbol = container.getAttribute('data-symbol');

            if (entry.isIntersecting) {
                // When coming into view, render if not already there
                if (rawSymbol && !symbolCharts[slug]) {
                    // Slight delay to prioritize scrolling performance
                    setTimeout(() => {
                        if (entry.isIntersecting) updateSymbolChart(rawSymbol, 'flow', 'month');
                    }, 100);
                }
            } else {
                // When far out of view, destroy instance to free RAM
                if (symbolCharts[slug]) {
                    symbolCharts[slug].destroy();
                    delete symbolCharts[slug];
                    // Keep the container height to prevent layout shift
                    container.style.minHeight = '350px';
                }
            }
        });
    }, { 
        rootMargin: '200px 0px', // Start loading 200px before it enters
        threshold: 0.01 
    });

    document.querySelectorAll('.symbol-chart-container').forEach(el => observer.observe(el));
});

// --- Transaction History Specific Logic ---

let transactionChart = null;

function toggleLevel(level, isOpen) {
    let selector = "";
    if (level === 1) selector = ".main-content > details";
    if (level === 2) selector = ".main-content > details > details";
    if (level === 3) selector = ".main-content > details > details > details";
    
    const elements = document.querySelectorAll(selector);
    elements.forEach(d => {
        d.open = isOpen;
        if (isOpen) {
            let parent = d.parentElement;
            while (parent && parent.tagName === 'DETAILS') {
                parent.open = true;
                parent = parent.parentElement;
            }
        } else {
            d.querySelectorAll('details').forEach(child => child.open = false);
        }
    });
}

function clearTxSearch() {
    const input = document.getElementById('tx-search');
    if (input) {
        input.value = "";
        filterTransactions();
    }
}

function filterTransactions() {
    const input = document.getElementById('tx-search');
    if (!input) return;
    const filter = input.value.toUpperCase();
    const isReset = filter === "";
    
    // 1. Memory Filtering & Tallying
    const visibleTxIds = new Set();
    const yearTallies = {};
    const monthTallies = {};
    const undTallies = {};
    let globalExp = 0;
    let globalInc = 0;

    // Fast pass: Filter memory index and accumulate totals
    txIndex.forEach(tx => {
        if (isReset || tx.search.indexOf(filter) > -1) {
            visibleTxIds.add(tx.id);
            
            // accumulate totals
            yearTallies[tx.year] = (yearTallies[tx.year] || 0) + tx.flow;
            monthTallies[tx.month] = (monthTallies[tx.month] || 0) + tx.flow;
            undTallies[tx.und] = (undTallies[tx.und] || 0) + tx.flow;

            if (tx.flow > 0) globalExp += tx.flow;
            else globalInc += Math.abs(tx.flow);
        }
    });

    // 2. DOM Updates (Bulk pass)
    // Toggle transaction records
    document.querySelectorAll('.tx-item').forEach(li => {
        li.style.display = visibleTxIds.has(li.id) ? "" : "none";
    });

    // Toggle folders and update headers
    const mainContent = document.querySelector('.main-content');
    const years = mainContent.querySelectorAll(':scope > details');

    years.forEach(year => {
        const yearSpan = year.querySelector('.year-total');
        const yearId = yearSpan.dataset.year;
        const yearVisible = yearTallies[yearId] !== undefined;

        year.style.display = (yearVisible || isReset) ? "" : "none";
        if (yearVisible && !isReset) year.open = true;
        updateDynamicSpan(yearSpan, yearTallies[yearId] || 0, isReset);

        const months = year.querySelectorAll(':scope > details');
        months.forEach(month => {
            const monthSpan = month.querySelector('.month-total');
            const monthId = monthSpan.dataset.monthId;
            const monthVisible = monthTallies[monthId] !== undefined;

            month.style.display = (monthVisible || isReset) ? "" : "none";
            if (monthVisible && !isReset) month.open = true;
            updateDynamicSpan(monthSpan, monthTallies[monthId] || 0, isReset);

            const underlyings = month.querySelectorAll(':scope > details');
            underlyings.forEach(und => {
                const undSpan = und.querySelector('.underlying-total');
                const undId = undSpan.dataset.undId;
                const undVisible = undTallies[undId] !== undefined;

                und.style.display = (undVisible || isReset) ? "" : "none";
                if (undVisible && !isReset) und.open = true;
                updateDynamicSpan(undSpan, undTallies[undId] || 0, isReset);
            });
        });
    });

    // Sidebar & Chart
    const clearBtn = document.getElementById('clear-tx-search');
    if (clearBtn) clearBtn.style.display = isReset ? "none" : "block";

    updateGlobalSummary(globalExp, globalInc, isReset);

    let noResults = document.getElementById('no-tx-results-msg');
    if (!noResults) {
        noResults = document.createElement('div');
        noResults.id = 'no-tx-results-msg';
        noResults.innerHTML = '<div style="padding: 40px; text-align: center; background: var(--card-bg); border-radius: 8px; margin-top: 20px;"><h3>No transactions found matching your search.</h3></div>';
        mainContent.appendChild(noResults);
    }
    noResults.style.display = (visibleTxIds.size === 0 && !isReset) ? "block" : "none";
    if (transactionChart) updateTxChart();
}

function updateGlobalSummary(exp, inc, isReset) {
    const expEl = document.getElementById('global-expense');
    const incEl = document.getElementById('global-income');
    const netEl = document.getElementById('global-net');
    if (!expEl || !incEl || !netEl) return;

    let finalExp, finalInc, finalNet;
    if (isReset) {
        finalExp = parseFloat(expEl.dataset.orig);
        finalInc = parseFloat(incEl.dataset.orig);
        finalNet = parseFloat(netEl.dataset.orig);
    } else {
        finalExp = exp;
        finalInc = inc;
        finalNet = exp - inc;
    }

    expEl.innerText = `${finalExp.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} SGD`;
    incEl.innerText = `${finalInc.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} SGD`;
    netEl.innerText = `${finalNet.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} SGD`;
    
    netEl.classList.remove('pos-flow', 'neg-flow');
    if (finalNet > 0) netEl.classList.add('pos-flow');
    else if (finalNet < 0) netEl.classList.add('neg-flow');

    expEl.classList.add('pos-flow');
    incEl.classList.add('neg-flow');
}

function updateDynamicSpan(span, value, isReset) {
    let val = isReset ? parseFloat(span.dataset.orig) : value;
    span.innerText = `${val.toLocaleString(undefined, {minimumFractionDigits: 2, maximumFractionDigits: 2})} SGD`;
    span.classList.remove('pos-flow', 'neg-flow');
    if (val > 0) span.classList.add('pos-flow');
    else if (val < 0) span.classList.add('neg-flow');
}

function toggleTxChart() {
    const wrapper = document.getElementById('chart-wrapper'), btn = document.getElementById('chart-btn');
    if (!wrapper || !btn) return;
    if (wrapper.style.display === 'none') {
        wrapper.style.display = 'block'; btn.innerText = '📊 Hide Filtered Chart';
        initTxChart();
        setTimeout(() => { wrapper.scrollIntoView({ behavior: 'smooth', block: 'start' }); }, 100);
    } else {
        wrapper.style.display = 'none'; btn.innerText = '📊 Show Filtered Chart';
    }
}

function initTxChart() {
    if (transactionChart) return updateTxChart();
    const options = {
        chart: { type: 'bar', height: 450, theme: 'dark', background: 'transparent', toolbar: { show: false } },
        theme: { mode: 'dark' }, series: [],
        xaxis: { categories: [], labels: { style: { colors: '#888', fontSize: desktopFontSize }, rotate: -45, rotateAlways: false } },
        yaxis: getYAxisConfig('val', false),
        dataLabels: { enabled: true, formatter: (val) => '$' + Math.round(val).toLocaleString(), style: { fontSize: desktopFontSize, colors: ["#fff"] }, offsetY: -20 },
        title: { text: 'Monthly Net Flow (Filtered) (SGD)', align: 'left', style: { color: '#e0e0e0' } },
        colors: ['#3498db'],
        plotOptions: { bar: { dataLabels: { position: 'top' }, colors: { ranges: [{ from: -9999999, to: -0.01, color: '#e74c3c' }, { from: 0, to: 9999999, color: '#2ecc71' }] } } },
        responsive: getResponsiveConfig('val')
    };
    transactionChart = new ApexCharts(document.querySelector("#filtered-chart"), options);
    transactionChart.render().then(() => updateTxChart());
}

function updateTxChart() {
    const visibleTxs = document.querySelectorAll('.tx-item:not([style*="display: none"])');
    const monthlyData = {}; 
    visibleTxs.forEach(tx => {
        const dateParts = tx.dataset.month.split('-'); 
        const label = tx.dataset.month;
        const flow = parseFloat(tx.dataset.flow);
        monthlyData[label] = (monthlyData[label] || 0) + flow;
    });
    const sortedKeys = Object.keys(monthlyData).sort();
    let lastYear = "";
    const displayLabels = sortedKeys.map(key => {
        const [year, month] = key.split('-');
        const monthName = monthNames[parseInt(month) - 1];
        if (year !== lastYear) { lastYear = year; return `${monthName} ${year}`; }
        return monthName;
    });
    const values = sortedKeys.map(k => Math.round(monthlyData[k]));
    transactionChart.updateOptions({ xaxis: { categories: displayLabels }, series: [{ name: 'Net Flow (SGD)', data: values }], tooltip: { y: { formatter: (val) => '$' + Math.round(val).toLocaleString() } } });
}

function clearTickerSearch() {
    const input = document.getElementById('ticker-search');
    if (input) {
        input.value = "";
        filterTickers();
    }
}

function filterTickers() {
    const input = document.getElementById('ticker-search');
    if (!input) return;
    const filter = input.value.toUpperCase();
    
    // Show/hide clear button
    const clearBtn = document.getElementById('clear-ticker-search');
    if (clearBtn) clearBtn.style.display = filter !== "" ? "block" : "none";

    // 1. Filter the Table of Contents
    const tocLinks = document.querySelectorAll('.toc-month-content li');
    tocLinks.forEach(li => {
        const text = (li.textContent || li.innerText).toUpperCase();
        li.style.display = text.indexOf(filter) > -1 ? "" : "none";
    });

    // Auto-expand months that have visible results
    document.querySelectorAll('.toc-month').forEach(monthHeader => {
        const content = monthHeader.nextElementSibling;
        const visibleItems = content.querySelectorAll('li:not([style*="display: none"])');
        if (filter !== "" && visibleItems.length > 0) {
            monthHeader.classList.add('active');
        } else if (filter === "") {
            // Keep first month active by default if no filter
            if (monthHeader === document.querySelector('.toc-month')) monthHeader.classList.add('active');
        } else {
            monthHeader.classList.remove('active');
        }
    });

    // 2. Filter the main content area
    const performanceContainer = document.querySelector('.performance-container');
    if (!performanceContainer) return;

    let totalVisible = 0;
    const underlyingSections = performanceContainer.querySelectorAll('.underlying-section');

    if (underlyingSections.length > 0) {
        // Active layout: filter by underlying-section wrappers
        underlyingSections.forEach(section => {
            const searchData = (section.getAttribute('data-search') || "").toUpperCase();
            const symbolsText = Array.from(section.querySelectorAll('h2')).map(h2 => h2.innerText).join(" ").toUpperCase();
            if (searchData.indexOf(filter) > -1 || symbolsText.indexOf(filter) > -1 || filter === "") {
                section.style.display = "";
                totalVisible++;
            } else {
                section.style.display = "none";
            }
        });

        // Hide empty group headers
        document.querySelectorAll('.report-group').forEach(group => {
            const visible = group.querySelectorAll('.underlying-section:not([style*="display: none"])');
            group.style.display = (filter !== "" && visible.length === 0) ? "none" : "";
        });
    } else {
        // Closed flat layout: filter individual symbol-card-header h2 elements
        // Wrap each h2+siblings as a logical card block using hr separators
        const symbolHeaders = performanceContainer.querySelectorAll('.symbol-card-header');
        symbolHeaders.forEach(h2 => {
            const text = h2.innerText.toUpperCase();
            const show = filter === "" || text.indexOf(filter) > -1;
            // Walk siblings until next h2 or hr that precedes the next h2
            let node = h2;
            while (node) {
                if (node !== h2 && node.nodeType === 1 && node.classList.contains('symbol-card-header')) break;
                if (node.nodeType === 1) node.style.display = show ? "" : "none";
                node = node.nextElementSibling;
            }
            if (show) totalVisible++;
        });

        // Hide empty group headers
        document.querySelectorAll('.report-group').forEach(group => {
            const visible = group.querySelectorAll('.symbol-card-header:not([style*="display: none"])');
            group.style.display = (filter !== "" && visible.length === 0) ? "none" : "";
        });
    }

    // Show/hide "No results" message
    let noResults = document.getElementById('no-results-msg');
    if (!noResults) {
        noResults = document.createElement('div');
        noResults.id = 'no-results-msg';
        noResults.innerHTML = '<div style="padding: 40px; text-align: center; background: var(--card-bg); border-radius: 8px; margin-top: 20px;"><h3>No tickers found matching your search.</h3></div>';
        performanceContainer.appendChild(noResults);
    }
    noResults.style.display = (totalVisible === 0 && filter !== "") ? "block" : "none";
}

function updateTimeAgos() {
    document.querySelectorAll('.timeago').forEach(el => {
        const dtStr = el.getAttribute('data-datetime');
        if (!dtStr) return;
        
        let cleanDtStr = dtStr;
        let isSGT = false;
        if (dtStr.includes(' SGT')) {
            cleanDtStr = dtStr.replace(' SGT', '');
            isSGT = true;
        }
        
        let dateVal;
        if (isSGT) {
            const isoStr = cleanDtStr.trim().replace(' ', 'T') + '+08:00';
            dateVal = new Date(isoStr);
        } else {
            dateVal = new Date(cleanDtStr);
        }
        
        if (isNaN(dateVal.getTime())) return;
        
        // Always format the base date in SGT: dd MMM hh:mm AM/PM
        // e.g. "25 Jun 06:18PM"
        let formattedDate = "";
        try {
            const options = {
                timeZone: 'Asia/Singapore',
                day: '2-digit',
                month: 'short',
                hour: '2-digit',
                minute: '2-digit',
                hour12: true
            };
            const formatter = new Intl.DateTimeFormat('en-SG', options);
            const parts = formatter.formatToParts(dateVal);
            
            let day = "", month = "", hour = "", minute = "", dayPeriod = "";
            for (const part of parts) {
                if (part.type === 'day') day = part.value;
                if (part.type === 'month') month = part.value;
                if (part.type === 'hour') hour = part.value;
                if (part.type === 'minute') minute = part.value;
                if (part.type === 'dayPeriod') dayPeriod = part.value.toUpperCase();
            }
            
            // Format to: dd MMM hh:mm AM/PM (e.g. 25 Jun 06:18PM)
            formattedDate = `${day} ${month} ${hour}:${minute} ${dayPeriod}`;
        } catch (e) {
            formattedDate = dtStr;
        }
        
        const now = new Date();
        const diffMs = now.getTime() - dateVal.getTime();
        const diffSecs = Math.floor(diffMs / 1000);
        const diffMins = Math.floor(diffSecs / 60);
        const diffHours = Math.floor(diffMins / 60);
        const diffDays = Math.floor(diffHours / 24);
        
        let text = '';
        if (diffSecs < 60) {
            text = 'just now';
        } else if (diffMins < 60) {
            text = `${diffMins}m ago`;
        } else if (diffHours < 24) {
            text = `${diffHours}h ago`;
        } else {
            text = `${diffDays}d ago`;
        }
        
        el.textContent = `${formattedDate} (${text})`;
    });
}

document.addEventListener('DOMContentLoaded', () => {
    updateTimeAgos();
    // Re-check periodically
    setInterval(updateTimeAgos, 60000);
});

/* --- Ticker Utilities & Interactive Position Calculator Logic --- */
let calcTickers = [];
let calcTotalPortfolioValue = 0;

function toggleTickerMenu(symbol, event) {
    if (event) {
        event.stopPropagation();
    }
    const menu = document.getElementById(`ticker-menu-${symbol}`);
    if (!menu) return;
    const isVisible = menu.style.display === 'block';
    
    // Hide all menus first
    document.querySelectorAll('.ticker-menu-dropdown').forEach(dropdown => {
        dropdown.style.display = 'none';
    });
    
    // Toggle current
    menu.style.display = isVisible ? 'none' : 'block';
}

function addTickerToCalculator(tickerData, event) {
    if (event) {
        event.stopPropagation();
    }
    
    // Hide dropdown menu
    document.querySelectorAll('.ticker-menu-dropdown').forEach(dropdown => {
        dropdown.style.display = 'none';
    });
    
    const symbol = tickerData.symbol;
    const currency = tickerData.currency;
    const price = parseFloat(tickerData.price) || 0;
    const qty = parseFloat(tickerData.qty) || 0;
    const rate = parseFloat(tickerData.rate) || 1.0;
    const exchange = tickerData.exchange || "";
    
    // Store/update total portfolio value
    calcTotalPortfolioValue = parseFloat(tickerData.totalMarket) || 0;
    
    let existing = calcTickers.find(t => t.symbol === symbol);
    if (!existing) {
        calcTickers.push({
            symbol: symbol,
            currency: currency,
            price: price,
            qty: qty,
            rate: rate,
            exchange: exchange,
            simShares: 0
        });
    } else {
        // Update existing info
        existing.price = price;
        existing.qty = qty;
        existing.rate = rate;
        existing.exchange = exchange;
    }
    
    const widget = document.getElementById('portfolio-calculator-widget');
    if (widget) {
        widget.style.display = 'flex';
        widget.classList.remove('minimized');
    }
    
    renderCalculatorTable();
}

function removeTickerColumn(symbol, event) {
    if (event) {
        event.stopPropagation();
    }
    calcTickers = calcTickers.filter(t => t.symbol !== symbol);
    if (calcTickers.length === 0) {
        closeCalculator(event);
    } else {
        renderCalculatorTable();
    }
}

function toggleMinimizeCalculator(event) {
    // If the close button, expand button, or other controls inside the header are clicked, let their handlers run
    if (event && (event.target.id === 'calc-close-btn' || event.target.id === 'calc-expand-btn' || event.target.closest('.calc-col-remove') || event.target.closest('.calc-input') || event.target.closest('.lot-guide'))) {
        return;
    }
    if (event) {
        event.stopPropagation();
    }
    const widget = document.getElementById('portfolio-calculator-widget');
    const backdrop = document.getElementById('calc-backdrop');
    if (widget) {
        widget.classList.toggle('minimized');
        if (widget.classList.contains('minimized')) {
            widget.classList.remove('expanded');
            if (backdrop) backdrop.style.display = 'none';
        }
    }
}

function closeCalculator(event) {
    if (event) {
        event.stopPropagation();
    }
    const widget = document.getElementById('portfolio-calculator-widget');
    const backdrop = document.getElementById('calc-backdrop');
    if (widget) {
        widget.style.display = 'none';
        widget.classList.remove('expanded');
    }
    if (backdrop) {
        backdrop.style.display = 'none';
    }
}

function toggleExpandCalculator(event) {
    if (event) {
        event.stopPropagation();
    }
    const widget = document.getElementById('portfolio-calculator-widget');
    const backdrop = document.getElementById('calc-backdrop');
    if (!widget) return;

    // If currently minimized, maximize first
    if (widget.classList.contains('minimized')) {
        widget.classList.remove('minimized');
    }

    widget.classList.toggle('expanded');
    
    if (backdrop) {
        backdrop.style.display = widget.classList.contains('expanded') ? 'block' : 'none';
    }
}

function populateSimShares(symbol, value) {
    const input = document.querySelector(`.calc-input[data-symbol="${symbol}"][data-field="simShares"]`);
    if (input) {
        input.value = value;
        // Trigger calculations update
        handleCalculatorInput();
    }
}

function renderCalculatorTable() {
    const trHeaders = document.getElementById('calc-tr-headers');
    const rowCurrency = document.getElementById('calc-row-currency');
    const rowPrice = document.getElementById('calc-row-price');
    const rowPosition = document.getElementById('calc-row-position');
    const rowWeight = document.getElementById('calc-row-weight');
    const rowSimulate = document.getElementById('calc-row-simulate');
    const rowTxNative = document.getElementById('calc-row-tx-native');
    const rowTxSGD = document.getElementById('calc-row-tx-sgd');
    const rowNewWeight = document.getElementById('calc-row-new-weight');
    const rowWeightChange = document.getElementById('calc-row-weight-change');
    const rowStockChange = document.getElementById('calc-row-stock-change');

    if (!trHeaders || !rowCurrency || !rowPrice || !rowPosition || !rowWeight || 
        !rowSimulate || !rowTxNative || !rowTxSGD || !rowNewWeight || !rowWeightChange || !rowStockChange) return;

    // Reset table structure
    trHeaders.innerHTML = '<th class="sticky-col">Fields</th>';
    rowCurrency.innerHTML = '<td class="sticky-col">Currency</td>';
    rowPrice.innerHTML = '<td class="sticky-col">Current Share Price</td>';
    rowPosition.innerHTML = '<td class="sticky-col">Current Positions</td>';
    rowWeight.innerHTML = '<td class="sticky-col">Current Weight</td>';
    rowSimulate.innerHTML = '<td class="sticky-col">Simulated Action (Shares)</td>';
    rowTxNative.innerHTML = '<td class="sticky-col">Transacted Amt</td>';
    rowTxSGD.innerHTML = '<td class="sticky-col">Transacted Amt (SGD)</td>';
    rowNewWeight.innerHTML = '<td class="sticky-col">New Weight</td>';
    rowWeightChange.innerHTML = '<td class="sticky-col">Weightage Change</td>';
    rowStockChange.innerHTML = '<td class="sticky-col">Position Change %</td>';

    // Update count display
    const countSpan = document.getElementById('calc-count');
    if (countSpan) countSpan.textContent = calcTickers.length;

    calcTickers.forEach(t => {
        // Ticker header cell
        const th = document.createElement('th');
        th.innerHTML = `${t.symbol} <span class="calc-col-remove" onclick="removeTickerColumn('${t.symbol}', event)">×</span>`;
        trHeaders.appendChild(th);

        // Currency cell
        const tdCurrency = document.createElement('td');
        tdCurrency.textContent = t.currency;
        rowCurrency.appendChild(tdCurrency);

        // Price input cell
        const tdPrice = document.createElement('td');
        tdPrice.innerHTML = `<input type="number" step="any" class="calc-input" data-symbol="${t.symbol}" data-field="price" value="${t.price}">`;
        rowPrice.appendChild(tdPrice);

        // Position cell
        const tdPosition = document.createElement('td');
        tdPosition.id = `calc-cell-position-${t.symbol}`;
        rowPosition.appendChild(tdPosition);

        // Current Weight cell
        const tdWeight = document.createElement('td');
        tdWeight.id = `calc-cell-curr-weight-${t.symbol}`;
        rowWeight.appendChild(tdWeight);

        // Simulated action input cell
        const tdSimulate = document.createElement('td');
        tdSimulate.innerHTML = `
            <input type="number" step="any" class="calc-input" data-symbol="${t.symbol}" data-field="simShares" value="${t.simShares}">
            <span class="lot-guide" id="lot-guide-${t.symbol}"></span>
        `;
        rowSimulate.appendChild(tdSimulate);

        // Transacted Native cell
        const tdTxNative = document.createElement('td');
        tdTxNative.id = `calc-cell-tx-native-${t.symbol}`;
        rowTxNative.appendChild(tdTxNative);

        // Transacted SGD cell
        const tdTxSGD = document.createElement('td');
        tdTxSGD.id = `calc-cell-tx-sgd-${t.symbol}`;
        rowTxSGD.appendChild(tdTxSGD);

        // New Weight cell
        const tdNewWeight = document.createElement('td');
        tdNewWeight.id = `calc-cell-new-weight-${t.symbol}`;
        rowNewWeight.appendChild(tdNewWeight);

        // Weightage Change cell
        const tdWeightChange = document.createElement('td');
        tdWeightChange.id = `calc-cell-weight-change-${t.symbol}`;
        rowWeightChange.appendChild(tdWeightChange);

        // Position Change cell
        const tdStockChange = document.createElement('td');
        tdStockChange.id = `calc-cell-stock-change-${t.symbol}`;
        rowStockChange.appendChild(tdStockChange);
    });

    // Attach event listeners to all newly created inputs
    const inputs = document.querySelectorAll('#calc-comparison-table .calc-input');
    inputs.forEach(input => {
        input.addEventListener('input', handleCalculatorInput);
    });

    // Run initial calculations
    updateCalculatorCalculations();
}

function handleCalculatorInput() {
    // Update internal calcTickers state with current input values
    calcTickers.forEach(t => {
        const inputPrice = document.querySelector(`.calc-input[data-symbol="${t.symbol}"][data-field="price"]`);
        const inputSim = document.querySelector(`.calc-input[data-symbol="${t.symbol}"][data-field="simShares"]`);
        if (inputPrice) t.price = parseFloat(inputPrice.value) || 0;
        if (inputSim) t.simShares = parseFloat(inputSim.value) || 0;
    });

    // Recalculate and update the UI cell contents
    updateCalculatorCalculations();
}

function updateCalculatorCalculations() {
    // 1. Calculate sum of all transacted SGD values to adjust the portfolio denominator
    let totalTxSgd = 0;
    calcTickers.forEach(t => {
        const txNative = t.simShares * t.price;
        const txSGD = txNative * t.rate;
        totalTxSgd += txSGD;
    });

    const adjustedPortfolioValue = calcTotalPortfolioValue + totalTxSgd;

    // 2. Update each column
    calcTickers.forEach(t => {
        // Canadian and Singapore lot size mapping
        const isCanadian = (t.currency === 'CAD' || t.exchange === 'TO' || t.exchange === 'V' || t.symbol.endsWith('.TO') || t.symbol.endsWith('.V') || t.symbol.includes('-U') || t.symbol.includes('.U'));
        const isSingapore = (t.currency === 'SGD' || t.exchange === 'SG' || t.symbol.endsWith('.SI'));
        const lotSize = (isCanadian || isSingapore) ? 100 : 1;
        
        const isLotViolated = t.simShares !== 0 && (t.simShares % lotSize !== 0);

        // Highlight input warning
        const inputSim = document.querySelector(`.calc-input[data-symbol="${t.symbol}"][data-field="simShares"]`);
        const guideSpan = document.getElementById(`lot-guide-${t.symbol}`);
        
        if (inputSim) {
            if (isLotViolated) {
                inputSim.classList.add('warning');
            } else {
                inputSim.classList.remove('warning');
            }
        }
        
        if (guideSpan) {
            let guideHTML = `Lot size: ${lotSize}`;
            if (t.qty > 0) {
                guideHTML += ` | <span style="text-decoration: underline; cursor: pointer; color: var(--accent-primary, #8b5cf6); font-weight: 600;" onclick="populateSimShares('${t.symbol}', ${-t.qty})">Max: -${t.qty.toLocaleString(undefined, {minimumFractionDigits: 0, maximumFractionDigits: 4})}</span>`;
            }
            if (isLotViolated) {
                guideSpan.innerHTML = `⚠️ Lot violates size of ${lotSize}<br>${guideHTML}`;
                guideSpan.className = 'lot-guide warning';
            } else {
                guideSpan.innerHTML = guideHTML;
                guideSpan.className = 'lot-guide';
            }
        }

        // Calculations
        const currSGDVal = t.qty * t.price * t.rate;
        const currWeight = calcTotalPortfolioValue > 0 ? (currSGDVal / calcTotalPortfolioValue * 100) : 0;
        
        const txNative = t.simShares * t.price;
        const txSGD = txNative * t.rate;
        
        const displayTxNative = -1 * txNative;
        const displayTxSGD = -1 * txSGD;
        
        const newPositionVal = currSGDVal + txSGD;
        const newWeight = adjustedPortfolioValue > 0 ? (newPositionVal / adjustedPortfolioValue * 100) : 0;
        const weightChange = newWeight - currWeight;

        // Populate cells
        const cellPosition = document.getElementById(`calc-cell-position-${t.symbol}`);
        if (cellPosition) {
            cellPosition.textContent = t.qty.toLocaleString(undefined, { minimumFractionDigits: 0, maximumFractionDigits: 4 });
        }

        const cellCurrWeight = document.getElementById(`calc-cell-curr-weight-${t.symbol}`);
        if (cellCurrWeight) {
            cellCurrWeight.textContent = `${currWeight.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
        }

        const cellTxNative = document.getElementById(`calc-cell-tx-native-${t.symbol}`);
        if (cellTxNative) {
            const formattedTxNative = displayTxNative.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: 'always' });
            cellTxNative.textContent = `${formattedTxNative} ${t.currency}`;
            cellTxNative.className = '';
            if (displayTxNative > 0.0001) {
                cellTxNative.classList.add('pos-val');
            } else if (displayTxNative < -0.0001) {
                cellTxNative.classList.add('neg-val');
            }
        }

        const cellTxSGD = document.getElementById(`calc-cell-tx-sgd-${t.symbol}`);
        if (cellTxSGD) {
            const formattedTxSGD = displayTxSGD.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: 'always' });
            cellTxSGD.textContent = `${formattedTxSGD} SGD`;
            cellTxSGD.className = '';
            if (displayTxSGD > 0.0001) {
                cellTxSGD.classList.add('pos-val');
            } else if (displayTxSGD < -0.0001) {
                cellTxSGD.classList.add('neg-val');
            }
        }

        const cellNewWeight = document.getElementById(`calc-cell-new-weight-${t.symbol}`);
        if (cellNewWeight) {
            cellNewWeight.textContent = `${newWeight.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`;
        }

        const cellWeightChange = document.getElementById(`calc-cell-weight-change-${t.symbol}`);
        if (cellWeightChange) {
            const formattedWeightChange = weightChange.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: 'always' });
            cellWeightChange.textContent = `${formattedWeightChange}%`;
            cellWeightChange.className = ''; // Reset class
            if (weightChange > 0.0001) {
                cellWeightChange.classList.add('pos-val');
            } else if (weightChange < -0.0001) {
                cellWeightChange.classList.add('neg-val');
            }
        }

        const cellStockChange = document.getElementById(`calc-cell-stock-change-${t.symbol}`);
        if (cellStockChange) {
            if (t.qty > 0) {
                const stockChange = (t.simShares / t.qty) * 100;
                const formattedStockChange = stockChange.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2, signDisplay: 'always' });
                cellStockChange.textContent = `${formattedStockChange}%`;
                cellStockChange.className = ''; // Reset class
                if (stockChange > 0.0001) {
                    cellStockChange.classList.add('pos-val');
                } else if (stockChange < -0.0001) {
                    cellStockChange.classList.add('neg-val');
                }
            } else {
                cellStockChange.textContent = t.simShares > 0 ? 'New' : '-';
                cellStockChange.className = t.simShares > 0 ? 'pos-val' : '';
            }
        }
    });
}

// Global click event to close dropdowns when clicking outside
window.addEventListener('click', (e) => {
    if (!e.target.closest('.ticker-menu-container')) {
        document.querySelectorAll('.ticker-menu-dropdown').forEach(dropdown => {
            dropdown.style.display = 'none';
        });
    }
});

window.openModal = function(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.add("show");
};
window.closeModal = function(id) {
    const modal = document.getElementById(id);
    if (modal) modal.classList.remove("show");
};



// =============================================================================
// TX Visualizer
// =============================================================================

let _txvChart = null;          // ApexCharts instance (destroyed on each open)
let _txvState = {              // Persisted across range switches within one open
    symbol: "",
    avgCost: 0,
    currency: "",
    transactions: [],
    activeRange: "1y",
};

/** Read transaction annotations from the DOM symbol card closest to the button */
function _txvGetTransactions(btnEl) {
    // Walk up to symbol-card-lower → find tx-details-wrapper elements
    const lower = btnEl.closest(".symbol-card-lower");
    if (!lower) return [];
    const txs = [];
    lower.querySelectorAll(".tx-details-wrapper").forEach(wrapper => {
        const year = wrapper.getAttribute("data-year");
        // Transactions are lazy-loaded; read from the rendered table if available,
        // otherwise we only have year-level data (no individual markers needed at year precision).
        // The per-tx data is already encoded in the page via the performance chart tojson filter.
        // We'll rely on the data stored in the symbol analytics chart dataset instead.
        // Keep a placeholder; actual data is fetched from the chart store below.
    });

    // Prefer reading from performance chart data store (already JSON-encoded in page)
    const slug = btnEl.dataset.symbol.toLowerCase().replace(/[^a-z0-9]/g, "-");
    if (window.txDataBySlug && window.txDataBySlug[slug]) {
        return window.txDataBySlug[slug];
    }
    return [];
}

/**
 * Open the TX Visualizer modal for a given symbol.
 * @param {HTMLElement} btnEl  – the clicked .txv-trigger-btn element
 */
window.openTxVisualizer = async function(btnEl) {
    const symbol   = btnEl.dataset.symbol   || "";
    const avgCost  = parseFloat(btnEl.dataset.avgCost  || 0);
    const currency = btnEl.dataset.currency || "";

    let transactions = [];
    try {
        if (btnEl.dataset.txs) {
            transactions = JSON.parse(btnEl.dataset.txs);
        }
    } catch (e) {
        console.error("Failed to parse transactions JSON on button:", e);
    }

    _txvState.symbol       = symbol;
    _txvState.avgCost      = avgCost;
    _txvState.currency     = currency;
    _txvState.transactions = transactions;
    _txvState.activeRange  = "1y";

    // Update modal header
    document.getElementById("txv-symbol-label").textContent = symbol;
    document.getElementById("txv-avg-cost-label").textContent =
        avgCost > 0 ? `Avg cost: ${currency} ${avgCost.toFixed(4)}` : "";

    // Hide custom range inputs and clear values
    const customInputs = document.getElementById("txv-custom-date-inputs");
    if (customInputs) customInputs.style.display = "none";
    const toggleBtnEl = document.getElementById("txv-custom-toggle-btn");
    if (toggleBtnEl) toggleBtnEl.classList.remove("txv-range-active");
    const startInput = document.getElementById("txv-start-date");
    const endInput = document.getElementById("txv-end-date");
    if (startInput) startInput.value = "";
    if (endInput) endInput.value = "";

    // Reset active range button
    document.querySelectorAll(".txv-range-btn").forEach(b => {
        b.classList.toggle("txv-range-active", b.dataset.range === "6m");
    });

    openModal("txv-modal");
    await _txvLoadAndRender("6m");
};

window.closeTxVisualizer = function() {
    closeModal("txv-modal");
    if (_txvChart) { _txvChart.destroy(); _txvChart = null; }
};

/** Wire up range button clicks once the modal exists */
document.addEventListener("DOMContentLoaded", () => {
    // Wire up range button clicks (excluding the calendar toggle and apply button)
    document.querySelectorAll(".txv-range-btn:not(#txv-custom-toggle-btn):not(#txv-apply-custom-btn)").forEach(btn => {
        btn.addEventListener("click", async () => {
            // Hide custom inputs when switching back to predefined range
            const customInputs = document.getElementById("txv-custom-date-inputs");
            if (customInputs) customInputs.style.display = "none";
            const toggleBtn = document.getElementById("txv-custom-toggle-btn");
            if (toggleBtn) toggleBtn.classList.remove("txv-range-active");

            const range = btn.dataset.range;
            document.querySelectorAll(".txv-range-btn").forEach(b =>
                b.classList.toggle("txv-range-active", b === btn));
            _txvState.activeRange = range;
            await _txvLoadAndRender(range);
        });
    });

    // Toggle custom date range inputs display
    const toggleBtn = document.getElementById("txv-custom-toggle-btn");
    if (toggleBtn) {
        toggleBtn.addEventListener("click", () => {
            const inputs = document.getElementById("txv-custom-date-inputs");
            if (inputs) {
                const isHidden = inputs.style.display === "none";
                inputs.style.display = isHidden ? "flex" : "none";
                
                // Toggle active class on toggle button
                toggleBtn.classList.toggle("txv-range-active", isHidden);
                if (isHidden) {
                    // Deactivate predefined range buttons
                    document.querySelectorAll(".txv-range-btn:not(#txv-custom-toggle-btn)").forEach(b => {
                        b.classList.remove("txv-range-active");
                    });
                } else {
                    // Re-activate current range button
                    const currentBtn = document.querySelector(`.txv-range-btn[data-range="${_txvState.activeRange}"]`);
                    if (currentBtn) currentBtn.classList.add("txv-range-active");
                }
            }
        });
    }

    // Apply custom date range
    const applyBtn = document.getElementById("txv-apply-custom-btn");
    if (applyBtn) {
        applyBtn.addEventListener("click", async () => {
            const startVal = document.getElementById("txv-start-date").value;
            const endVal = document.getElementById("txv-end-date").value;
            if (!startVal || !endVal) {
                alert("Please select both start and end dates.");
                return;
            }
            if (startVal > endVal) {
                alert("Start date must be before or equal to end date.");
                return;
            }
            await _txvLoadAndRender("custom", startVal, endVal);
        });
    }
});

/** Fetch price history and render the chart */
async function _txvLoadAndRender(range, customStart = null, customEnd = null) {
    const statusEl    = document.getElementById("txv-status");
    const containerEl = document.getElementById("txv-chart-container");

    statusEl.textContent = "Loading price history…";

    let prices = [];
    try {
        let url = `/api/prices/history/${encodeURIComponent(_txvState.symbol)}?range=${range}`;
        if (customStart && customEnd) {
            url += `&start=${customStart}&end=${customEnd}`;
        }
        const resp = await fetch(url);
        if (!resp.ok) {
            const err = await resp.json().catch(() => ({}));
            statusEl.textContent = "Error: " + (err.detail || resp.statusText);
            return;
        }
        const data = await resp.json();
        prices = data.prices || [];
    } catch (e) {
        statusEl.textContent = "Network error: " + e.message;
        return;
    }

    if (!prices.length) {
        statusEl.textContent = "No price data available for this range.";
        return;
    }
    statusEl.textContent = "";

    // Invoke render function without clearing or destroying the existing canvas
    _txvRenderChart(containerEl, prices, range);
}

/** Helper to format date as "11 Jul '26" */
function _txvFormatDateLong(dateStr) {
    if (!dateStr) return "";
    const d = new Date(dateStr);
    const day = d.getDate();
    const months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
    const month = months[d.getMonth()];
    const year = d.getFullYear().toString().slice(-2);
    return `${day} ${month} '${year}`;
}

/** Build and render the ApexCharts candlestick chart */
function _txvRenderChart(containerEl, prices, range) {
    // Transform prices into candlestick format with timestamp x values
    const seriesData = prices.map(p => {
        const o = p.open !== null && p.open !== undefined ? p.open : p.close;
        const h = p.high !== null && p.high !== undefined ? p.high : p.close;
        const l = p.low !== null && p.low !== undefined ? p.low : p.close;
        const c = p.close;
        return {
            x: new Date(p.date + 'T00:00:00').getTime(),
            y: [o, h, l, c]
        };
    });

    // Lookup map to translate timestamp back to date string
    const timestampToDateMap = {};
    prices.forEach(p => {
        const ts = new Date(p.date + 'T00:00:00').getTime();
        timestampToDateMap[ts] = p.date;
    });

    // Calculate and display performance over the selected period
    const perfInfoEl = document.getElementById("txv-perf-info");
    if (perfInfoEl && prices.length >= 2) {
        const startPrice = prices[0].close;
        const endPrice = prices[prices.length - 1].close;
        const startDate = prices[0].date;
        const endDate = prices[prices.length - 1].date;

        const changeAbs = endPrice - startPrice;
        const changePct = (changeAbs / startPrice) * 100;

        const symbolMap = { "USD": "$", "SGD": "S$", "CAD": "C$" };
        const curSymbol = symbolMap[_txvState.currency] || _txvState.currency || "$";

        const sign = changeAbs >= 0 ? "+" : "";
        const dirSymbol = changeAbs >= 0 ? "▲" : "▼";
        const perfClass = changeAbs >= 0 ? "pos-val" : "neg-val";
        
        perfInfoEl.innerHTML = `
            ${_txvFormatDateLong(startDate)} - ${_txvFormatDateLong(endDate)}
            <span class="txv-perf-change ${perfClass}">
                ● ${sign}${curSymbol}${changeAbs.toFixed(2)} (${dirSymbol} ${Math.abs(changePct).toFixed(2)}%)
            </span>
        `;
    } else if (perfInfoEl) {
        perfInfoEl.innerHTML = "";
    }

    // Build transaction annotations (point markers & vertical lines)
    const pointAnnotations = [];
    const xAnnotations = [];
    const snapDateTxMap = {}; // snapDate -> list of txs for tooltip display

    if (_txvState.transactions && _txvState.transactions.length) {
        // Build a date→close lookup for snapping
        const priceMap = {};
        prices.forEach(p => { priceMap[p.date] = p.close; });

        // Define visible bounds to filter out-of-view transactions
        const minTime = new Date(prices[0].date + 'T00:00:00').getTime();
        const maxTime = new Date(prices[prices.length - 1].date + 'T23:59:59').getTime();

        // For weekly charts, snap to nearest date in the priceMap
        function nearestDate(targetDate) {
            if (priceMap[targetDate]) return targetDate;
            let closest = null, minDiff = Infinity;
            Object.keys(priceMap).forEach(d => {
                const diff = Math.abs(new Date(d) - new Date(targetDate));
                if (diff < minDiff) { minDiff = diff; closest = d; }
            });
            return closest;
        }

        _txvState.transactions.forEach(tx => {
            if (!tx.date || !tx.action || tx.action.toUpperCase() === "SPLIT") return;
            const txDate  = (tx.date || "").slice(0, 10);
            
            // Check if transaction is out of visible view bounds
            const txTime = new Date(txDate + 'T12:00:00').getTime();
            if (txTime < minTime || txTime > maxTime) return;

            const snapDate = nearestDate(txDate);
            if (!snapDate || priceMap[snapDate] === undefined) return;

            const isBuy   = tx.action.toUpperCase() === "BUY";
            const color   = isBuy ? "#10b981" : "#ef4444";
            const marker  = isBuy ? "▲" : "▼";
            const qty     = tx.quantity || tx.qty || 0;
            const price   = tx.price || 0;
            
            // Map snapDate to transactions list for tooltips
            if (!snapDateTxMap[snapDate]) {
                snapDateTxMap[snapDate] = [];
            }
            snapDateTxMap[snapDate].push(tx);

            const txTimestamp = new Date(snapDate + 'T00:00:00').getTime();

            // Plot marker at exact execution price to make it highly obvious
            pointAnnotations.push({
                x: txTimestamp,
                y: price,
                seriesIndex: 0,
                marker: {
                    size: 8,
                    fillColor: color,
                    strokeColor: "#ffffff",
                    strokeWidth: 2,
                    shape: "circle",
                },
                label: {
                    text: `${marker} ${tx.action.toUpperCase()} (${qty})`,
                    style: {
                        background: color,
                        color: "#fff",
                        fontSize: "9px",
                        padding: { left: 5, right: 5, top: 2, bottom: 2 },
                        borderRadius: 3,
                    },
                    offsetY: isBuy ? -14 : 14,
                },
                tooltip: `${txDate}: ${tx.action.toUpperCase()} ${qty} @ ${_txvState.currency} ${price.toFixed(4)}`,
            });

            // Draw highly visible vertical dashed line to highlight transaction date
            xAnnotations.push({
                x: txTimestamp,
                borderColor: isBuy ? "rgba(16, 185, 129, 0.4)" : "rgba(239, 68, 68, 0.4)",
                strokeDashArray: 4,
                label: {
                    text: "",
                }
            });
        });
    }

    // Avg cost horizontal annotation
    const yAnnotations = [];
    if (_txvState.avgCost > 0) {
        yAnnotations.push({
            y: _txvState.avgCost,
            borderColor: "#a78bfa",
            strokeDashArray: 5,
            label: {
                text: `My cost: ${_txvState.currency} ${_txvState.avgCost.toFixed(4)}`,
                style: {
                    background: "rgba(167,139,250,0.15)",
                    color: "#a78bfa",
                    fontSize: "11px",
                    padding: { left: 6, right: 6, top: 2, bottom: 2 },
                    borderRadius: 4,
                },
                position: "left",
                offsetX: 60, // Shift inwards to avoid overlapping axis
            },
        });
    }

    const options = {
        chart: {
            type: "candlestick",
            height: 600,
            background: "transparent",
            toolbar: { show: false },
            animations: { enabled: false },
            zoom: { enabled: false },
        },
        theme: { mode: "dark" },
        series: [{ name: _txvState.symbol, data: seriesData }],
        plotOptions: {
            candlestick: {
                colors: {
                    upward: '#10b981',
                    downward: '#ef4444'
                },
                wick: {
                    useFillColor: true
                }
            }
        },
        xaxis: {
            type: "datetime",
            tickAmount: Math.min(12, prices.length),
            labels: {
                rotate: -30,
                style: { fontSize: "11px", colors: "#94a3b8" },
                datetimeUTC: false,
            },
        },
        yaxis: {
            labels: {
                style: { fontSize: "11px", colors: "#94a3b8" },
                formatter: (v) => v == null ? "" : v.toFixed(3),
            },
        },
        annotations: {
            yaxis: yAnnotations,
            points: pointAnnotations,
            xaxis: xAnnotations,
        },
        tooltip: {
            theme: "dark",
            custom: function({ series, seriesIndex, dataPointIndex, w }) {
                const ohlc = w.config.series[seriesIndex].data[dataPointIndex];
                if (!ohlc) return "";
                const dateStr = _txvFormatDateLong(ohlc.x);
                const o = ohlc.y[0].toFixed(3);
                const h = ohlc.y[1].toFixed(3);
                const l = ohlc.y[2].toFixed(3);
                const c = ohlc.y[3].toFixed(3);
                
                // Show transaction inside tooltip if it exists on this hovered day/period
                const dateKey = timestampToDateMap[ohlc.x];
                const txs = snapDateTxMap[dateKey] || [];
                
                let txHtml = "";
                if (txs.length > 0) {
                    txHtml = `
                        <div class="txv-tooltip-tx-section">
                            <div class="txv-tooltip-tx-title">Transactions:</div>
                            ${txs.map(t => {
                                const isBuy = t.action.toUpperCase() === "BUY";
                                const actClass = isBuy ? "buy" : "sell";
                                const marker = isBuy ? "▲" : "▼";
                                const qty = t.quantity || t.qty || 0;
                                const p = t.price || 0;
                                return `
                                    <div class="txv-tooltip-tx-row">
                                        <span class="txv-tooltip-tx-action ${actClass}">${marker} ${t.action.toUpperCase()}</span>
                                        ${qty} @ ${_txvState.currency} ${p.toFixed(3)}
                                    </div>
                                `;
                            }).join("")}
                        </div>
                    `;
                }
                
                return `
                    <div class="txv-tooltip-card">
                        <div class="txv-tooltip-date">${dateStr}</div>
                        <div class="txv-tooltip-row"><span>Open:</span><span class="txv-tooltip-value">${o}</span></div>
                        <div class="txv-tooltip-row"><span>High:</span><span class="txv-tooltip-value high">${h}</span></div>
                        <div class="txv-tooltip-row"><span>Low:</span><span class="txv-tooltip-value low">${l}</span></div>
                        <div class="txv-tooltip-row"><span>Close:</span><span class="txv-tooltip-value close">${c}</span></div>
                        ${txHtml}
                    </div>
                `;
            }
        },
        grid: {
            borderColor: "rgba(255,255,255,0.06)",
        },
        dataLabels: { enabled: false },
        legend:    { show: false }
    };

    if (_txvChart) {
        _txvChart.updateOptions(options);
    } else {
        containerEl.innerHTML = "";
        _txvChart = new ApexCharts(containerEl, options);
        _txvChart.render();
    }
}
