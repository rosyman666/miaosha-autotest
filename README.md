# 接口自动化测试工程（秒杀系统）

![CI](https://github.com/rosyman666/miaosha-autotest/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.11-blue)
![pytest](https://img.shields.io/badge/test-pytest%209-0A9EDC)
![License](https://img.shields.io/badge/license-MIT-green)

用 Pytest + Requests 对本地秒杀系统做的接口自动化工程，把 Postman 集合里的核心断言迁移成了可一条命令回归的代码用例。

## 目录结构（三层设计）

```
miaosha-autotest/
├── common/
│   └── api_client.py      # 请求层：Requests 会话封装，登录态自动携带
├── data/
│   ├── env.yaml           # 数据层：环境地址、测试账号（与代码分离）
│   └── env.local.yaml     # 本机私有配置（含库密码），已被 gitignore
├── testcases/
│   ├── test_login.py      # 用例层：登录模块
│   ├── test_goods.py      # 用例层：商品模块
│   └── test_miaosha.py    # 用例层：秒杀模块（含写操作用例的 mark 隔离）
├── tools/                 # 命令行工具：环境自检 / 数据重置 / 缓存对账
│   ├── __main__.py        # 入口：argparse 子命令
│   ├── settings.py        # 配置分层：环境变量 > env.local.yaml > env.yaml
│   ├── storage.py         # 唯一与 MySQL / Redis 建连接的地方，含 Redis key 规则
│   └── commands/          # doctor / seed / reconcile
├── docs/
│   └── sample-report.html # 一次完整回归的 pytest-html 报告样例
├── .github/workflows/     # CI：语法检查 + 用例可收集性检查
├── conftest.py            # 全局 fixture：一次登录，整个会话复用
├── pytest.ini             # 配置：marker 注册、默认报告
├── reset-data.bat         # 兼容入口，实际调用 python -m tools seed
├── LICENSE
└── requirements.txt
```

分层思想：**请求封装、测试数据、用例逻辑三者分离**——换环境只改 `env.yaml`，加用例只写 `testcases/`，接口变了只改 `api_client.py`。

## 环境准备

被测系统需在本机运行，启动顺序不能颠倒：

`MySQL（库 miaosha）` → `Redis 6379` → `RabbitMQ 5672` → `被测应用 8003`

（本仓库只包含测试代码，被测系统为开源秒杀项目，需自行部署；接口地址与账号在 `data/env.yaml` 里改。）

## 安装依赖

```bat
python -m venv .venv
.venv\Scripts\python -m pip install -r requirements.txt
```

## 跑用例

```bat
:: 常规回归（只读，不碰库存数据）
.venv\Scripts\python -m pytest

:: 含秒杀下单的写操作用例（会消耗库存，先把数据重置回基线）
.venv\Scripts\python -m tools seed --stock 10
.venv\Scripts\python -m pytest -m miaosha_write

:: 跑完对账，确认库存、订单、缓存三者一致
.venv\Scripts\python -m tools reconcile --total 10

:: 生成 Allure 结果（需另装 allure 命令行，再执行 allure serve allure-results）
.venv\Scripts\python -m pytest --alluredir=allure-results
```

常规回归跑完会在根目录生成单文件 `report.html`，可直接打开查看；`docs/sample-report.html` 是一次完整回归的报告样例。

## 配套工具（tools/）

用例只读地验证系统行为；`tools/` 下是允许写操作的命令行工具，用来给回归准备数据基线、核对三层存储。

| 命令 | 作用 |
|---|---|
| `python -m tools doctor` | 自检 MySQL、Redis、应用、RabbitMQ；任一必需项不通过时退出码非 0 |
| `python -m tools seed --stock 10` | 重置基线：DB 库存、清订单、同步 Redis 库存并清下单标记与验证码缓存 |
| `python -m tools seed --stock 10 --dry-run` | 只打印将要执行的 SQL 与 Redis 命令，不改数据 |
| `python -m tools reconcile --total 10` | 对账：库存是否一致、已售数量与订单数是否吻合、缓存标记能否对上库内订单 |

**为什么需要 reconcile。** 秒杀系统的库存同时存在于 MySQL 和 Redis，
“是否已下单”的判定也同时存在于两处。这类不一致在接口层看不出来：
下单接口返回成功，但库里没有订单，或者有订单却查不到对应的库存扣减。
对账把这种“看起来成功”的状态变成可检测的差异项：

```
$ python -m tools reconcile --total 10
对账结果  goods_id=1
--------------------------------------------------------------------
[ OK ] 库存一致   DB 9 == Redis 9
[FAIL] 库存与订单  按库存推算已售 1，实际订单 0，差 1（疑似超卖或漏单）
[ OK ] 售罄标记   未标记售罄
[FAIL] 幽灵订单   1 个缓存标记在库里无对应订单：OrderKey:moug13000000000_1
[ OK ] 漏缓存    0 笔数据库订单均有缓存标记
--------------------------------------------------------------------
发现 2 项不一致
```

（上面这段是删掉数据库订单、保留 Redis 标记之后的实际输出。）

**配置分层。** `data/env.yaml` 只放地址、端口、库名，密码留空；
本机密码写 `data/env.local.yaml`（已加入 `.gitignore`），
也可以用 `MIAOSHA_DB_PASSWORD`、`MIAOSHA_REDIS_PASSWORD`、`MIAOSHA_BASE_URL` 等环境变量覆盖。

**doctor 的一个坑。** 本机装了代理软件时，请求 `localhost:8003` 会被代理转走并返回 502，
看起来像应用没起来。`doctor` 里显式设了 `trust_env=False`，绕开系统代理再判断。

## 用例清单（11 条）

| 模块 | 条数 | 覆盖点 |
|---|---|---|
| 登录 | 3 | 正常登录并下发 token Cookie；密码错误返回 30010 且不发 token；非法手机号参数校验（缺陷锁定） |
| 商品 | 3 | 列表页可访问且非空；详情返回 `goods.goodsName`；查不存在商品（缺陷锁定） |
| 秒杀 | 5 | 验证码接口可访问；错误验证码被拒；`verifyCode=0` 可通过校验（缺陷锁定）；结果轮询接口；完整下单链路（写操作，marker 隔离） |

## 持续集成

`.github/workflows/ci.yml`：push 后自动安装依赖、做语法检查、验证用例可被收集。

被测的秒杀系统是本地部署的（MySQL + Redis + RabbitMQ + 应用 8003），托管 CI 环境里没有这套服务，
所以 CI 只覆盖「工程可安装、可导入、用例可被发现」这一层，**完整回归在本地服务起来后执行**。

## 这套用例里藏了三个"缺陷锁定用例"

不是所有用例都断言"正确行为"——有三个用例**故意断言当前的真实行为**（哪怕它是错的），并注释了正确行为应该是什么：

| 用例 | 当前实际行为 | 正确行为 | 为什么这么写 |
|---|---|---|---|
| `test_login_invalid_mobile` | 参数校验失败返回 `30005 会话错误` | 应为 `30001 参数绑定错误` | 全局异常处理器把 BindException 映射错了；用例钉住现状，等修复后改断言 |
| `test_goods_detail_not_exist` | 查不存在商品返回 `10001 系统异常` | 应有友好业务提示 | 未处理的空指针被兜底成系统异常 |
| `test_path_verifycode_zero` | 验证码答案恒为 `0`（JDK17 移除 Nashorn 后异常被吞） | 应为随机算式结果 | 静默失败实证，这条过了反而说明缺陷还在 |

这就是为什么"52 条断言过 51 条"里那 1 条失败不是 bug 而是哨兵。

### 搭框架调试过程中又挖出的缺陷（第 7 个）

**错误码与文案错位，且语义对调**（`ResultStatus.java`）：

```java
ACCESS_LIMIT_REACHED(30002, "请求非法!"),     // 限流拦截器实际返回这个：文案却是"请求非法"
REQUEST_ILLEGAL(30004, "访问太频繁!"),        // path 接口验证码校验失败返回这个：文案却是"访问太频繁"
```

枚举名和文案正好互相颠倒。更糟的是：`/miaosha/path` 里 `checkVerifyCode` 失败时复用了 30004——
用户验证码输错，看到的提示是"**访问太频繁**"，完全误导排障方向。正确做法：
限流返回"访问太频繁"、验证码错误返回"验证码错误"，两个语义分开定义。

### 测试数据管理踩过的三个坑

调试 `miaosha_write` 用例时连续踩了三个"数据残留"坑，正好是三层存储的活教材：

| 现象 | 根因 | 清理动作 |
|---|---|---|
| path 接口返回 30004 | 验证码是**一次性消费**：`checkVerifyCode` 校验成功即删 Redis key，前面的用例把它用掉了 | 下单前先调 `/miaosha/verifyCode` 重新生成 |
| 下单报 40002 不能重复秒杀（DB 订单已清） | "是否已秒杀"的判定读的是 **Redis 订单缓存**（`OrderKey:moug...`），不查 DB | 删 Redis `OrderKey:*` |
| —— | 上面这条本身就是**缓存与 DB 不一致**的实证：只删 DB 订单，用户仍无法重新下单，直到缓存过期 | 与简历里"缓存与消息库存不一致"缺陷互相印证 |

=> 一键重置脚本：`reset-data.bat`

## 设计决策 FAQ

- 为什么不用 Postman 就够？——回归要人手点；脚本化后一条命令全量回归，接 CI 后 push 即跑
- 为什么登录放 fixture？——session 级登录一次，所有用例复用 Cookie，不重复打登录接口
- 数据为什么放 YAML？——换环境/换账号不改代码；后面参数化 5000 个种子账号就是换数据文件的事
- 为什么有用例断言的是"错误行为"？——见上文「缺陷锁定用例」一节：用例也是质量资产，先钉住现状，修复后随版本一起改断言
- 为什么 reset-data.bat 改成调用 Python？——原来那个 bat 里硬编码了本机 mysql.exe 路径和库密码，换台机器就跑不了，密码还进了公开仓库；现在工具读配置、支持 `--dry-run`、执行后打印前后对比，也能在 CI 里复用
- 工具为什么用 Python 而不是 Java？——工程本身是 Python，工具和用例共用 `data/env.yaml`，不需要再起一套构建；对账逻辑本身也不依赖语言特性
- 为什么工具和用例分两个目录？——用例遵守只读约束（写操作要靠 mark 显式打开），工具天然会改数据。放在一起容易让后来者误以为可以直接在用例里改库
