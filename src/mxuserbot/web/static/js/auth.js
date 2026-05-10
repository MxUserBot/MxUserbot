const { createApp, ref, reactive, onMounted, watch } = Vue;

createApp({
    setup() {
        const view = ref('welcome');
        const availableLangs = ['en', 'ru'];
        const initialLang = localStorage.getItem('lang');
        const lang = ref(availableLangs.includes(initialLang) ? initialLang : 'en');
        const loading = ref(false);
        const translations = ref({});
        const form = reactive({ mxid: '', password: '' });
        const result = reactive({ ok: false, msg: '' });
        const ssoAvailable = ref(false);
        const checkingSso = ref(false);
        let ssoTimer = null;

        const t = (key) => {
            return (translations.value[lang.value] && translations.value[lang.value][key]) || 
                   (translations.value['en'] && translations.value['en'][key]) || key;
        };

        const setLang = (l) => {
            lang.value = l;
            localStorage.setItem('lang', l);
        };

        const doSsoCheck = async (mxid) => {
            checkingSso.value = true;
            ssoAvailable.value = false;
            try {
                const res = await fetch('/api/auth/sso/init', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        mxid: mxid,
                        callback_url: window.location.origin + '/api/auth/sso/callback'
                    })
                });
                if (res.ok) {
                    const data = await res.json();
                    ssoAvailable.value = !!data.available;
                }
            } catch (e) {}
            checkingSso.value = false;
        };

        watch(() => form.mxid, (val) => {
            if (ssoTimer) clearTimeout(ssoTimer);
            const v = val.trim();
            if (!v) {
                ssoAvailable.value = false;
                return;
            }
            ssoTimer = setTimeout(() => doSsoCheck(v), 400);
        });

        const handleLogin = async () => {
            if (!form.mxid.includes(':')) return alert(t('mxid_format_error'));
            loading.value = true;
            try {
                const res = await fetch('/api/auth', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(form)
                });
                const data = await res.json();
                result.ok = res.ok;
                result.msgKey = res.ok ? 'session_initialized' : null;
                result.msg = res.ok ? t('session_initialized') : (data.detail || t('result_failed'));
                view.value = 'result';
            } catch (e) {
                result.ok = false;
                result.msgKey = 'server_unreachable';
                result.msg = t('server_unreachable');
                view.value = 'result';
            }
            loading.value = false;
        };

        const handleSsoLogin = async () => {
            if (!form.mxid.trim()) return;
            loading.value = true;
            try {
                const res = await fetch('/api/auth/sso/init', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        mxid: form.mxid,
                        callback_url: window.location.origin + '/api/auth/sso/callback'
                    })
                });
                const data = await res.json();
                if (data.available && data.redirect_url) {
                    window.location.href = data.redirect_url;
                } else {
                    alert(t('sso_unavailable'));
                    loading.value = false;
                }
            } catch (e) {
                alert(t('server_unreachable'));
                loading.value = false;
            }
        };

        const terminate = () => {
            result.ok = false;
            result.msgKey = 'session_terminated';
            result.msg = t('session_terminated');
            view.value = 'result';
        };

        const goToPanel = () => { window.location.href = '/panel'; };

        const initStars = () => {
            const canvas = document.getElementById('cosmos');
            const ctx = canvas.getContext('2d', { alpha: false });
            let stars = [];
            const resize = () => { canvas.width = window.innerWidth; canvas.height = window.innerHeight; };
            window.addEventListener('resize', resize);
            resize();

            class Star {
                constructor() { this.reset(); }
                reset() {
                    this.x = Math.random() * canvas.width;
                    this.y = Math.random() * canvas.height;
                    this.r = Math.random() * 1.2 + 0.3;
                    this.speed = Math.random() * 0.08 + 0.02;
                    this.alpha = Math.random() * 0.5 + 0.2;
                }
                update() {
                    this.y -= this.speed;
                    if (this.y < -10) { this.y = canvas.height + 10; this.x = Math.random() * canvas.width; }
                }
                draw() {
                    ctx.fillStyle = `rgba(161, 161, 170, ${this.alpha})`;
                    ctx.beginPath(); ctx.arc(this.x, this.y, this.r, 0, Math.PI * 2); ctx.fill();
                }
            }

            for (let i = 0; i < 150; i++) stars.push(new Star());
            const anim = () => {
                ctx.fillStyle = '#09090b'; ctx.fillRect(0, 0, canvas.width, canvas.height);
                stars.forEach(s => { s.update(); s.draw(); });
                requestAnimationFrame(anim);
            };
            anim();
        };

        onMounted(async () => {
            try {
                const res = await fetch('/api/locale');
                translations.value = await res.json();
            } catch (e) {}
            initStars();

            if (window.location.search.includes('error=')) {
                const params = new URLSearchParams(window.location.search);
                view.value = 'login';
                result.ok = false;
                result.msg = params.get('error');
                result.msgKey = null;
            }
        });

        return {
            view, lang, loading, form, result, t, setLang,
            handleLogin, handleSsoLogin, terminate, goToPanel,
            ssoAvailable, checkingSso
        };
    }
}).mount('#app');
