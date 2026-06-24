# 秒杀系统

基于 Flask + Redis 的限时抢购系统，使用 Redis Lua 脚本实现原子扣库存，防止超卖。

## 功能

- **用户认证** — 注册/登录/登出，强密码策略（8位+、字母+数字），用户名支持中英文
- **秒杀核心** — 商品列表、详情页、Redis Lua 原子扣库存、一人一单限购、定时上架/下架、倒计时
- **后台管理** — 商品 CRUD、软删除、上下架切换、订单查看，管理员权限控制
- **安全防护** — CSRF Token、OpenRedirect 修复、安全响应头（CSP 等）、双限流策略
- **前端界面** — 响应式布局、深色/浅色模式、侧边栏导航、移动端底部导航、毛玻璃效果

## 技术栈

| 组件 | 用途 |
|------|------|
| Flask 3.1 | Web 框架 |
| Flask-SQLAlchemy | ORM（默认 SQLite，可切换 MySQL/PostgreSQL） |
| Flask-Login | 用户会话管理 |
| Redis 7 | 原子库存扣减 + 限流计数器 |
| Lua Script | Redis 内原子执行库存检查→扣减→记录用户，防竞态 |
| Werkzeug | 密码哈希 / 安全工具 |

## 快速开始

```bash
# 1. 启动 Redis
docker-compose up -d

# 2. 安装依赖
pip install -r requirements.txt

# 3. 配置环境变量
cp .env.example .env
# 修改 SECRET_KEY 为随机字符串

# 4. 启动应用
python app.py
```

打开 <http://localhost:5000>。

> **首次使用：** 注册第一个账号后，需手动在数据库中将 `is_admin` 设为 `1` 来获得管理员权限。SQLite 示例：
> ```bash
> sqlite3 instance/seckill.db "UPDATE users SET is_admin=1 WHERE id=1;"
> ```

## 路由架构

| 蓝图 | URL 前缀 | 说明 |
|------|----------|------|
| `auth_bp` | `/auth` | 登录、注册、登出 |
| `seckill_bp` | `/` | 首页、商品详情、抢购 API、我的订单 |
| `admin_bp` | `/admin` | 后台管理（需管理员权限） |

### API 端点

| 方法 | 路径 | 说明 |
|------|------|------|
| `POST` | `/api/seckill` | 抢购接口，JSON 参数 `product_id`，需登录 |

## 项目结构

```
.
├── app.py                    # 应用工厂 & 入口
├── config.py                 # 配置（从环境变量读取）
├── requirements.txt
├── docker-compose.yml        # Redis 服务
├── .env.example
├── core/
│   ├── models.py             # User / Product / Order 数据模型
│   ├── auth.py               # 认证蓝图（登录/注册/登出）
│   ├── seckill.py            # 秒杀蓝图（首页/详情/抢购API/订单）
│   ├── admin.py              # 后台管理蓝图（商品管理/订单查看）
│   ├── csrf.py               # CSRF Token 生成与校验
│   ├── limiter.py            # Redis 滑动窗口限流
│   └── redis_client.py       # Redis 连接池初始化
├── static/
│   └── style.css             # 完整设计系统（Design Tokens / 毛玻璃 / Bento Grid）
└── templates/
    ├── base.html             # 基础布局（侧边栏 / 状态栏 / 移动导航）
    ├── index.html            # 秒杀商品列表
    ├── product_detail.html   # 商品详情
    ├── login.html
    ├── register.html
    ├── orders.html           # 我的订单
    ├── 404.html / 500.html   # 错误页
    ├── _pagination.html      # 分页组件
    └── admin/
        ├── index.html        # 管理后台首页
        ├── products.html     # 商品管理
        └── orders.html       # 订单列表
```

## 配置项

| 环境变量 | 默认值 | 说明 |
|----------|--------|------|
| `SECRET_KEY` | — | Flask 密钥，**生产务必修改** |
| `DATABASE_URL` | `sqlite:///seckill.db` | 数据库连接（支持 MySQL/PostgreSQL） |
| `REDIS_HOST` | `localhost` | Redis 地址 |
| `REDIS_PORT` | `6379` | Redis 端口 |
| `REDIS_PASSWORD` | — | Redis 密码（可选） |
| `REDIS_DB` | `0` | Redis 数据库编号 |
| `RATE_LIMIT_MAX` | `30` | 限流窗口内最大请求数 |
| `RATE_LIMIT_WINDOW` | `30` | 限流窗口秒数 |
| `FLASK_DEBUG` | `0` | 调试模式开关 |

## 核心设计

### 防超卖

抢购 API 先通过 Redis Lua 脚本原子检查库存 + 记录用户（单次往返），成功后再异步写 MySQL，Redis 失败直接拒绝。

流程：
1. Lua 脚本原子执行：`SISMEMBER` 检查是否已购买 → `GET` + `DECR` 扣库存 → `SADD` 记录用户
2. Redis 成功后，SQLAlchemy `UPDATE ... WHERE stock > 0` 二次校验扣减 MySQL 库存
3. 创建订单记录

Redis 不可用时优雅降级，提示系统繁忙而非直接崩溃。

### 一人一单

每个商品的已购买用户集合存储在 Redis Set 中（`seckill:users:{product_id}`），由 Lua 脚本在扣库存时原子检查，杜绝重复购买。

### 软删除

管理后台删除商品时仅标记 `is_deleted=True` + `is_active=False`，商品 ID 永久保留，关联订单不受影响。同时清理 Redis 中对应库存和用户集合。

### 限流

双限流策略，使用 Redis 滑动窗口算法（ZSET + Lua）：

| 场景 | 限流 Key | 默认阈值 |
|------|----------|----------|
| 秒杀接口（已登录） | `rate_limit:{user_id}` | 30次/30s |
| 登录（未登录） | `rate_limit:login:{ip}` | 10次/60s |
| 注册（未登录） | `rate_limit:register:{ip}` | 5次/300s |

### CSRF 防护

- 所有 POST 表单携带 `_csrf_token`，Session 内比对
- 使用 `secrets.compare_digest` 防时序攻击
- `csrf_required` 装饰器统一校验

### OpenRedirect 修复

登录后跳转只允许相对路径（以 `/` 开头且不以 `//` 开头），拒绝外部 URL。

### 安全响应头

```python
X-Content-Type-Options: nosniff
X-Frame-Options: DENY
X-XSS-Protection: 0
Referrer-Policy: strict-origin-when-cross-origin
```

### 倒计时

自定义 Jinja 过滤器 `countdown`，将 `timedelta` 格式化为中文"X天X时X分"显示，秒杀开始前自动倒计时。

### 日志

应用级结构化日志，格式为 `时间 [级别] 模块: 消息`，记录关键操作（秒杀成功、管理员操作、登录失败等）。

### 密码策略

- 最少 8 位
- 必须同时包含字母和数字
- 使用 Werkzeug 内置哈希（自动加盐）

## 许可证

MIT