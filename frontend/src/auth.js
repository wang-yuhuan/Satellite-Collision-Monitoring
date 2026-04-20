export class AuthManager {
    constructor(config) {
        this.config = config;

        this.overlay = document.getElementById('auth-overlay');
        this.msgBox = document.getElementById('auth-msg');

        this.viewLogin = document.getElementById('view-login');
        this.viewRegister = document.getElementById('view-register');

        // 配置 API 地址
        this.api = {
            login: this.config.API.LOGIN,
            register: this.config.API.REGISTER
        };

        this._bindEvents();

        this.particleSystem = new ParticleNetwork('constellation-canvas');
    }

    _bindEvents() {
        // 切换视图按钮
        document.getElementById('btn-goto-register')?.addEventListener('click', () => this._switchView('register'));
        document.getElementById('btn-goto-login')?.addEventListener('click', () => this._switchView('login'));
        
        // 提交按钮
        document.getElementById('btn-do-login')?.addEventListener('click', () => this._handleLogin());
        document.getElementById('btn-do-register')?.addEventListener('click', () => this._handleRegister());
    }

    _switchView(target) {
        this._updateStatus("STANDBY");
        if (target === 'register') {
            this.viewLogin.classList.add('hidden');
            this.viewRegister.classList.remove('hidden');
        } else {
            this.viewRegister.classList.add('hidden');
            this.viewLogin.classList.remove('hidden');
        }
    }

    // ==========================================
    // 核心修改：真实的登录请求
    // ==========================================
    async _handleLogin() {
        const userInp = document.getElementById('login-user');
        const passInp = document.getElementById('login-pass');
        const user = userInp.value.trim();
        const pass = passInp.value.trim();

        if (!user || !pass) {
            this._updateStatus("ERROR: INPUT REQUIRED", true);
            return;
        }

        this._updateStatus("VERIFYING ENCRYPTION KEYS...", false);

        try {
            const res = await fetch(this.api.login, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: user, password: pass })
            });

            const data = await res.json();

            if (data.success) {
                this._updateStatus("ACCESS GRANTED.");
                this._unlockSystem();
            } else {
                // 显示后端返回的具体错误信息 (例如: User not found)
                this._updateStatus(`ACCESS DENIED: ${data.message.toUpperCase()}`, true);
                passInp.value = ''; // 密码错误清空密码框
            }

        } catch (err) {
            console.error(err);
            this._updateStatus("CONNECTION FAILURE: SERVER UNREACHABLE", true);
        }
    }

    // ==========================================
    // 核心修改：真实的注册请求
    // ==========================================
    async _handleRegister() {
        const userInp = document.getElementById('reg-user');
        const passInp = document.getElementById('reg-pass');
        const confInp = document.getElementById('reg-pass-confirm');
        
        const user = userInp.value.trim();
        const pass = passInp.value.trim();
        const conf = confInp.value.trim();

        if (!user || !pass) return this._updateStatus("ERROR: DATA MISSING", true);
        if (pass !== conf) return this._updateStatus("ERROR: PASSWORD MISMATCH", true);

        this._updateStatus("UPLINKING NEW IDENTITY...", false);

        try {
            const res = await fetch(this.api.register, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: user, password: pass })
            });

            const data = await res.json();

            if (data.success) {
                alert(`IDENTITY [${user}] REGISTERED SUCCESSFULLY.`);
                
                // 注册成功，切回登录页，并自动填入用户名
                this._switchView('login');
                document.getElementById('login-user').value = user;
                this._updateStatus("REGISTRATION COMPLETE. PLEASE LOGIN.");
                
                // 清空注册框
                userInp.value = ''; passInp.value = ''; confInp.value = '';
            } else {
                this._updateStatus(`REGISTRATION FAILED: ${data.message.toUpperCase()}`, true);
            }

        } catch (err) {
            console.error(err);
            this._updateStatus("SYSTEM ERROR: UNABLE TO WRITE DATA", true);
        }
    }

    _unlockSystem() {
        this.overlay.classList.add('unlocked');
        document.dispatchEvent(new Event('auth:success'));

        if (this.particleSystem) {
            // 稍微延迟一点销毁，配合 fade-out 动画
            setTimeout(() => {
                this.particleSystem.destroy();
            }, 1000);
        }

    }

    _updateStatus(text, isError = false) {
        this.msgBox.innerText = text;
        this.msgBox.style.color = isError ? '#ff5050' : 'rgba(255,255,255,0.5)';
        this.msgBox.style.textShadow = isError ? '0 0 5px #ff0000' : 'none';
        
        // 只有错误时才抖动
        if (isError) {
            const box = document.querySelector('.auth-box');
            box.classList.remove('shake'); // 重置动画
            void box.offsetWidth; // 触发重绘
            box.classList.add('shake');
        }
    }
}




