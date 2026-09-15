let currentPage = 1;
let totalPages = 1;
let allLogTypes = new Set();

async function loadDates() {
    const res = await fetch("/api/dates");
    const data = await res.json();
    document.getElementById("mode-badge").textContent = "Modo: " + data.mode;

    const select = document.getElementById("date-select");
    select.innerHTML = '<option value="">— Todas las fechas —</option>';
    
    if (data.dates.length > 0) {
        data.dates.forEach(d => {
            const opt = document.createElement("option");
            opt.value = d;
            opt.textContent = d;
            select.appendChild(opt);
        });
    }
}

async function loadLogTypes(dateStr = "") {
    const select = document.getElementById("logtype-select");
    select.innerHTML = '<option value="">— Todos los tipos —</option>';
    
    if (!dateStr) {
        if (allLogTypes.size > 0) {
            [...allLogTypes].sort().forEach(t => {
                const opt = document.createElement("option");
                opt.value = t;
                opt.textContent = t;
                select.appendChild(opt);
            });
            return;
        }
        
        try {
            const dateRes = await fetch("/api/dates");
            const dateData = await dateRes.json();
            
            for (const date of dateData.dates) {
                const typeRes = await fetch(`/api/log_types?date=${encodeURIComponent(date)}`);
                const typeData = await typeRes.json();
                typeData.log_types.forEach(t => allLogTypes.add(t));
            }
            
            [...allLogTypes].sort().forEach(t => {
                const opt = document.createElement("option");
                opt.value = t;
                opt.textContent = t;
                select.appendChild(opt);
            });
        } catch (e) {
            console.error("Error cargando tipos:", e);
        }
        return;
    }
    
    const res = await fetch(`/api/log_types?date=${encodeURIComponent(dateStr)}`);
    const data = await res.json();
    
    if (data.log_types.length > 0) {
        data.log_types.forEach(t => {
            const opt = document.createElement("option");
            opt.value = t;
            opt.textContent = t;
            select.appendChild(opt);
        });
    }
}

async function loadRecords(page = 1) {
    const date = document.getElementById("date-select").value;
    const logType = document.getElementById("logtype-select").value;
    const search = document.getElementById("search-input").value;
    
    document.getElementById("table-container").innerHTML = '<div class="loading">Cargando...</div>';
    document.getElementById("pagination").style.display = "none";

    const params = new URLSearchParams({ page, page_size: 50 });
    
    if (date) params.append("date", date);
    if (logType) params.append("log_type", logType);
    if (search) params.append("search", search);

    try {
        const res = await fetch(`/api/records?${params}`);
        const data = await res.json();

        if (data.error) {
            document.getElementById("table-container").innerHTML =
                `<div class="empty">⚠️ ${data.error}</div>`;
            return;
        }

        currentPage = data.page;
        totalPages = data.total_pages;

        renderTable(data.records);

        let filterParts = [];
        if (date) filterParts.push(`Fecha: ${date}`);
        if (logType) filterParts.push(`Tipo: ${logType}`);
        if (search) filterParts.push(`Búsqueda: "${search}"`);
        
        let filterText = filterParts.length > 0 
            ? `Filtros activos: ${filterParts.join(" | ")}` 
            : "Sin filtros (mostrando todos los registros)";
        
        document.getElementById("filter-info").textContent = filterText;
        document.getElementById("status-line").textContent =
            `${data.total} registros encontrados`;

        document.getElementById("page-info").textContent = `Página ${currentPage} de ${totalPages}`;
        document.getElementById("pagination").style.display = "flex";
        document.getElementById("prev-btn").disabled = currentPage <= 1;
        document.getElementById("next-btn").disabled = currentPage >= totalPages;
    } catch (e) {
        console.error("Error cargando registros:", e);
        document.getElementById("table-container").innerHTML =
            `<div class="empty">❌ Error: ${e.message}</div>`;
    }
}

function renderTable(records) {
    const container = document.getElementById("table-container");

    if (!records || records.length === 0) {
        container.innerHTML = '<div class="empty">No hay registros que coincidan.</div>';
        return;
    }

    const priorityCols = ["_source_file", "timestamp_normalized", "timestamp", "message", "frequency_per_minute"];
    const allKeys = new Set();
    
    records.forEach(r => Object.keys(r).forEach(k => {
        if (!k.startsWith("_") && k !== "extracted") allKeys.add(k);
    }));
    

    const hasExtracted = records.some(r => r.extracted && Object.keys(r.extracted).length > 0);
    let extractedKeys = new Set();
    if (hasExtracted) {
        records.forEach(r => {
            if (r.extracted) Object.keys(r.extracted).forEach(k => extractedKeys.add(k));
        });
    }

    let otherCols = [...allKeys].filter(k => !priorityCols.includes(k));
    const removeCols = ["log_type", "pattern", "_source_file", "source_file", "file", "template_group_id"];
    otherCols = otherCols.filter(k => !removeCols.includes(k));
    const columns = [
        ...priorityCols.filter(c => allKeys.has(c) || c.startsWith("_")), 
        ...otherCols, 
        ...extractedKeys
    ];
    console.log(columns)

    let html = "<table><thead><tr>";
    columns.forEach(c => {
        let displayName = c;
        // if (c === "_date") displayName = "📅 Fecha";
        if (c === "_source_file") displayName = "📄 Origen";
        else if (c === "timestamp_normalized") displayName = "🕐 Timestamp";
        else if (c.startsWith("_")) displayName = c.substring(1);
        
        html += `<th>${displayName}</th>`;
    });
    html += "</tr></thead><tbody>";

    records.forEach(r => {
        html += "<tr>";
        columns.forEach(c => {
            let value;
            if (extractedKeys.has(c) && r.extracted) {
                value = r.extracted[c];
            } else {
                value = r[c];
            }
            
            if (Array.isArray(value)) value = value.join(", ");
            if (value === null || value === undefined) value = "";
            
            let cellClass = "";
            if (c === "_source_file") cellClass = 'class="origin-cell"';
            else if (c === "_date") cellClass = 'class="date-cell"';
            else if (c === "message") cellClass = 'class="message-cell"';
            
            html += `<td ${cellClass}>${escapeHtml(String(value))}</td>`;
        });
        html += "</tr>";
    });

    html += "</tbody></table>";
    container.innerHTML = html;
}

function escapeHtml(str) {
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;");
}

// Event listeners
document.getElementById("date-select").addEventListener("change", (e) => {
    const selectedDate = e.target.value;
    loadLogTypes(selectedDate);
    loadRecords(1);
});

document.getElementById("logtype-select").addEventListener("change", () => {
    loadRecords(1);
});

document.getElementById("search-btn").addEventListener("click", () => {
    loadRecords(1);
});

document.getElementById("search-input").addEventListener("keydown", (e) => {
    if (e.key === "Enter") loadRecords(1);
});

document.getElementById("reset-btn").addEventListener("click", () => {
    document.getElementById("date-select").value = "";
    document.getElementById("logtype-select").value = "";
    document.getElementById("search-input").value = "";
    loadLogTypes("");
    loadRecords(1);
});

document.getElementById("prev-btn").addEventListener("click", () => {
    if (currentPage > 1) loadRecords(currentPage - 1);
});

document.getElementById("next-btn").addEventListener("click", () => {
    if (currentPage < totalPages) loadRecords(currentPage + 1);
});

// Inicialización
(async function init() {
    await loadDates();
    await loadLogTypes("");
    await loadRecords(1);
})();