const { cookie, getBaseUrl } = require('../_auth');

module.exports = async function handler(req, res) {
  res.setHeader('Set-Cookie', cookie('coovoamae_session', '', { maxAge: 0 }));
  res.statusCode = 302;
  res.setHeader('Location', `${getBaseUrl(req)}/api/auth/start`);
  res.end();
};
