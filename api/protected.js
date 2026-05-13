const fs = require('fs');
const path = require('path');
const { verifySession, parseCookies } = require('./_auth');

module.exports = async function handler(req, res) {
  const user = verifySession(parseCookies(req).coovoamae_session);
  if (!user) {
    res.statusCode = 302;
    res.setHeader('Location', '/api/auth/start');
    res.end();
    return;
  }
  const htmlPath = path.join(process.cwd(), 'index.html');
  let html = fs.readFileSync(htmlPath, 'utf8');
  const safeName = String(user.name || user.email || 'Feishu User').replace(/[&<>"']/g, s => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
  html = html.replace('</body>', `<script>window.COOVOAMAE_AUTH_USER=${JSON.stringify({name: user.name || '', email: user.email || ''})};</script><div style="position:fixed;left:14px;bottom:14px;z-index:20;background:#1f1b16;color:#fff;border-radius:999px;padding:8px 12px;font:12px system-ui;box-shadow:0 10px 30px rgba(0,0,0,.18)">飞书已登录：${safeName} · <a href="/api/auth/logout" style="color:#ffe4b8">退出</a></div></body>`);
  res.statusCode = 200;
  res.setHeader('Content-Type', 'text/html; charset=utf-8');
  res.setHeader('Cache-Control', 'no-store');
  res.end(html);
};
