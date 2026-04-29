const { createApp, ref, onMounted, computed, watch } = Vue;

createApp({
    setup() {
        const view = ref('mods');
        const modTab = ref('installed');
        const loading = ref(false);
        const processing = ref(null);
        const errors = ref({}); 
        
        const stats = ref({ modules_count: 0, api_status: 'Stable', version: '?.?.?', host_mode: "tunnel" });
        const searchQuery = ref('');
        const searchResults = ref([]);
        const installedModules = ref([]);

        const repos = ref([]);
        const newRepo = ref('');
        const repoLoading = ref(false);

        const cfgModal = ref({ open: false, loading: false, saving: false, moduleId: '', modName: '', schema:[], msg: '' });
        
        // Переменные для хоста
        const currentHostMode = ref('tunnel');
        const hostSaving = ref(false);

        // ПРАВИЛЬНЫЙ fetchStatus: читает статус и обновляет выпадающий список
        const fetchStatus = async () => {
            try {
                const res = await fetch('/api/status');
                if (res.status === 401) window.location.href = '/';
                const data = await res.json();
                stats.value = data;
                
                // Синхронизируем выпадающий список с базой данных
                if (data.host_mode) {
                    currentHostMode.value = data.host_mode;
                }
            } catch (e) {}
        };

        const updateHost = async () => {
            hostSaving.value = true;
            try {
                const res = await fetch('/api/config/host', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ host: currentHostMode.value })
                });
                
                if (res.ok) {
                    alert("✅ Host mode updated! Restart the bot to apply changes.");
                } else {
                    alert("❌ Failed to update host mode. Validation error.");
                }
            } catch (e) {
                alert("❌ Network Error");
            }
            hostSaving.value = false;
        };

        const fetchInstalled = async () => {
            loading.value = true;
            try {
                const res = await fetch('/api/modules/installed');
                installedModules.value = await res.json();
            } catch (e) {}
            loading.value = false;
        };

        const searchModules = async () => {
            loading.value = true;
            try {
                const res = await fetch(`/api/modules/search?query=${encodeURIComponent(searchQuery.value)}`);
                searchResults.value = await res.json();
            } catch (e) {}
            loading.value = false;
        };

        const fetchRepos = async () => {
            try {
                const res = await fetch('/api/repos');
                repos.value = await res.json();
            } catch (e) {}
        };

        const addRepo = async () => {
            if (!newRepo.value) return;
            repoLoading.value = true;
            try {
                const res = await fetch('/api/repos/add', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url: newRepo.value })
                });
                if (res.ok) {
                    newRepo.value = '';
                    await fetchRepos();
                } else alert("Failed to add repository.");
            } catch(e) {}
            repoLoading.value = false;
        };

        const removeRepo = async (url) => {
            try {
                await fetch('/api/repos/remove', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ url })
                });
                await fetchRepos();
            } catch(e) {}
        };

        const toggleModule = async (mod) => {
            processing.value = mod.id;
            errors.value[mod.id] = null;
            const endpoint = mod.is_installed ? '/api/modules/uninstall' : '/api/modules/install';
            const payload = mod.is_installed ? { module_id: mod.id } : { module_id: mod.id, target: mod.target };
            
            try {
                const res = await fetch(endpoint, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
                
                if (res.ok) {
                    mod.is_installed = !mod.is_installed;
                    fetchStatus();
                    if (modTab.value === 'installed') fetchInstalled();
                } else {
                    const errorData = await res.json();
                    errors.value[mod.id] = `Error ${res.status}`;
                    setTimeout(() => { errors.value[mod.id] = null; }, 3000);
                }
            } catch (e) { 
                errors.value[mod.id] = 'Network Error'; 
                setTimeout(() => { errors.value[mod.id] = null; }, 3000);
            }
            processing.value = null;
        };

        const openConfig = async (mod) => {
            cfgModal.value = { ...cfgModal.value, moduleId: mod.id, modName: mod.name, open: true, loading: true, msg: '' };
            try {
                const res = await fetch(`/api/modules/${mod.id}/config`);
                if (res.ok) {
                    const data = await res.json();
                    cfgModal.value.schema = data.config;
                } else closeConfig();
            } catch (e) { closeConfig(); }
            cfgModal.value.loading = false;
        };

        const closeConfig = () => { cfgModal.value.open = false; cfgModal.value.schema =[]; };

        const saveConfig = async () => {
            cfgModal.value.saving = true;
            cfgModal.value.msg = '';
            const payload = {};
            cfgModal.value.schema.forEach(item => { if (item.editable) payload[item.key] = item.value; });

            try {
                const res = await fetch(`/api/modules/${cfgModal.value.moduleId}/config`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ config: payload })
                });
                if (res.ok) {
                    cfgModal.value.msg = "Saved successfully.";
                    setTimeout(() => { if(cfgModal.value.open) closeConfig(); }, 1000);
                } else {
                    const err = await res.json();
                    cfgModal.value.msg = "Error: " + (err.detail || "Validation failed.");
                }
            } catch (e) { cfgModal.value.msg = "Network Error."; }
            cfgModal.value.saving = false;
        };

        const btnClass = (active) => `px-3 py-1.5 rounded-md text-xs font-medium transition-colors ${active ? 'bg-[#27272a] text-blue-400' : 'text-[#a1a1aa] hover:text-white hover:bg-[#18181b]'}`;

        const tabClass = (active) => `text-xs font-semibold pb-1 transition-colors border-b-2 ${active ? 'text-blue-400 border-blue-400' : 'text-[#71717a] border-transparent hover:text-[#a1a1aa]'}`;

        const currentModList = computed(() => modTab.value === 'installed' ? installedModules.value : searchResults.value);

        watch(modTab, (v) => { if (v === 'installed') fetchInstalled(); if (v === 'search' && searchResults.value.length === 0) searchModules(); });
        watch(view, (v) => { if (v === 'set' && repos.value.length === 0) fetchRepos(); });

        onMounted(() => { fetchStatus(); fetchInstalled(); setInterval(fetchStatus, 15000); });

        return { view, modTab, loading, processing, stats, searchQuery, currentModList, btnClass, tabClass, searchModules, toggleModule, cfgModal, openConfig, closeConfig, saveConfig, errors, repos, newRepo, repoLoading, addRepo, removeRepo, updateHost, currentHostMode, hostSaving };
    }
}).mount('#app');