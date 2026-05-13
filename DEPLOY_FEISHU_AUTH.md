# 飞书登录版上线步骤

> 不要把任何密钥写进 GitHub。所有密钥只放部署平台环境变量。

## 已完成

- 已新增分支：`feishu-auth-vercel`
- 已加入 Vercel Serverless 保护层
- 未登录访问网页会跳转飞书登录
- 白名单校验使用 `FEISHU_ALLOWED_USERS`
- Session 使用 HttpOnly Cookie

## 上线需要 2 个外部配置

### 1. 部署平台

推荐 Vercel，因为当前代码已按 Vercel Serverless 写好。

需要在 Vercel 导入 GitHub 仓库：

```text
saralau0223/coovoamae-product-dashboard-web
branch: feishu-auth-vercel
```

配置环境变量：

```bash
FEISHU_APP_ID=cli_xxx
FEISHU_APP_SECRET=***
FEISHU_ALLOWED_USERS=ou_xxx,xxx@example.com
AUTH_SESSION_SECRET=随机长字符串
PUBLIC_BASE_URL=https://部署出来的域名
FEISHU_AUTH_HOST=https://open.feishu.cn
FEISHU_API_HOST=https://open.feishu.cn
```

### 2. 飞书开放平台

在对应飞书应用后台添加 OAuth 回调地址：

```text
https://部署出来的域名/api/auth/callback
```

只需要最小权限：网页登录获取用户身份/基础信息。不要新增通讯录全量、表格写权限、广告后台、采购等权限。

## 上线后验收

1. 无 Cookie 打开页面，应跳转飞书登录。
2. 刘希账号登录后能进入看板。
3. 非白名单账号登录后应看到 403。
4. 页面源代码不能通过未登录直接拿到 `index.html` 内容。
5. 点击“允许询价”仍能生成询价任务行并本地保存。

## 公网页收口

飞书登录版验证通过后，应把当前 GitHub Pages 公网页关闭或改成“已迁移，请走飞书登录入口”，避免内部机会/成本/报价字段继续公网暴露。
