const crypto = require('crypto');

function base64url(input) {
  return Buffer.from(input).toString('base64url');
}

function unbase64url(input) {
  return Buffer.from(input, 'base64url').toString('utf8');
}

function sign(payload, secret) {
  return crypto.createHmac('sha256', secret).update(payload).digest('base64url');
}

function createSession(user) {
  const secret = process.env.AUTH_SESSION_SECRET;
  if (!secret) throw new Error('AUTH_SESSION_SECRET is not configured');
  const payload = base64url(JSON.stringify({
    open_id: user.open_id || '',
    union_id: user.union_id || '',
    user_id: user.user_id || '',
    name: user.name || user.en_name || user.email || 'Feishu User',
    email: user.email || '',
    avatar_url: user.avatar_url || '',
    iat: Math.floor(Date.now() / 1000),
    exp: Math.floor(Date.now() / 1000) + 60 * 60 * 24 * 7
  }));
  return `${payload}.${sign(payload, secret)}`;
}

function verifySession(cookieValue) {
  const secret = process.env.AUTH_SESSION_SECRET;
  if (!secret || !cookieValue || !cookieValue.includes('.')) return null;
  const [payload, sig] = cookieValue.split('.');
  const expected = sign(payload, secret);
  if (!crypto.timingSafeEqual(Buffer.from(sig), Buffer.from(expected))) return null;
  const data = JSON.parse(unbase64url(payload));
  if (!data.exp || data.exp < Math.floor(Date.now() / 1000)) return null;
  return data;
}

function parseCookies(req) {
  return Object.fromEntries(String(req.headers.cookie || '').split(';').filter(Boolean).map(part => {
    const idx = part.indexOf('=');
    return [decodeURIComponent(part.slice(0, idx).trim()), decodeURIComponent(part.slice(idx + 1).trim())];
  }));
}

function cookie(name, value, options = {}) {
  const attrs = [`${name}=${encodeURIComponent(value)}`];
  attrs.push('Path=/');
  attrs.push('HttpOnly');
  attrs.push('Secure');
  attrs.push('SameSite=Lax');
  if (options.maxAge !== undefined) attrs.push(`Max-Age=${options.maxAge}`);
  return attrs.join('; ');
}

function allowedUser(user) {
  if (String(process.env.FEISHU_ALLOW_ALL_USERS || '').toLowerCase() === 'true') return true;
  const allow = String(process.env.FEISHU_ALLOWED_USERS || '')
    .split(/[\s,;]+/).map(s => s.trim()).filter(Boolean);
  if (!allow.length) return false;
  const ids = [user.open_id, user.user_id, user.union_id, user.email].filter(Boolean);
  return ids.some(id => allow.includes(id));
}

function getBaseUrl(req) {
  if (process.env.PUBLIC_BASE_URL) return process.env.PUBLIC_BASE_URL.replace(/\/$/, '');
  const proto = req.headers['x-forwarded-proto'] || 'https';
  const host = req.headers['x-forwarded-host'] || req.headers.host;
  return `${proto}://${host}`;
}

module.exports = { createSession, verifySession, parseCookies, cookie, allowedUser, getBaseUrl };
