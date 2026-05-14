<div align="center">
  <h1>✨ | MXUserbot | ✨</h1>
  <img width="1376" height="768" alt="result" src="assets/banner.webp"/>
  <br>
</div>

<br>

<p>
  <b>What is a userbot:</b> A bot that runs directly on your account, acting on your behalf.<br>
  <b>Purpose:</b> From showing off to your friends that you use bot commands from your account to automation and useful modules. It all depends on you!
</p>

<h3><b>Matrix Space</b></h3>
<p>We have Matrix space: <a href="https://matrix.to/#/#SpacePashaHatsune:matrix.org">#SpacePashaHatsune:matrix.org</a></p>

<hr>

<h2>✨ | Feature</h2>

<table cellspacing="0" width="100%">
 <tr>
  <td width="50%" style="border:1px solid #30363d;padding:0;vertical-align:top">
    <img src="assets/promo/EMOJICALLBACK.gif" width="100%" style="display:block">
    <div align="center" style="padding:12px;border-top:1px solid #30363d"><sub><b>Emoji Callbacks</b> - Reactions as buttons.</sub></div>
  </td>
  <td width="50%" style="border:1px solid #30363d;padding:0;vertical-align:top">
    <img src="assets/promo/FSM.gif" width="100%" style="display:block">
    <div align="center" style="padding:12px;border-top:1px solid #30363d"><sub><b>FSM</b> - Multi-step dialogs with state persistence.</sub></div>
  </td>
 </tr>
</table>

<table cellspacing="0" width="100%">
 <tr>
  <td width="50%" style="border:1px solid #30363d;padding:0;vertical-align:top">
    <img src="assets/promo/SITE.gif" width="100%" style="display:block">
    <div align="center" style="padding:12px;border-top:1px solid #30363d"><sub><b>Web Panel</b> - Manage modules/account via web panel</sub></div>
  </td>
  <td width="50%" style="border:1px solid #30363d;padding:0;vertical-align:top">
    <img src="assets/promo/SUDO.gif" width="100%" style="display:block">
    <div align="center" style="padding:12px;border-top:1px solid #30363d"><sub><b>SUDO LIST</b> - Grant your friend permission to execute commands </sub></div>
  </td>
 </tr>
</table>

<table cellspacing="0" width="100%">
 <tr>
  <td width="50%" style="border:1px solid #30363d;padding:0;vertical-align:top">
    <img src="assets/promo/VERIF.gif" width="100%" style="display:block">
    <div align="center" style="padding:12px;border-top:1px solid #30363d"><sub><b>SAS Verification</b> - Verify your device anywhere!.</sub></div>
  </td>
  <td width="50%" style="border:1px solid #30363d;padding:0;vertical-align:top">
    <img src="assets/promo/REPOS.gif" width="100%" style="display:block">
    <div align="center" style="padding:12px;border-top:1px solid #30363d"><sub><b>Module Repository</b> — add custom repositories!</sub></div>
  </td>
 </tr>
</table>

<br>

<table cellspacing="0" width="100%">
 <tr>
  <td width="100%" style="border:1px solid #30363d;padding:0;vertical-align:top">
    <img src="assets/promo/RATE_LIMITER.png" width="100%" style="display:block">
    <div align="center" style="padding:12px;border-top:1px solid #30363d">
      <sub><b>Rate Limiter</b> - AIMD-based protection against "Too Many Requests" allows you to run your userbot on any server!.</sub>
    </div>
   </td>
 </tr>
</table>

<br>

<table cellspacing="0" cellpadding="0" style="border-collapse: collapse; width: 100%;">
  <tr>
    <td width="50%" style="padding: 0 10px 0 0; vertical-align: top; border: none;">
      <img src="assets/promo/SSO_LOGIN.gif" width="100%" style="display:block;">
      <div align="center">
        <sub>Login via SSO</sub>
      </div>
    </td>
    <td width="50%" style="padding: 0; vertical-align: top; border: none;">
      <img src="assets/promo/LOGIN.gif" width="100%" style="display:block;"> 
      <div align="center">
        <sub>Login via @user:server</sub>
      </div>
    </td>
  </tr>
</table>

<h2>Installation</h2>

<h4>Docker</h4>
<pre lang="sh"><code>git clone https://github.com/PashaHatsune/MxUserbot.git
cd MxUserbot
docker-compose up --build</code></pre>

<h4>Manual Installation on <a href="https://docs.astral.sh/uv/#highlights">uv</a></h4>
<pre lang="sh"><code>git clone https://github.com/PashaHatsune/MxUserbot.git
cd MxUserbot
uv sync
uv run -m src.mxuserbot</code></pre>

<hr>

<h2>Systemd (User Service)</h2>
<p>To run the userbot in the background as a system daemon</p>
<pre lang="sh"><code>mkdir -p ~/.config/systemd/user/
cp mxuserbot.service ~/.config/systemd/user/
# Edit WorkingDirectory in the service file if needed
systemctl --user daemon-reload
systemctl --user enable --now mxuserbot.service</code></pre>

<hr>

<h3>Documentation</h3>
<p><a href="https://mxuserbot.github.io/documentation/">https://mxuserbot.github.io/documentation/</a></p>
<hr>
<h3>Donate</h3>
<p><a href="https://destream.net/live/Pashahatsune/donate">https://destream.net/live/Pashahatsune/donate</a></p>

<hr>

<h3>Contribution</h3>
<p>
  We accept <b>Issues</b> and <b>Pull requests</b>.<br>
  If you have ideas or code — send them over, I will review everything.
</p>

<hr>

<h2>Disclaimer</h2>
<p align="justify">
  This software is provided <b>"as is"</b>, without warranty of any kind, express or implied. By using this userbot, you acknowledge that:
</p>
<ul>
  <li><b>Full Responsibility:</b> You are solely responsible for your actions and any consequences resulting from the use of this software.</li>
  <li><b>No Liability:</b> The developer shall not be held liable for any damages, including but not limited to account bans, data loss, or legal issues.</li>
  <li><b>Strict Prohibition:</b> Use of this bot for fraudulent activities, spam, or any actions that violate terms of service or local laws is strictly prohibited.</li>
</ul>

<hr>

<h3>Credits</h3>
<ul>
  <li><b>@ArThirtyFour</b> — thanks for help with the code/banner.</li>
  <li><b>@maseckt</b> — thanks for help with the code/videos.</li>
</ul>

<hr>

<div align="center">
    <img width="10%" src="assets/promo/miku.gif">
</div>