class ParticleNetwork {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        if (!this.canvas) return;

        this.ctx = this.canvas.getContext('2d');
        this.particles = [];
        this.animationFrameId = null;

        // 配置参数
        this.config = {
            count: 200,           // 粒子数量
            color: '#00f3ea',    // 粒子颜色 (Holo-Cyan)
            lineColor: '0, 243, 234', // 线条颜色 RGB (方便调节透明度)
            lineWidth: 1.8,        // [新增] 线宽：默认是1，建议改为 1.5 或 2 (太粗会像棍子)
            radius: 1.5,           // 粒子半径
            speed: 0.5,          // 移动速度
            range: 120,          // 连线距离阈值
            mouseRange: 100      // 鼠标互动范围
        };

        // 鼠标位置追踪
        this.mouse = { x: null, y: null };

        this._resize();
        this._initParticles();
        this._bindEvents();
        this.animate();
    }

    _bindEvents() {
        // 监听窗口大小改变
        window.addEventListener('resize', () => {
            this._resize();
            this._initParticles();
        });

        // 监听鼠标移动 (整个窗口)
        window.addEventListener('mousemove', (e) => {
            this.mouse.x = e.clientX;
            this.mouse.y = e.clientY;
        });

        // 鼠标移出窗口时清除位置
        window.addEventListener('mouseout', () => {
            this.mouse.x = null;
            this.mouse.y = null;
        });
    }

    _resize() {
        this.canvas.width = window.innerWidth;
        this.canvas.height = window.innerHeight;
    }

    _initParticles() {
        this.particles = [];
        for (let i = 0; i < this.config.count; i++) {
            this.particles.push({
                x: Math.random() * this.canvas.width,
                y: Math.random() * this.canvas.height,
                vx: (Math.random() - 0.5) * this.config.speed,
                vy: (Math.random() - 0.5) * this.config.speed
            });
        }
    }

    animate() {
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
        
        // 1. 更新与绘制粒子
        for (let i = 0; i < this.particles.length; i++) {
            let p = this.particles[i];

            // 移动
            p.x += p.vx;
            p.y += p.vy;

            // 边界反弹
            if (p.x < 0 || p.x > this.canvas.width) p.vx *= -1;
            if (p.y < 0 || p.y > this.canvas.height) p.vy *= -1;

            // 鼠标互动 (斥力效果 - 模拟被鼠标推开)
            if (this.mouse.x != null) {
                let dx = this.mouse.x - p.x;
                let dy = this.mouse.y - p.y;
                let distance = Math.sqrt(dx*dx + dy*dy);
                
                if (distance < this.config.mouseRange) {
                    const forceDirectionX = dx / distance;
                    const forceDirectionY = dy / distance;
                    const force = (this.config.mouseRange - distance) / this.config.mouseRange;
                    
                    // 粒子被推开的方向
                    const repelStrength = 0.2; 
                    p.vx -= forceDirectionX * force * repelStrength * 0.1;
                    p.vy -= forceDirectionY * force * repelStrength * 0.1;
                }
            }

            // 绘制粒子点
            this.ctx.beginPath();
            this.ctx.arc(p.x, p.y, this.config.radius, 0, Math.PI * 2);
            this.ctx.fillStyle = this.config.color;
            this.ctx.fill();

            // 2. 绘制连线 (Constellation Logic)
            for (let j = i + 1; j < this.particles.length; j++) {
                let p2 = this.particles[j];
                let dist = Math.sqrt((p.x - p2.x)**2 + (p.y - p2.y)**2);

                if (dist < this.config.range) {
                    this.ctx.beginPath();
                    // 根据距离计算透明度 (越近越亮)
                    let opacity = 1 - (dist / this.config.range);
                    this.ctx.strokeStyle = `rgba(${this.config.lineColor}, ${opacity})`;
                    this.ctx.lineWidth = this.config.lineWidth;
                    this.ctx.moveTo(p.x, p.y);
                    this.ctx.lineTo(p2.x, p2.y);
                    this.ctx.stroke();
                }
            }
        }

        this.animationFrameId = requestAnimationFrame(() => this.animate());
    }

    destroy() {
        if (this.animationFrameId) {
            cancelAnimationFrame(this.animationFrameId);
        }
        // 清空画布
        this.ctx.clearRect(0, 0, this.canvas.width, this.canvas.height);
    }
}