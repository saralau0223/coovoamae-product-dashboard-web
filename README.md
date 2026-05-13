# COOVOAMAE 产品开发闭环网页版

固定网页入口，用于把飞书产品数据总看板变成更好看的阅读层和轻交互推进台。

## 当前定位

- 飞书共享表格仍是主数据源和协作底座。
- 网页只做：可视化阅读、允许询价、人工报价录入、本地复算、复制/导出给供应链和财神爷。
- 网页动作不会自动联系供应商、不会下单、不会修改 Amazon 后台。

## 飞书登录保护版本

本目录已加入 Vercel Serverless 版飞书登录保护：

- 未登录访问任意页面会跳转 `/api/auth/start`
- `/api/auth/start` 跳转飞书网页登录授权
- `/api/auth/callback` 用授权码换取用户信息
- 用户必须在 `FEISHU_ALLOWED_USERS` 白名单内，或显式设置 `FEISHU_ALLOW_ALL_USERS=true`
- 登录后由 `coovoamae_session` HttpOnly Cookie 保护页面
- 退出入口：`/api/auth/logout`

### 需要配置的环境变量

不要提交任何密钥到仓库，只在部署平台环境变量里配置：

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=***
FEISHU_ALLOWED_USERS=ou_xxx,xxx@example.com
AUTH_SESSION_SECRET=随机长字符串
PUBLIC_BASE_URL=https://你的部署域名
# 可选，默认如下
FEISHU_AUTH_HOST=https://open.feishu.cn
FEISHU_API_HOST=https://open.feishu.cn
```

### Feishu 开放平台需要配置

在飞书应用后台加入 OAuth 回调地址：

```text
https://你的部署域名/api/auth/callback
```

建议先只开最小权限：获取用户身份/基础信息，用于登录鉴权；不要给表格写权限、通讯录全量权限或后台操作权限。

## 本地开发

```bash
npm install
npx vercel dev
```

本地测试时也要配置同名环境变量，并把本地回调地址加入飞书应用后台。
