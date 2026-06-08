// CRM Dashboard Logic

let funnelChartInstance = null;
let conversionChartInstance = null;
let allLeads = [];

// Helper to include tenant slug in headers if provided via query parameters or localStorage
async function fetchWithTenant(url, options = {}) {
    const urlParams = new URLSearchParams(window.location.search);
    let tenantSlug = urlParams.get('tenant_slug') || localStorage.getItem('tenant_slug');
    if (urlParams.get('tenant_slug')) {
        localStorage.setItem('tenant_slug', urlParams.get('tenant_slug'));
    }
    if (tenantSlug) {
        if (!options.headers) {
            options.headers = {};
        }
        options.headers['X-Tenant-Slug'] = tenantSlug;
    }
    return fetch(url, options);
}

document.addEventListener('DOMContentLoaded', () => {
    // Initialize icons
    lucide.createIcons();
    
    // Initial fetch of data
    loadDashboardData();
    
    // Refresh data every 30 seconds
    setInterval(loadDashboardData, 30000);
});

// Switch active tabs
function switchTab(tabName) {
    // Hide all tab sections
    document.querySelectorAll('.tab-section').forEach(el => el.classList.add('hidden'));
    
    // Deactivate all nav buttons
    document.querySelectorAll('aside nav button').forEach(el => {
        el.className = 'w-full flex items-center gap-3 px-4 py-3 rounded-xl transition duration-200 text-sm font-semibold group text-slate-400 hover:bg-glass-hover hover:text-white border border-transparent';
    });
    
    // Show active tab
    document.getElementById(`tab-${tabName}`).classList.remove('hidden');
    
    // Activate clicked button
    const btn = document.getElementById(`btn-${tabName}`);
    btn.className = 'w-full flex items-center gap-3 px-4 py-3 rounded-xl transition duration-200 text-sm font-semibold group bg-brand-600/10 text-brand-500 shadow-sm border border-brand-500/20';
    
    // Update Header Title
    const titles = {
        overview: "Dashboard Geral",
        kanban: "Quadro Kanban de Negócios",
        leads: "Lista de Clientes & Auditoria de Chats",
        agenda: "Agenda de Eventos & Consultas"
    };
    document.getElementById('page-title').innerText = titles[tabName];
}

// Fetch and load dashboard data
async function loadDashboardData() {
    try {
        const statsResponse = await fetchWithTenant('/api/dashboard/stats');
        const stats = await statsResponse.json();
        renderStats(stats);
        renderCharts(stats.stages);

        const leadsResponse = await fetchWithTenant('/api/dashboard/leads');
        allLeads = await leadsResponse.json();
        renderLeadsTable(allLeads);
        renderKanban(allLeads);

        const apptsResponse = await fetchWithTenant('/api/dashboard/appointments');
        const appts = await apptsResponse.json();
        renderAppointments(appts);
        
        lucide.createIcons();
    } catch (err) {
        console.error("Erro ao carregar dados do dashboard:", err);
    }
}

// Render overall stats numbers
function renderStats(stats) {
    document.getElementById('stat-total-contacts').innerText = stats.total_contacts;
    document.getElementById('stat-total-deals').innerText = stats.total_deals;
    document.getElementById('stat-total-appointments').innerText = stats.total_appointments;
    document.getElementById('stat-ready-for-handoff').innerText = stats.stages.PRONTO_PARA_HUMANO || 0;
}

