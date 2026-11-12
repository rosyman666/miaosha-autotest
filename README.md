# 接口自动化测试工程（秒杀系统）

![CI](https://github.com/rosyman666/miaosha-autotest/actions/workflows/ci.yml/badge.svg)
![Python](https://img.shields.io/badge/python-3.11-blue)
![pytest](https://img.shields.io/badge/test-pytest%209-0A9EDC)
![License](https://img.shields.io/badge/license-MIT-green)

用 Pytest + Requests 对本地秒杀系统做的接口自动化工程。用例写在 YAML 里，由一套断言引擎驱动：
加一条边界值只改数据文件，不改代码；跑挂的时候把请求和响应直接贴在报告里，不用再复跑加 print。

## 目录结构

```
miaosha-autotest/
├── common/
│   ├── api_client.py      # 请求层：会话封装、请求记录、限流节奏
│   ├── cases.py           # 数据层：读 YAML 用例、解析占位符、结构校验
│   ├── expectation.py     # 断言层：把 expect 声明翻译成校验
│   ├── runner.py          # 执行层：一条用例 -> 一次请求 -> 一次断言
│   ├── reporting.py       # 展示层：请求/响应渲染成报告附件
│   └── env_loader.py      # 环境配置读取
├── data/
│   ├── cases/
│   │   ├── login.yaml     # 登录模块 9 条
│   │   ├── goods.yaml     # 商品模块 9 条
│   │   └── miaosha.yaml   # 秒杀模块 13 条
│   ├── env.yaml           # 环境地址、测试账号（与代码分离）
│   └── env.local.yaml     # 本机私有配置（含库密码），已被 gitignore
├── testcases/
│   ├── test_login.py      # 驱动登录用例集
│   ├── test_goods.py      # 驱动商品用例集
│   ├── test_miaosha.py    # 驱动秒杀用例集
│   ├── test_order_flow.py # 完整下单链路 + 限流触发（写操作，marker 隔离）
│   └── test_framework.py  # 框架自检：断言引擎单测 + 用例数据校验
├── tools/                 # 命令行工具：环境自检 / 数据重置 / 缓存对账
│   ├── __main__.py        # 入口：argparse 子命令
│   ├── settings.py        # 配置分层：环境变量 > env.local.yaml > env.yaml
│   ├── storage.py         # 唯一与 MySQL / Redis 建连接的地方，含 Redis key 规则
│   └── commands/          # doctor / seed / reconcile
├── docs/
│   ├── sample-report.html # 一次完整回归的 pytest-html 报告样例
│   └── allure/categories.json  # Allure 失败分类规则
├── .github/workflows/     # CI：语法检查 + 用例收集 + 框架自检 + Allure 产物
├── conftest.py            # 全局 fixture 与失败附件钩子
├── pytest.ini             # marker 注册、默认报告
├── reset-data.bat         # 兼容入口，实际调用 python -m tools seed
├── LICENSE
└── requirements.txt
```

分层思想：**请求、数据、断言、执行四件事各自独立**。
换环境改 `env.yaml`，加用例改 `data/cases/`，接口变了改 `api_client.py`，
断言不够用才动 `expectation.py`。

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
:: 常规回归（只读，不碰库存数据）：31 条接口用例 + 16 条框架自检
.venv\Scripts\python -m pytest

:: 只跑某个模块（用例编号前缀就是 -k 的过滤条件）
.venv\Scripts\python -m pytest -k MIAOSHA

:: 含秒杀下单的写操作用例（会消耗库存，先把数据重置回基线）
.venv\Scripts\python -m tools seed --stock 10
.venv\Scripts\python -m pytest -m miaosha_write

:: 跑完对账，确认库存、订单、缓存三者一致
.venv\Scripts\python -m tools reconcile --total 10
```

常规回归跑完会在根目录生成单文件 `report.html`，可直接打开；`docs/sample-report.html` 是一次完整回归的报告样例。

### Allure 报告

```bat
.venv\Scripts\python -m pytest --alluredir=allure-results
allure serve allure-results
```

`allure` 命令需要单独安装（[allure-commandline](https://github.com/allure-framework/allure2/releases) 解压后把 `bin` 加进 PATH，需要 Java 8+）。
报告里按 epic/feature/story 三级组织，每条用例带编号、严重级、缺陷说明，失败的用例会附上请求/响应。
CI 里已经跑通这一步并上传产物，本地不装也能看 `report.html`。

## 加一条用例

以「手机号超过 11 位」为例，往 `data/cases/login.yaml` 里加一段就行，不需要动 Python：

```yaml
  - id: LOGIN-010
    title: 手机号 12 位被拒绝
    severity: normal
    auth: false          # 用未登录的干净会话
    defect: true         # 断言的是当前真实行为，修好后本条会失败
    note: 当前返回 30005；正确应为 30001(参数校验异常)。
    request:
      method: post
      path: /login/do_login
      form:
        mobile: "130000000001"
        password: "${user.password_cipher}"
    expect:
      status: 200
      json:
        code: 30005
```

三条约定：

- **`id` 全局唯一**，报告里按它定位；`-k` 也能直接按编号过滤
- **`${...}` 是环境占位符**，可取 `env.yaml` 里的任意字段（`${user.mobile}`、`${goods_id}`），整串是占位符时保留原类型
- **`auth: false`** 表示用未登录会话执行。复用已登录的 client 去断言「未登录会被拦截」，永远不会失败

### expect 能写什么

| 关键字 | 含义 |
|---|---|
| `status` | HTTP 状态码相等 |
| `json` | 按点路径取值后相等，如 `data.goods.goodsName` |
| `json_not` | 按点路径取值后不等 |
| `json_in` | 取值属于给定集合 |
| `json_exists` | 路径存在且非空（`null` / `""` / `[]` 都算空） |
| `json_absent` | 路径缺失或为空 |
| `json_type` | 类型：`int` / `float` / `number` / `str` / `bool` / `list` / `dict` |
| `json_matches` | 取值完整匹配给定正则 |
| `json_gt` / `json_ge` / `json_lt` | 数值比较 |
| `text_contains` | 响应原文包含子串（返回 HTML 的页面用它） |
| `header_contains` | 响应头包含子串，如 `Set-Cookie: token=` |
| `cookie` | `present` / `absent` |
| `content_length_gt` | 响应体字节数大于给定值（验证码图片用它） |

一次收集全部不符项再抛错，而不是遇到第一个就中断——一条用例常常同时校验状态码、业务码、关键字段，
逐个报错会把「改了三次才跑通」变成日常。失败信息长这样：

```
MIAOSHA-006 期望不满足（2 项）
  - json.code: 期望 0，实际 30004
  - json.data: 期望存在且非空，实际 None
```

### 前置请求 pre

有些用例必须先让系统进入某个状态。最典型的是秒杀验证码：`checkVerifyCode` 校验通过即删 Redis key，
验证码是一次性的，想验证「不传验证码会怎样」，得先重新生成一张：

```yaml
    pre:
      - method: get
        path: /miaosha/verifyCode
        params:
          goodsId: "${goods_id}"
```

加了 pre 之后，这条用例单独跑和全量跑结果一致——用例不依赖执行顺序。

## 失败时自动附上请求/响应

排查接口用例最费时间的不是断言本身，而是「它到底发了什么、服务返回了什么」。
`conftest.py` 里挂了一个 `pytest_runtest_makereport` 钩子，用例失败时把本次发出的请求和响应
写进报告（pytest-html 的 section + Allure 的 attachment），跑挂当场就能看到现场：

```
GET http://localhost:8003/miaosha/verifyCode
query  : {"goodsId": 1}
cookies: token=f5c87716...(已脱敏)
------------------------------------------------------------
HTTP 200   耗时 5.3 ms
响应头 : {"Set-Cookie": "token=f5c87716...", "Content-Type": "application/json"}
响应体 :
{"status":"SUCCESS","code":30005,"message":"Session不存在或者已经失效!",...}
```

两个细节：

- **按用例切片，不是取最后 N 条**。client 是 session 级全程复用，`exchanges` 里存着前面几十条用例的请求，
  钩子按本条用例的开始时刻过滤，只展示自己发的请求
- **token 脱敏**。报告要能看出「有没有下发」，不需要能复用它

## 限流感知

秒杀三个接口都挂了 `@AccessLimit(seconds = 5, maxCount = 5)`，计数 key 是 URI + 用户名（不含 query）。
用例连着打同一个接口很容易撞上限流，报出来的 30002 长得像业务错误，排查方向会歪。

所以用例里用 `rate_limit` 声明接口的限流参数，执行器按记录的调用时间戳提前让路，留一次余量：

```yaml
    rate_limit: {seconds: 5, max_count: 5}
```

只有真要测限流本身时（`test_access_limit_returns_30002`）才故意打满窗口，
那条用例会先等满一个窗口再连续发 6 次。

## 用例清单

### 接口用例（31 条）

| 模块 | 条数 | 覆盖点 |
|---|---|---|
| 登录 | 9 | 正常登录并下发 token；密码错误 30010；手机号不存在 30009；密码过短/为空、缺 mobile、缺 password、手机号格式非法、手机号为空串 6 个参数校验入口 |
| 商品 | 9 | 列表页可访问；详情主体字段；价格与库存字段类型；秒杀状态字段；不存在商品；goodsId 非数字/负数/0；未登录可查看详情 |
| 秒杀 | 13 | 验证码出图；验证码缺参数/类型错误；错误验证码被拒；`verifyCode=0` 通过；不传验证码也通过；结果轮询取值约定；结果缺参数；未登录三连拒绝；缺 path 段返回 404；伪造 path 被拒 |

其中 17 条是**缺陷锁定用例**（`defect: true`），断言的是「当前真实行为」，项目修复后这些用例会失败，
届时把断言改成正确值即完成回归确认。详见下一节。

### 写操作用例（2 条，`-m miaosha_write`）

| 用例 | 内容 |
|---|---|
| `test_full_order_flow` | 出验证码 → 换令牌 → 下单 → 轮询订单号；顺带断言 seed 后 `result` 返回 0 |
| `test_access_limit_returns_30002` | 等满窗口后连发 6 次，第 6 次被限流，并钉住 30002 的文案 |

### 框架自检（16 条，不连被测服务）

`testcases/test_framework.py` 用假的 Response 对象跑断言引擎：等值、不等、存在、缺失、类型
（`true` 不能冒充 `int`）、正则、数值比较、Cookie 存在性、未知关键字必须报错、一次报出全部不符项。
另外校验三份 YAML：字段齐全、编号唯一、`method`/`path` 合法、断言关键字都是支持的。

这部分**能在托管的 CI 里真跑**——被测系统依赖 MySQL/Redis/RabbitMQ，CI 里没有，
但「改 YAML 漏了字段」「断言引擎把 bool 当 int」这类错误不该等到本地跑全量才发现。

## 用例钉住的缺陷

用例不是都断言「正确行为」。下面这些按当前真实行为固定下来，并注明了应该是什么。

### 1. 参数校验错误被伪装成「会话失效」

`LoginVo` 上声明了 `@NotNull` / `@MobileCheck` / `@Length(min = 32)`，参数不合法时本该返回
`30001 BIND_ERROR` 并带上具体校验信息。实际 `GlobleExceptionHandler` 把 `BindException` 一律映射成
`SESSION_ERROR(30005)`：

```java
} else if (e instanceof BindException) {
    ...
    return ResultGeekQ.error(SESSION_ERROR);   // 与参数校验毫无关系
}
```

前端只会提示「Session 不存在或者已经失效」，用户看到的和真实原因完全无关。
更离谱的是枚举里 `BIND_ERROR(30001)`、`PASSWORD_EMPTY(30006)`、`MOBILE_EMPTY(30007)`、
`MOBILE_ERROR(30008)` 四个更精确的码全部闲置，一个都没被用上。

涉及用例：`LOGIN-004` ~ `LOGIN-009`（6 个入口，同一个根因）。

### 2. 验证码的「正确答案」恒为 0

```java
private static int calc(String exp) {
    try {
        ScriptEngineManager manager = new ScriptEngineManager();
        ScriptEngine engine = manager.getEngineByName("JavaScript");
        Integer catch1 = (Integer) engine.eval(exp);
        return catch1.intValue();
    } catch (Exception e) {
        e.printStackTrace();
        return 0;          // 异常被吞掉，答案固定成 0 写进 Redis
    }
}
```

并发依赖 JDK 17，而 Nashorn 在 JDK 15 就被移除，`getEngineByName("JavaScript")` 返回 null，
`engine.eval()` 抛 NPE 后 `return 0`。于是 Redis 里存的「正确答案」永远是 0，
`checkVerifyCode` 只要传 `verifyCode=0` 就通过。异常被 `printStackTrace` 吞掉，
日志里只有一段堆栈，业务上完全静默。

涉及用例：`MIAOSHA-005`。

### 3. 不传验证码也能拿到下单令牌

```java
@RequestParam(value = "verifyCode", defaultValue = "0") int verifyCode
```

不传即按 0 处理，叠加上一条，等于验证码环节可以整段跳过。
攻击者只需要发一次 `verifyCode` 请求（完全不用看图片内容），再拼一个不带 `verifyCode` 的 URL 就能拿到令牌。
人机校验没有起到任何拦截作用。

涉及用例：`MIAOSHA-006`。

### 4. 30002 / 30004 的枚举名和文案互为颠倒

```java
ACCESS_LIMIT_REACHED(30002, "请求非法!"),   // 限流拦截器返回这个：文案却是"请求非法"
REQUEST_ILLEGAL(30004, "访问太频繁!"),       // 验证码校验失败返回这个：文案却是"访问太频繁"
```

用户验证码输错，看到的是「访问太频繁」；点太快被限流，看到的是「请求非法」。
两个提示正好指向相反的原因。

涉及用例：`MIAOSHA-004`、`MIAOSHA-013`、`test_access_limit_returns_30002`。

### 5. 异常路径一律兜底成 10001「系统错误」

查不存在的商品、`goodsId` 传 `abc` / `-1` / `0`、缺少必填的 `goodsId`——
这些本该是「商品不存在」「参数错误」，实际全部返回 `10001 系统错误`（未处理的 NPE 与类型转换异常被全局兜底）。
前端拿不到可展示的文案，用户不知道是商品下架了、链接错了，还是服务挂了。

涉及用例：`GOODS-005` ~ `GOODS-008`、`MIAOSHA-002`、`MIAOSHA-003`、`MIAOSHA-008`。

### 6. 缓存与数据库不一致（接口层看不出来，靠对账）

秒杀系统的库存同时存在于 MySQL 和 Redis，「是否已下单」的判定也同时存在于两处。
下单接口返回成功、库里却没有订单，或者有订单却查不到库存扣减，这类问题在接口层是完全成功的，
只有对账能发现。`python -m tools reconcile` 就是干这个的：

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

调试写操作用例时还踩到一个直接后果：只删数据库订单、不清 Redis `OrderKey`，用户仍然无法重新下单，
接口返回 40002「不能重复秒杀」——因为判定读的是缓存，不查库。这就是 `tools seed` 要同时清两边的原因。

## 配套工具（tools/）

用例只读地验证系统行为；`tools/` 下是允许写操作的命令行工具，用来给回归准备数据基线、核对三层存储。

| 命令 | 作用 |
|---|---|
| `python -m tools doctor` | 自检 MySQL、Redis、应用、RabbitMQ；任一必需项不通过时退出码非 0 |
| `python -m tools seed --stock 10` | 重置基线：DB 库存、清订单、同步 Redis 库存并清下单标记与验证码缓存 |
| `python -m tools seed --stock 10 --dry-run` | 只打印将要执行的 SQL 与 Redis 命令，不改数据 |
| `python -m tools reconcile --total 10` | 对账：库存是否一致、已售数量与订单数是否吻合、缓存标记能否对上库内订单 |

**配置分层。** `data/env.yaml` 只放地址、端口、库名，密码留空；
本机密码写 `data/env.local.yaml`（已加入 `.gitignore`），
也可以用 `MIAOSHA_DB_PASSWORD`、`MIAOSHA_REDIS_PASSWORD`、`MIAOSHA_BASE_URL` 等环境变量覆盖。

**doctor 的一个坑。** 本机装了代理软件时，请求 `localhost:8003` 会被代理转走并返回 502，
看起来像应用没起来。`doctor` 和用例的 `ApiClient` 都显式设了 `trust_env=False`，绕开系统代理再判断。

## 持续集成

`.github/workflows/ci.yml`：push 后依次做四件事。

1. 语法检查（`compileall`）
2. 命令行工具入口可用
3. 用例可收集性检查——YAML 语法错、`parametrize` 写错、占位符引用了不存在的字段，这一步就会失败
4. 框架自检 + 生成 Allure 报告，产物上传为 artifact（保留 7 天）

被测的秒杀系统是本地部署的（MySQL + Redis + RabbitMQ + 应用 8003），托管 CI 环境里没有这套服务，
所以 CI 不跑真实接口，只验证「工程可安装、可导入、用例可发现、框架逻辑正确」。
**完整回归在本地服务起来后执行。**

## 设计决策 FAQ

- **为什么不直接写 pytest 函数，要用 YAML？** 31 条用例里有 17 条是同一个接口的不同输入，
  写 Python 就是复制粘贴 + 改期望值，加边界值还得改代码。放 YAML 后，加一条用例是加 8 行数据，
  而且数据文件可以单独 review。
- **为什么要单独一个断言引擎？** 三种模块的断言结构是一样的（状态码、业务码、关键字段），
  分散在用例里就会写出十种风格。收敛到 `expectation.py` 后，一次收集全部不符项、失败消息格式统一，
  加新的断言方式也只改一个文件。
- **为什么登录放 session fixture？** 一次登录、全程复用 Cookie，不重复打登录接口。
  「未登录会怎样」另开 `anon_client`，两个场景不互相污染。
- **为什么有用例断言的是「错误行为」？** 见上文「用例钉住的缺陷」：用例也是质量资产，
  先钉住现状、把根因写进注释，修复后用例失败即提醒改断言。比写在文档里更容易被执行。
- **为什么失败才挂请求响应？** 通过的用例附上请求会把报告撑成几十页，没人看。
  失败现场才有排查价值。
- **为什么 reset-data.bat 改成调用 Python？** 原来那个 bat 里硬编码了本机 mysql.exe 路径和库密码，
  换台机器就跑不了，密码还进了公开仓库；现在工具读配置、支持 `--dry-run`、执行后打印前后对比，也能在 CI 里复用。
- **工具为什么用 Python 而不是 Java？** 工程本身是 Python，工具和用例共用 `data/env.yaml`，
  不需要再起一套构建；对账逻辑本身也不依赖语言特性。
- **为什么工具和用例分两个目录？** 用例遵守只读约束（写操作要靠 mark 显式打开），工具天然会改数据。
  放在一起容易让后来者误以为可以直接在用例里改库。
