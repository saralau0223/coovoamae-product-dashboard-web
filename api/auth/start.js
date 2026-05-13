const crypto = require('crypto');
const { cookie, getBaseUrl } = require('../_auth');

module.exports = async function handler(req, res) {
  const appId = process.env.FEISHU_APP_ID;
  if (!appId) {
    res.statusCode = 500;
    res.end('FEISHU_APP_ID is not configured');
    return;
  }
  const baseUrl = getBaseUrl(req);
  const redirectUri = `${baseUrl}/api/auth/callback`;
  const state = crypto.randomBytes(24).toString('base64url');
  res.setHeader('Set-Cookie', cookie('feishu_oauth_state', state, { maxAge: 600 }));
  const authHost = process.env.FEISHU_AUTH_HOST || 'https://open.feishu.cn';
  const url = new URL('/open-apis/authen/v1/index', authHost);
  url.searchParams.set('app_id', appId);
  url.searchParams.set('redirect_uri', redirectUri);
  url.searchParams.set('state', state);
  res.statusCode = 302;
  res.setHeader('Location', url.toString());
  res.end();
};