// Render ChartJS graphs
function renderCharts(stages) {
    const ctxFunnel = document.getElementById('funnelChart').getContext('2d');
    const ctxConversion = document.getElementById('conversionChart').getContext('2d');

    const labels = ["Novo Lead", "Em Qualificação", "Alinhamento", "Pronto p/ Humano"];
    const data = [
        stages.NOVO || 0,
        stages.EM_QUALIFICACAO || 0,
        stages.ALINHAMENTO || 0,
        stages.PRONTO_PARA_HUMANO || 0
    ];

    // Destroy existing instances if they exist
    if (funnelChartInstance) funnelChartInstance.destroy();
    if (conversionChartInstance) conversionChartInstance.destroy();

    // Chart 1: Funnel Pipeline Bar Chart
    funnelChartInstance = new Chart(ctxFunnel, {
        type: 'bar',
        data: {
            labels: labels,
            datasets: [{
                label: 'Negócios',
                data: data,
                backgroundColor: [
                    'rgba(244, 63, 94, 0.75)', // Rose / Novo
                    'rgba(59, 130, 246, 0.75)', // Blue / Em Qualificacao
                    'rgba(245, 158, 11, 0.75)', // Amber / Alinhamento
                    'rgba(16, 185, 129, 0.75)'  // Emerald / Pronto
                ],
                borderColor: [
                    '#f43f5e', '#3b82f6', '#f59e0b', '#10b981'
                ],
                borderWidth: 1.5,
                borderRadius: 8
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            plugins: {
                legend: { display: false }
            },
            scales: {
                y: {
                    grid: { color: 'rgba(255, 255, 255, 0.05)' },
                    ticks: { color: '#94a3b8', stepSize: 1 }
                },
                x: {
                    grid: { display: false },
                    ticks: { color: '#94a3b8' }
                }
            }
        }
    });

    // Chart 2: Conversion Doughnut Chart
    const totalLeads = data.reduce((a, b) => a + b, 0);
    const converted = stages.PRONTO_PARA_HUMANO || 0;
    const inProcess = totalLeads - converted;

    conversionChartInstance = new Chart(ctxConversion, {
        type: 'doughnut',
        data: {
            labels: ['Qualificados', 'Em Aberto'],
            datasets: [{
                data: [converted, inProcess],
                backgroundColor: ['#10b981', 'rgba(255, 255, 255, 0.05)'],
                borderColor: ['#10b981', 'rgba(255, 255, 255, 0.1)'],
                borderWidth: 1
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            cutout: '75%',
            plugins: {
                legend: {
                    position: 'bottom',
                    labels: { color: '#94a3b8', font: { family: 'Inter', size: 11 } }
                }
            }
        }
    });
}

// Render Kanban Column Cards
function renderKanban(leads) {
    const columns = {
        NOVO: document.getElementById('kanban-stage-novo'),
        EM_QUALIFICACAO: document.getElementById('kanban-stage-em_qualificacao'),
        ALINHAMENTO: document.getElementById('kanban-stage-alinhamento'),
        PRONTO_PARA_HUMANO: document.getElementById('kanban-stage-pronto_para_humano')
    };

    // Clear columns
    Object.keys(columns).forEach(key => {
        columns[key].innerHTML = '';
        document.getElementById(`count-kanban-${key.toLowerCase()}`).innerText = 0;
    });

    leads.forEach(lead => {
        const deal = lead.deal;
        if (!deal) return;

        const stage = deal.etapa_funil;
        if (!columns[stage]) return;

        // Increment count
        const counter = document.getElementById(`count-kanban-${stage.toLowerCase()}`);
        counter.innerText = parseInt(counter.innerText) + 1;

        // Card HTML
        const card = document.createElement('div');
        card.className = 'p-4 rounded-xl border border-glass-border bg-glass-card hover:border-slate-500 transition duration-200 cursor-pointer shadow-sm relative group';
        card.innerHTML = `
            <div class="flex items-start justify-between gap-2 mb-2">
                <h5 class="font-outfit font-semibold text-white text-sm">${lead.contact.nome || 'Cliente Sem Nome'}</h5>
            </div>
            <div class="text-[11px] text-slate-400 space-y-1">
                <p class="flex items-center gap-1"><i data-lucide="phone" class="w-3 h-3 text-slate-500"></i> ${lead.contact.whatsapp_id}</p>
                ${deal.tipo_evento ? `<p class="flex items-center gap-1"><i data-lucide="tag" class="w-3 h-3 text-slate-500"></i> ${deal.tipo_evento}</p>` : ''}
                ${deal.orcamento_estimado ? `<p class="flex items-center gap-1"><i data-lucide="dollar-sign" class="w-3 h-3 text-slate-500"></i> R$ ${deal.orcamento_estimado.toLocaleString('pt-BR')}</p>` : ''}
            </div>
            <div class="mt-4 pt-3 border-t border-glass-border/30 flex items-center justify-between">
                <span class="text-[9px] text-slate-500">Atualizado: ${formatDate(deal.atualizado_em)}</span>
                <select onchange="changeLeadStage(${lead.contact.id}, this.value)" class="bg-[#0b0f19] border border-glass-border rounded px-1 py-0.5 text-[10px] text-slate-300 focus:outline-none">
                    <option value="NOVO" ${stage === 'NOVO' ? 'selected' : ''}>Novo</option>
                    <option value="EM_QUALIFICACAO" ${stage === 'EM_QUALIFICACAO' ? 'selected' : ''}>Qualificando</option>
                    <option value="ALINHAMENTO" ${stage === 'ALINHAMENTO' ? 'selected' : ''}>Alinhamento</option>
                    <option value="PRONTO_PARA_HUMANO" ${stage === 'PRONTO_PARA_HUMANO' ? 'selected' : ''}>Comercial</option>
                </select>
            </div>
        `;
        columns[stage].appendChild(card);
    });
}

// Render Leads List Table
function renderLeadsTable(leads) {
    const tbody = document.getElementById('leads-table-body');
    tbody.innerHTML = '';

    leads.forEach(lead => {
        const deal = lead.deal;
        const stageBadges = {
            NOVO: '<span class="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-rose-500/10 text-rose-500 border border-rose-500/20">Novo</span>',
            EM_QUALIFICACAO: '<span class="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-blue-500/10 text-blue-500 border border-blue-500/20">Qualificando</span>',
            ALINHAMENTO: '<span class="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-500 border border-amber-500/20">Alinhamento</span>',
            PRONTO_PARA_HUMANO: '<span class="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">Pronto p/ Humano</span>'
        };

        const stageBadge = deal ? (stageBadges[deal.etapa_funil] || deal.etapa_funil) : '<span class="text-xs text-slate-500">-</span>';

        const tr = document.createElement('tr');
        tr.className = 'hover:bg-glass/30 transition duration-150';
        tr.innerHTML = `
            <td class="p-4 font-semibold text-white">${lead.contact.nome || 'Cliente Sem Nome'}</td>
            <td class="p-4 text-slate-300 font-mono text-xs">${lead.contact.whatsapp_id}</td>
            <td class="p-4">${stageBadge}</td>
            <td class="p-4 text-slate-400 text-xs">${formatDate(lead.contact.data_criacao)}</td>
            <td class="p-4 text-right">
                <button onclick="openLeadChat(${lead.contact.id}, '${lead.contact.nome}', '${lead.contact.whatsapp_id}')" class="px-3 py-1.5 rounded-xl border border-glass-border hover:border-brand-500/30 bg-glass text-xs font-semibold text-slate-200 hover:text-white transition duration-200 flex items-center gap-1.5 ml-auto">
                    <i data-lucide="message-square" class="w-3.5 h-3.5 text-brand-500"></i>
                    Ver Conversa
                </button>
            </td>
        `;
        tbody.appendChild(tr);
    });
}

// Render appointments/agendamentos list
function renderAppointments(appts) {
    const tbody = document.getElementById('appointments-table-body');
    tbody.innerHTML = '';

    if (appts.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="7" class="p-8 text-center text-slate-500">
                    <i data-lucide="calendar-x" class="w-8 h-8 mx-auto mb-2 text-slate-600"></i>
                    Nenhuma consulta ou atendimento agendado no momento.
                </td>
            </tr>
        `;
        return;
    }

    appts.forEach(appt => {
        const appointment = appt.appointment;
        const contact = appt.contact;

        const isConfirmed = appointment.confirmado 
            ? '<span class="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-500 border border-emerald-500/20">Confirmado</span>'
            : '<span class="px-2.5 py-0.5 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-500 border border-amber-500/20">Pendente</span>';

        const tr = document.createElement('tr');
        tr.className = 'hover:bg-glass/30 transition duration-150';
        tr.innerHTML = `
            <td class="p-4 font-semibold text-white">${contact.nome || 'Cliente Sem Nome'}</td>
            <td class="p-4 text-slate-300 font-mono text-xs">${contact.whatsapp_id}</td>
            <td class="p-4 text-slate-200 text-xs">${formatFullDate(appointment.data_agendamento)}</td>
            <td class="p-4 text-slate-400 text-xs">${appointment.duracao_minutos} min</td>
            <td class="p-4 text-slate-300 capitalize text-xs">${appointment.tipo_agendamento.replace('_', ' ')}</td>
            <td class="p-4">${isConfirmed}</td>
            <td class="p-4 text-slate-400 text-xs">${appointment.local_atendimento || 'Online'}</td>
        `;
        tbody.appendChild(tr);
    });
}

// Fetch and open lead chat window
async function openLeadChat(contactId, name, phone) {
    const chatHeaderName = document.getElementById('chat-active-name');
    const chatHeaderPhone = document.getElementById('chat-active-phone');
    const chatContainer = document.getElementById('chat-messages-container');

    chatHeaderName.innerText = name || 'Cliente Sem Nome';
    chatHeaderPhone.innerText = phone;

    chatContainer.innerHTML = `
        <div class="text-center text-slate-500 text-sm my-auto">
            <span class="w-6 h-6 border-2 border-brand-500 border-t-transparent rounded-full animate-spin inline-block mb-2"></span>
            Carregando conversa...
        </div>
    `;

    try {
        const response = await fetchWithTenant(`/api/dashboard/leads/${contactId}/chat`);
        const activities = await response.json();

        chatContainer.innerHTML = '';

        if (activities.length === 0) {
            chatContainer.innerHTML = `
                <div class="text-center text-slate-500 text-sm my-auto">
                    Nenhuma mensagem registrada para esta sessão ainda.
                </div>
            `;
            return;
        }

        activities.forEach(act => {
            const isOutbound = act.direcao === 'outbound';
            const bubble = document.createElement('div');
            
            bubble.className = `flex ${isOutbound ? 'justify-end' : 'justify-start'} w-full`;
            bubble.innerHTML = `
                <div class="max-w-[75%] rounded-2xl p-4 shadow-md text-sm border ${
                    isOutbound 
                        ? 'bg-brand-600 border-transparent text-white rounded-tr-none' 
                        : 'bg-slate-800 border-slate-700 text-slate-100 rounded-tl-none'
                }">
                    <p class="whitespace-pre-line leading-relaxed font-medium">${act.conteudo}</p>
                    <span class="text-[9px] ${isOutbound ? 'text-rose-200' : 'text-slate-400'} block text-right mt-1.5">${formatTime(act.timestamp)}</span>
                </div>
            `;
            chatContainer.appendChild(bubble);
        });

        // Scroll to the bottom
        chatContainer.scrollTop = chatContainer.scrollHeight;

    } catch (err) {
        console.error("Erro ao carregar mensagens do chat:", err);
        chatContainer.innerHTML = `
            <div class="text-center text-rose-400 text-sm my-auto">
                Falha ao carregar o chat.
            </div>
        `;
    }
}

// Change stage patch endpoint
async function changeLeadStage(contactId, newStage) {
    try {
        const response = await fetchWithTenant(`/api/dashboard/leads/${contactId}/stage`, {
            method: 'PATCH',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ stage: newStage })
        });
        const result = await response.json();
        if (result.status === 'success') {
            loadDashboardData();
        }
    } catch (err) {
        console.error("Erro ao alterar estágio:", err);
    }
}

// Filter leads table in real-time
function filterLeadsTable() {
    const input = document.getElementById('lead-search-input');
    const filter = input.value.toLowerCase();
    const tbody = document.getElementById('leads-table-body');
    const trs = tbody.getElementsByTagName('tr');

    for (let i = 0; i < trs.length; i++) {
        const nameTd = trs[i].getElementsByTagName('td')[0];
        const phoneTd = trs[i].getElementsByTagName('td')[1];
        if (nameTd || phoneTd) {
            const nameText = nameTd.textContent || nameTd.innerText;
            const phoneText = phoneTd.textContent || phoneTd.innerText;
            if (nameText.toLowerCase().indexOf(filter) > -1 || phoneText.toLowerCase().indexOf(filter) > -1) {
                trs[i].style.display = "";
            } else {
                trs[i].style.display = "none";
            }
        }
    }
}

// Helpers
function formatDate(dateStr) {
    if (!dateStr) return "-";
    const date = new Date(dateStr);
    return date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric' });
}

function formatFullDate(dateStr) {
    if (!dateStr) return "-";
    const date = new Date(dateStr);
    return date.toLocaleDateString('pt-BR', { day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit' }) + "h";
}

function formatTime(dateStr) {
    if (!dateStr) return "";
    const date = new Date(dateStr);
    return date.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
}
