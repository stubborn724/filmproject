# 配置化电影票自动购买工具

这是一个纯 Python CLI 工具，不需要启动后端服务或打开网页。订单、小程序和会员账号参数统一放在 `config.local.json` 中。

默认运行会真实锁座并使用会员卡付款。首次使用或修改配置后，请先执行 `--check-only`。

## 配置

项目提供两个配置文件：

- `config.example.json`：可提交的脱敏示例，包含完整订单填写范例。
- `config.local.json`：本地实际配置，程序默认读取，已被 Git 忽略。

主要配置项：

```json
{
  "miniProgram": {
    "baseUrl": "https://pandl.xyz",
    "cinemaCode": "34025901",
    "referer": "https://servicewechat.com/wx52420337e5796bd6/15/page-frame.html",
    "distributorId": ""
  },
  "account": {
    "openId": "填写固定 openId",
    "memberCardPassword": "填写会员卡密码"
  },
  "order": {
    "movieName": "给阿嬷的情书",
    "showDate": "2026-06-19",
    "startTime": "19:20",
    "hallName": "6号LMAX巨幕厅",
    "filmLanguage": "普通话",
    "showType": "2D",
    "seatNames": ["5排9号"],
    "priceMax": 80
  },
  "runtime": {
    "timeout": 20,
    "outputDir": "picture"
  }
}
```

切换同系统的其他小程序时，通常需要修改 `baseUrl`、`cinemaCode`、`referer`、`openId` 和会员卡密码。所有接口请求都会统一使用这里配置的影院编码和小程序 Referer。

`hallName`、`filmLanguage`、`showType` 可以留空；留空时不参与场次筛选。票数根据 `seatNames` 自动计算。

配置中的 `outputDir` 相对于配置文件所在目录解析，不需要填写本机绝对路径。

## 安装

```powershell
python -m pip install -r requirements.txt
```

当前版本只使用 Python 标准库，保留安装命令是为了后续依赖变化时使用方式不变。

## 安全检查

只查询场次和指定座位，不锁座、不付款：

```powershell
python .\movie_ticket_cli.py --check-only
```

## 自动购买

以下命令会真实锁座并使用会员卡付款：

```powershell
python .\movie_ticket_cli.py
```

使用其他配置文件：

```powershell
python .\movie_ticket_cli.py --config .\config.example.json --check-only
```

支付并出票成功后，取票信息会保存到配置的 `outputDir`。

## 测试

测试全部使用模拟响应，不会访问真实购票或付款接口：

```powershell
python -m unittest discover -v
```
