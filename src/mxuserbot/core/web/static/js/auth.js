const { createApp, ref, reactive, onMounted } = Vue;

createApp({
    setup() {
        const view = ref('welcome');
        const lang = ref(localStorage.getItem('lang') || 'en');
        const loading = ref(false);
        const translations = ref({});
        const form = reactive({ mxid: '', password: '' });
        const result = reactive({ ok: false, msg: '' });

        const t = (key) => {
            return (translations.value[lang.value] && translations.value[lang.value][key]) || 
                   (translations.value['en'] && translations.value['en'][key]) || key;
        };

        const setLang = (l) => {
            lang.value = l;
            localStorage.setItem('lang', l);
        };

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
                result.msg = res.ok ? (t('session_initialized') || 'Success') : (data.detail || t('result_failed'));
                view.value = 'result';
            } catch (e) {
                result.ok = false;
                result.msg = t('server_unreachable');
                view.value = 'result';
            }
            loading.value = false;
        };

        const terminate = () => {
            result.ok = false;
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
        });

        return { view, lang, loading, form, result, t, setLang, handleLogin, terminate, goToPanel };
    }
}).mount('#app');