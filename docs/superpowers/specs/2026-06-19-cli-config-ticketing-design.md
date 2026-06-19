# 纯 CLI 配置化电影购票改造设计

## 目标

将项目改造成无需 FastAPI、网页或前后端交互的纯 Python CLI 工具。用户只需编辑一份 `config.local.json`，直接运行脚本即可查询场次、匹配指定座位、锁座、使用会员卡付款并保存取票信息；`--check-only` 只查询和校验，不锁座、不付款。

## 范围

- 保留 `direct_ticketing.py` 中已验证的场次匹配、指定座位解析、锁座、会员卡支付和出票逻辑。
- 保留工作区中尚未提交的日期范围校验，以及 `channelOrderCode` 用于支付、`orderCode` 用于出票查询的修正。
- 删除 FastAPI 应用、浏览器页面、API 路由、相关依赖和 API 测试。
- 删除订单与影院配置分离的旧使用方式，改为默认读取单一配置文件。
- 不实现 `openId` 自动获取；CLI 从本地配置读取固定值。首轮本地测试使用用户提供的 `openId`，脱敏示例不保存真实值。
- 不扩展到不同协议的影院系统，只支持当前 `pandl.xyz/JavaWeb2` 同系统小程序。

## CLI 行为

- `python movie_ticket_cli.py`：读取默认的 `config.local.json` 并执行真实锁座、会员卡付款和出票查询。
- `python movie_ticket_cli.py --check-only`：查询场次和座位，输出匹配结果，但不调用锁座和付款接口。
- `python movie_ticket_cli.py --config <path>`：使用指定配置文件。
- 配置无效时在任何真实锁座请求前终止，并输出明确的配置字段错误。
- 命令以非零退出码表示配置错误、没有匹配场次、座位不可用、锁座失败或付款失败。

## 配置结构

默认测试配置使用现有小程序参数：

```json
{
  "miniProgram": {
    "baseUrl": "https://pandl.xyz",
    "cinemaCode": "34025901",
    "referer": "https://servicewechat.com/wx52420337e5796bd6/15/page-frame.html",
    "distributorId": ""
  },
  "account": {
    "openId": "本地配置中填写固定值",
    "memberCardPassword": "填写会员卡密码"
  },
  "order": {
    "movieName": "电影名称",
    "showDate": "2026-06-19",
    "startTime": "14:30",
    "hallName": "",
    "filmLanguage": "",
    "showType": "",
    "seatNames": ["5排9号"],
    "priceMax": 80
  },
  "runtime": {
    "timeout": 20,
    "outputDir": "picture"
  }
}
```

`config.example.json` 保存脱敏模板，`config.local.json` 保存本地实际值并被 Git 忽略。标准微信小程序请求头由程序生成；允许通过可选配置覆盖公共请求头和接口路径。订单票数由 `seatNames` 自动推导。

## 请求参数配置化

所有场次、座位、锁座、会员卡、会员价、支付和订单查询请求统一从 `miniProgram` 读取 `baseUrl`、`cinemaCode` 和 `referer`。代码中删除 `34025901` 等影院默认常量，避免切换小程序后部分请求仍发送旧参数。

用户提供的 `QueryCinema` 与 `cinemaInfo` 抓包用于确认同系统小程序的租户参数规律：接口主机和路径体系相同，变化字段是 `cinemaCode` 与微信小程序 `Referer`。它们不作为购票主流程的强制额外请求。

## 相对路径规则

- 默认配置文件路径相对于 CLI 脚本目录。
- `runtime.outputDir` 等配置中的相对路径以配置文件所在目录为基准解析。
- README、命令示例、默认图片目录和程序常量不包含 `E:\\filmproject`、`E:\\filmproject2` 等本机绝对路径。
- 测试使用临时目录，不依赖固定盘符或用户名。

## 错误处理与敏感信息

- 真实购买前校验 `baseUrl`、`cinemaCode`、`referer`、`openId`、会员卡密码、日期、时间和座位。
- `--check-only` 允许账号字段使用示例占位符，因为该模式不锁座、不付款；真实购买必须从本地配置读取有效的固定 `openId`。
- 日志和错误输出不显示完整 `openId`、会员卡密码、手机号或卡号。
- 网络错误注明失败步骤；锁座成功但付款失败时明确报告订单号和当前阶段，但不自动重复扣款。

## 测试与验收

- 配置解析测试覆盖默认配置、显式 `--config`、相对输出目录和占位符校验。
- 请求测试确认整条接口链路都使用配置中的 `cinemaCode` 和 `Referer`。
- CLI 测试确认默认执行真实流程，`--check-only` 不调用锁座或支付。
- 保留并迁移现有场次、座位、日期和会员支付测试。
- 删除 FastAPI 页面/API 测试。
- 测试全部使用模拟响应，不发送真实购票或扣款请求。

## 非目标

- 不自动抓取或刷新 `openId`；每次运行从本地配置读取固定值。
- 不提供网页配置界面。
- 不支持多个 profile；切换小程序时直接修改或替换单一配置文件。
- 不在自动测试中访问真实影院接口。
