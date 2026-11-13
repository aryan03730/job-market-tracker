/**
 * Job Market Tracker email relay (Google Apps Script).
 *
 * Sends emails from your own Gmail over HTTPS, so the app works on hosts that
 * block SMTP ports. Free; a personal Gmail account can send about 100 emails a day.
 *
 * Setup: script.google.com > New project > paste this file > change TOKEN >
 * Deploy > New deployment > Web app > Execute as: Me, Who has access: Anyone.
 * Put the web app URL in EMAIL_RELAY_URL and the same TOKEN in EMAIL_RELAY_TOKEN.
 */
const TOKEN = 'CHANGE-ME-to-a-long-random-string';

function doPost(e) {
  let d;
  try {
    d = JSON.parse(e.postData.contents);
  } catch (err) {
    return reply({ ok: false, error: 'bad request' });
  }
  if (d.token !== TOKEN) return reply({ ok: false, error: 'bad token' });
  if (!d.to || !d.subject) return reply({ ok: false, error: 'missing to/subject' });
  try {
    GmailApp.sendEmail(d.to, d.subject, d.text || '', {
      htmlBody: d.html || undefined,
      name: 'Job Market Tracker',
    });
    return reply({ ok: true, remaining: MailApp.getRemainingDailyQuota() });
  } catch (err) {
    return reply({ ok: false, error: String(err) });
  }
}

function reply(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
