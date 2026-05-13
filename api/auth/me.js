const { verifySession, parseCookies } = require('../_auth');

module.exports = async function handler(req, res) {
  const user = verifySession(parseCookies(req).coovoamae_session);
  if (!user) {
    res.statusCode = 401;
    res.setHeader('Content-Type', 'application/json; charset=utf-8');
    res.end(JSON.stringify({ ok: false }));
    return;
  }
  res.statusCode = 200;
  res.setHeader('Content-Type', 'application/json; charset=utf-8');
  res.end(JSON.stringify({ ok: true, user: { name: user.name, email: user.email, open_id: user.open_id, user_id: user.user_id } }));
};
