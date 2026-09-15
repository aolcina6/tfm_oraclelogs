let currentData = null;
let currentOrigin = null;

// Inicialización
document.addEventListener('DOMContentLoaded', function() {
    loadSummary();
});

async function loadSummary() {
    try {
        const response = await fetch('/api/drain/summary');
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        currentData = data;
        
        console.log('📊 Summary loaded:', data);
        
        // Actualizar estadísticas globales
        document.getElementById('statOrigins').textContent = data.total_origins || 0;
        document.getElementById('statClusters').textContent = data.total_clusters || 0;
        document.getElementById('statPatterns').textContent = data.total_patterns || 0;
        document.getElementById('statLines').textContent = data.total_lines || 0;
        
        // ✅ CORREGIDO: Cargar lista de orígenes desde endpoint correcto
        await loadOrigins();
        
    } catch (error) {
        console.error('❌ Error loading summary:', error);
        showError(`Failed to load DRAIN summary: ${error.message}`);
    }
}

async function loadOrigins() {
    try {
        const response = await fetch('/api/drain/origins');
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        console.log('📂 Origins loaded:', data.origins);
        
        const select = document.getElementById('originSelect');
        select.innerHTML = '<option value="">-- Choose an origin --</option>';
        
        if (data.origins && data.origins.length > 0) {
            data.origins.forEach(origin => {
                const option = document.createElement('option');
                option.value = origin;
                option.textContent = origin;
                select.appendChild(option);
            });
            
            // Auto-seleccionar el primer origen
            select.value = data.origins[0];
            loadOriginData();
        } else {
            console.warn('⚠️ No origins found');
            clearAllTabs();
        }
    } catch (error) {
        console.error('❌ Error loading origins:', error);
        showError(`Failed to load origins: ${error.message}`);
    }
}

async function loadOriginData() {
    const origin = document.getElementById('originSelect').value;
    
    if (!origin) {
        clearAllTabs();
        return;
    }
    
    currentOrigin = origin;
    console.log(`🔍 Loading data for origin: ${origin}`);
    
    // Cargar datos según la pestaña activa
    const activeTab = document.querySelector('.tab-button.active');
    const activeTabName = activeTab.getAttribute('onclick').match(/'([^']+)'/)[1];
    
    if (activeTabName === 'patterns') {
        loadPatterns(origin);
    } else if (activeTabName === 'contexts') {
        loadContexts(origin);
    } else if (activeTabName === 'variables') {
        loadVariables(origin);
    } else if (activeTabName === 'extractors') {
        loadExtractors(origin);
    }
}

function switchTab(tabName) {
    console.log(`🔄 Switching to tab: ${tabName}`);
    
    // Actualizar botones
    document.querySelectorAll('.tab-button').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');
    
    // Actualizar contenido
    document.querySelectorAll('.tab-content').forEach(content => {
        content.classList.remove('active');
    });
    document.getElementById(tabName).classList.add('active');
    
    // Cargar datos si hay origen seleccionado
    if (currentOrigin) {
        if (tabName === 'patterns') loadPatterns(currentOrigin);
        else if (tabName === 'contexts') loadContexts(currentOrigin);
        else if (tabName === 'variables') loadVariables(currentOrigin);
        else if (tabName === 'extractors') loadExtractors(currentOrigin);
    }
}

