# 秒杀系统

基于 Flask 的限时抢购系统，使用 Redis Lua 脚本实现原子扣库存，防止超卖。

## 功能

- **用户认证** — 注册/登录/登出，强密码策略（8位以上、字母+数字），用户名支持中英文
- **秒杀核心** — 商品列表、详情页、Redis 原子扣库存、一人一单限购、定时上架/下架
- **后台管理** — 商品 CRUD、上下架切换、订单查看，管理员权限控制
- **安全防护** — CSRF Token、OpenRedirect 修复、安全响应头、限流（Redis 滑动窗口）
- **前端界面** — 响应式布局、深色/浅色模式、侧边栏导航、移动端底部导航、毛玻璃效果

## 技术栈

| 组件 | 用途 |
|------|------|
| Flask 3.1 | Web 框架 |
| Flask-SQLAlchemy | ORM (SQLite / 可切换) |
| Flask-Login | 用户会话管理 |
| Redis 7 | 原子库存扣减 + 限流计数器 |
| Lua Script | Redis 内原子检查库存→扣减→记录用户，防竞态 |
| Werkzeug | 密码哈希 / 安全 |


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
    ├── product_detail.html    # 商品详情
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
| `RATE_LIMIT_MAX` | `5` | 限流窗口内最大请求数 |
| `RATE_LIMIT_WINDOW` | `60` | 限流窗口秒数 |
| `FLASK_DEBUG` | `0` | 调试模式开关 |

## 核心设计

**防超卖** — 抢购 API 先通过 Redis Lua 脚本原子检查库存 + 记录用户（单次往返），成功后再异步写 MySQL，Redis 失败直接拒绝。Redis 不可用时优雅降级，提示系统繁忙而非直接崩溃。

**限流** — 双限流策略：已登录用户按 `user_id` 限制秒杀接口频率，未登录用户按 IP 限制登录/注册频率。均使用 Redis 滑动窗口算法（ZSET），Lua 原子执行。

**CSRF** — 所有 POST 表单携带 `_csrf_token`，Session 内比对，使用 `secrets.compare_digest` 防时序攻击。

**OpenRedirect** — 登录后跳转只允许相对路径（以 `/` 开头且不以 `//` 开头），拒绝外部 URL。

## 许可证

MIT