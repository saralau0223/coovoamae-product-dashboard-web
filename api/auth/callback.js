const { createSession, parseCookies, cookie, allowedUser, getBaseUrl } = require('../_auth');

async function fetchJson(url, options) {
  const r = await fetch(url, options);
  const text = await r.text();
  let data;
  try { data = JSON.parse(text); } catch (_) { data = { raw: text }; }
  if (!r.ok || (data.code !== undefined && data.code !== 0)) {
    const msg = data.msg || data.message || text || `HTTP ${r.status}`;
    throw new Error(msg);
  }
  return data;
}

module.exports = async function handler(req, res) {
  try {
    const { code, state } = req.query || {};
    const cookies = parseCookies(req);
    if (!code || !state || !cookies.feishu_oauth_state || state !== cookies.feishu_oauth_state) {
      res.statusCode = 400;
      res.end('Invalid Feishu login state');
      return;
    }

    const appId = process.env.FEISHU_APP_ID;
    const appSecret = process.env.FEISHU_APP_SECRET;
    if (!appId || !appSecret) throw new Error('FEISHU_APP_ID / FEISHU_APP_SECRET is not configured');

    const apiHost = process.env.FEISHU_API_HOST || 'https://open.feishu.cn';
    const appTokenResp = await fetchJson(`${apiHost}/open-apis/auth/v3/app_access_token/internal`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
      body: JSON.stringify({ app_id: appId, app_secret: appSecret })
    });
    const appAccessToken = appTokenResp.app_access_token;
    if (!appAccessToken) throw new Error('No app_access_token returned from Feishu');

    const userTokenResp = await fetchJson(`${apiHost}/open-apis/authen/v1/access_token`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json; charset=utf-8',
        'Authorization': `Bearer ${appAccessToken}`
      },
      body: JSON.stringify({ grant_type: 'authorization_code', code })
    });
    const userAccessToken = userTokenResp.data && userTokenResp.data.access_token;
    if (!userAccessToken) throw new Error('No user access_token returned from Feishu');

    const userInfoResp = await fetchJson(`${apiHost}/open-apis/authen/v1/user_info`, {
      headers: { 'Authorization': `Bearer ${userAccessToken}` }
    });
    const user = userInfoResp.data || {};
    if (!allowedUser(user)) {
      res.statusCode = 403;
      res.end('账号已通过飞书登录，但不在看板允许名单内。请联系刘希/总管家加入白名单。');
      return;
    }

    res.setHeader('Set-Cookie', [
      cookie('coovoamae_session', createSession(user), { maxAge: 60 * 60 * 24 * 7 }),
      cookie('feishu_oauth_state', '', { maxAge: 0 })
    ]);
    res.statusCode = 302;
    res.setHeader('Location', `${getBaseUrl(req)}/`);
    res.end();
  } catch (err) {
    res.statusCode = 500;
    res.end(`Feishu login failed: ${err.message}`);
  }
};