async function loadPatterns(origin) {
    const tbody = document.getElementById('patternsBody');
    tbody.innerHTML = '<tr><td colspan="3" class="loading">Loading patterns...</td></tr>';
    
    try {
        console.log(`📊 Loading patterns for: ${origin}`);
        
        // ✅ CORREGIDO: Usar endpoint correcto
        const response = await fetch(`/api/drain/origin/${encodeURIComponent(origin)}/patterns`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        console.log(`✓ Patterns loaded: ${data.patterns?.length || 0}`);
        
        if (!data.patterns || data.patterns.length === 0) {
            tbody.innerHTML = '<tr><td colspan="3" class="loading">No patterns found</td></tr>';
            return;
        }
        
        // Ordenar por occurrences descendente
        const sortedPatterns = data.patterns.sort((a, b) => b.occurrences - a.occurrences);
        
        tbody.innerHTML = '';
        sortedPatterns.forEach((pattern, index) => {
            const row = tbody.insertRow();
            
            // Template
            const templateCell = row.insertCell();
            templateCell.innerHTML = `<div class="template">${escapeHtml(pattern.template)}</div>`;
            
            // Occurrences
            const occCell = row.insertCell();
            occCell.innerHTML = `<span class="badge">${pattern.occurrences}</span>`;
            
            // Examples
            const examplesCell = row.insertCell();
            if (pattern.examples && pattern.examples.length > 0) {
                const detailsId = `examples-${index}`;
                examplesCell.innerHTML = `
                    <details>
                        <summary>View ${pattern.examples.length} example${pattern.examples.length > 1 ? 's' : ''}</summary>
                        <div class="examples-container" id="${detailsId}">
                            ${pattern.examples.map(ex => 
                                `<div class="log-example">${escapeHtml(ex)}</div>`
                            ).join('')}
                        </div>
                    </details>
                `;
            } else {
                examplesCell.innerHTML = '<span class="no-examples">No examples</span>';
            }
        });
        
    } catch (error) {
        console.error('❌ Error loading patterns:', error);
        tbody.innerHTML = `<tr><td colspan="3" class="error">Error: ${escapeHtml(error.message)}</td></tr>`;
    }
}

async function loadContexts(origin) {
    const tbody = document.getElementById('contextsBody');
    tbody.innerHTML = '<tr><td colspan="5" class="loading">Loading contexts...</td></tr>';
    
    try {
        console.log(`🔗 Loading contexts for: ${origin}`);
        
        // ✅ CORREGIDO: Usar endpoint correcto
        const response = await fetch(`/api/drain/origin/${encodeURIComponent(origin)}/contexts`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        console.log(`✓ Contexts loaded: ${data.contexts?.length || 0}`);
        
        if (!data.contexts || data.contexts.length === 0) {
            tbody.innerHTML = '<tr><td colspan="5" class="loading">No contexts found</td></tr>';
            return;
        }
        
        // Ordenar por frecuencia descendente
        const sortedContexts = data.contexts.sort((a, b) => b.frequency - a.frequency);
        
        tbody.innerHTML = '';
        sortedContexts.forEach(ctx => {
            const row = tbody.insertRow();
            
            row.insertCell().textContent = ctx.position || '-';
            row.insertCell().innerHTML = `<code>${escapeHtml(ctx.left_context || '')}</code>`;
            row.insertCell().innerHTML = `<span class="badge badge-secondary">${escapeHtml(ctx.wildcard)}</span>`;
            row.insertCell().innerHTML = `<code>${escapeHtml(ctx.right_context || '')}</code>`;
            row.insertCell().innerHTML = `<span class="badge">${ctx.frequency}</span>`;
        });
        
    } catch (error) {
        console.error('❌ Error loading contexts:', error);
        tbody.innerHTML = `<tr><td colspan="5" class="error">Error: ${escapeHtml(error.message)}</td></tr>`;
    }
}

async function loadVariables(origin) {
    const container = document.getElementById('variablesContainer');
    container.innerHTML = '<div class="loading">Loading variable patterns...</div>';
    
    try {
        console.log(`🔍 Loading variables for: ${origin}`);
        
        // ✅ CORREGIDO: Usar endpoint correcto
        const response = await fetch(`/api/variable-patterns/origin/${encodeURIComponent(origin)}`);
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        console.log(`✓ Variables loaded: ${data.templates?.length || 0}`);
        
        if (!data.templates || data.templates.length === 0) {
            container.innerHTML = '<div class="loading">No variable patterns found</div>';
            return;
        }
        
        let html = '';
        
        data.templates.forEach(variable => {
            html += `
                <div class="variable-item">
                    <div class="variable-header">
                        <h3>${escapeHtml(variable.variable_name || variable.name)}</h3>
                        <span class="variable-type">${variable.variable_type || variable.type || 'UNKNOWN'}</span>
                    </div>
                    
                    ${variable.left_context || variable.right_context ? `
                        <div class="variable-context">
                            Context: 
                            ${variable.left_context ? `<code>${escapeHtml(variable.left_context)}</code>` : ''}
                            <strong>[${variable.variable_name || variable.name}]</strong>
                            ${variable.right_context ? `<code>${escapeHtml(variable.right_context)}</code>` : ''}
                        </div>
                    ` : ''}
                    
                    <div class="variable-stats">
                        <span>📊 Total occurrences: <strong>${variable.total_occurrences || variable.occurrences || 0}</strong></span>
                        <span>🔢 Unique values: <strong>${variable.unique_values || 0}</strong></span>
                        <span>📈 Patterns: <strong>${variable.patterns_count || 0}</strong></span>
                    </div>
                    
                    ${variable.top_values && variable.top_values.length > 0 ? `
                        <details style="margin-top: 15px;">
                            <summary>Top values (${variable.top_values.length})</summary>
                            <div class="examples-container">
                                ${variable.top_values.map(val => `
                                    <div class="example-value">
                                        <div class="example-value-header">${escapeHtml(val.value)}</div>
                                        <div style="font-size: 0.85em; color: #666;">
                                            Frequency: ${val.count} | 
                                            In ${val.patterns?.length || 0} pattern${val.patterns?.length !== 1 ? 's' : ''}
                                        </div>
                                        ${val.example_logs && val.example_logs.length > 0 ? `
                                            <div class="example-logs">
                                                ${val.example_logs.slice(0, 3).map(log => 
                                                    `<div class="log-line">${escapeHtml(log)}</div>`
                                                ).join('')}
                                            </div>
                                        ` : ''}
                                    </div>
                                `).join('')}
                            </div>
                        </details>
                    ` : ''}
                </div>
            `;
        });
        
        container.innerHTML = html;
        
    } catch (error) {
        console.error('❌ Error loading variables:', error);
        container.innerHTML = `<div class="error">Error: ${escapeHtml(error.message)}</div>`;
    }
}

async function loadExtractors(origin) {
    const container = document.getElementById('extractorsContainer');
    container.innerHTML = '<div class="loading">Loading extractor analysis...</div>';
    
    try {
        console.log(`📊 Loading extractors for: ${origin}`);
        
        // ✅ CORREGIDO: Usar endpoint global (no por origen)
        const response = await fetch('/api/extractor-analysis');
        
        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }
        
        const data = await response.json();
        
        if (data.error) {
            throw new Error(data.error);
        }
        
        // Filtrar por origen actual
        const originAnalysis = data.origins?.[origin];
        
        if (!originAnalysis) {
            container.innerHTML = `<div class="loading">No extractor analysis found for ${origin}</div>`;
            return;
        }
        
        console.log(`✓ Extractor analysis loaded for ${origin}`);
        
        const analysis = originAnalysis;
        
        let html = `
            <div class="extractor-card">
                <div class="extractor-header">
                    <div class="extractor-origin">${escapeHtml(origin)}</div>
                </div>
                
                <div class="extractor-stats">
                    <div class="extractor-stat">
                        <div class="extractor-stat-value">${analysis.total_variables || 0}</div>
                        <div class="extractor-stat-label">Variables</div>
                    </div>
                    <div class="extractor-stat">
                        <div class="extractor-stat-value">${analysis.extracted_count || 0}</div>
                        <div class="extractor-stat-label">Extracted</div>
                    </div>
                    <div class="extractor-stat ${analysis.duplicate_count > 0 ? 'warning' : ''}">
                        <div class="extractor-stat-value">${analysis.duplicate_count || 0}</div>
                        <div class="extractor-stat-label">Duplicates</div>
                    </div>
                    <div class="extractor-stat ${analysis.new_patterns_count > 0 ? 'success' : ''}">
                        <div class="extractor-stat-value">${analysis.new_patterns_count || 0}</div>
                        <div class="extractor-stat-label">New Patterns</div>
                    </div>
                </div>
        `;
        
        // Duplicates
        if (analysis.duplicates && analysis.duplicates.length > 0) {
            html += `
                <div class="duplicates-section">
                    <h3>⚠️ Duplicate Variables (${analysis.duplicates.length})</h3>
                    ${analysis.duplicates.map(dup => `
                        <div class="duplicate-item">
                            <div class="duplicate-var">${escapeHtml(dup.variable)}</div>
                            <div class="duplicate-match">
                                <span>📊 Extractor: <code>${escapeHtml(dup.extractor_name)}</code></span>
                                <span>🎯 Regex: <code>${escapeHtml(dup.extractor_regex)}</code></span>
                                <span>🔢 Occurrences: <strong>${dup.occurrences}</strong></span>
                            </div>
                        </div>
                    `).join('')}
                </div>
            `;
        }
        
        // New patterns
        if (analysis.new_patterns && analysis.new_patterns.length > 0) {
            html += `
                <div class="new-patterns-section">
                    <h3>✨ New Patterns Found (${analysis.new_patterns.length})</h3>
                    ${analysis.new_patterns.map(pattern => `
                        <div class="new-pattern-item">
                            <div style="display: flex; justify-content: space-between; align-items: center;">
                                <strong>Pattern Template:</strong>
                                <span class="status-badge ${pattern.coverage_status || 'new'}">${pattern.coverage_status || 'NEW'}</span>
                            </div>
                            <div class="new-pattern-template">${escapeHtml(pattern.template)}</div>
                            <div class="new-pattern-info">
                                <span>📊 Variables: <strong>${pattern.variables?.length || 0}</strong></span>
                                <span>🔢 Occurrences: <strong>${pattern.occurrences || 0}</strong></span>
                                ${pattern.variables && pattern.variables.length > 0 ? `
                                    <span>🏷️ Variables: <code>${pattern.variables.join(', ')}</code></span>
                                ` : ''}
                            </div>
                            ${pattern.example_log ? `
                                <details style="margin-top: 10px;">
                                    <summary>View example</summary>
                                    <div class="log-example" style="margin-top: 8px;">${escapeHtml(pattern.example_log)}</div>
                                </details>
                            ` : ''}
                        </div>
                    `).join('')}
                </div>
            `;
        }
        
        // Variables summary
        if (analysis.variables_summary) {
            html += `
                <div class="new-patterns-section">
                    <h3>📋 Variables Summary</h3>
                    <table class="patterns-table">
                        <thead>
                            <tr>
                                <th>Variable</th>
                                <th>Type</th>
                                <th>Patterns</th>
                                <th>Unique Values</th>
                                <th>Status</th>
                            </tr>
                        </thead>
                        <tbody>
                            ${Object.entries(analysis.variables_summary).map(([varName, info]) => `
                                <tr>
                                    <td><code>${escapeHtml(varName)}</code></td>
                                    <td><span class="variable-type">${info.type || 'UNKNOWN'}</span></td>
                                    <td><span class="badge">${info.patterns_count || 0}</span></td>
                                    <td><span class="badge badge-secondary">${info.unique_values || 0}</span></td>
                                    <td>
                                        ${info.has_extractor 
                                            ? '<span class="status-badge covered">✓ Extracted</span>' 
                                            : '<span class="status-badge new">New</span>'}
                                    </td>
                                </tr>
                            `).join('')}
                        </tbody>
                    </table>
                </div>
            `;
        }
        
        html += '</div>';
        container.innerHTML = html;
        
    } catch (error) {
        console.error('❌ Error loading extractors:', error);
        container.innerHTML = `<div class="error">Error: ${escapeHtml(error.message)}</div>`;
    }
}

function clearAllTabs() {
    document.getElementById('patternsBody').innerHTML = '<tr><td colspan="3" class="loading">Select an origin to view patterns</td></tr>';
    document.getElementById('contextsBody').innerHTML = '<tr><td colspan="5" class="loading">Select an origin to view contexts</td></tr>';
    document.getElementById('variablesContainer').innerHTML = '<div class="loading">Select an origin to view variables</div>';
    document.getElementById('extractorsContainer').innerHTML = '<div class="loading">Select an origin to view extractors</div>';
}

function showError(message) {
    const container = document.querySelector('.container');
    const errorDiv = document.createElement('div');
    errorDiv.className = 'error';
    errorDiv.style.padding = '20px';
    errorDiv.style.margin = '20px 0';
    errorDiv.style.backgroundColor = '#fee';
    errorDiv.style.border = '1px solid #fcc';
    errorDiv.style.borderRadius = '5px';
    errorDiv.innerHTML = `<strong>❌ Error:</strong> ${escapeHtml(message)}`;
    container.insertBefore(errorDiv, container.firstChild);
    
    // Auto-ocultar después de 10 segundos
    setTimeout(() => errorDiv.remove(), 10000);
}

function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}