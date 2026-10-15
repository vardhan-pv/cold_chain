#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include <Preferences.h>
#include <vector>
#include <algorithm>
#include "telemetry_net.h"
#include "config.h"
#include "cooling.h"
#include <WiFiClientSecure.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <time.h>
#include <atomic>
#if __has_include("secrets.h")
#include "secrets.h"
#else
#include "secrets.example.h"
#endif

// ==========================================
// Setup Portal Web Assets
// ==========================================
static const char SETUP_HTML[] PROGMEM = R"rawliteral(<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Cold Chain Setup</title>
  <style>
    :root {
      --bg: #0b0f19;
      --card: rgba(30, 41, 59, 0.75);
      --border: rgba(255, 255, 255, 0.12);
      --accent: #38bdf8;
      --accent-btn: linear-gradient(135deg, #0284c7 0%, #2563eb 100%);
      --text: #f8fafc;
      --text-muted: #94a3b8;
    }
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(135deg, #0b0f19 0%, #111827 50%, #1e293b 100%);
      color: var(--text);
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px;
    }
    .card {
      width: 100%;
      max-width: 420px;
      background: var(--card);
      backdrop-filter: blur(16px);
      -webkit-backdrop-filter: blur(16px);
      border: 1px solid var(--border);
      border-radius: 20px;
      padding: 28px 24px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5), 0 0 30px rgba(56, 189, 248, 0.15);
    }
    .badge {
      display: inline-block;
      padding: 4px 12px;
      border-radius: 9999px;
      background: rgba(56, 189, 248, 0.15);
      border: 1px solid rgba(56, 189, 248, 0.3);
      color: var(--accent);
      font-size: 11px;
      font-weight: 700;
      letter-spacing: 1.5px;
      text-transform: uppercase;
      margin-bottom: 12px;
    }
    .header { text-align: center; margin-bottom: 20px; }
    h1 { font-size: 22px; font-weight: 700; margin-bottom: 6px; }
    .sub { font-size: 13px; color: var(--text-muted); }
    .meta {
      display: flex;
      justify-content: space-between;
      background: rgba(15, 23, 42, 0.6);
      border-radius: 10px;
      padding: 8px 14px;
      margin-bottom: 20px;
      font-size: 12px;
      color: var(--text-muted);
      border: 1px solid rgba(255, 255, 255, 0.05);
    }
    .meta b { color: #e2e8f0; }
    .form-group { margin-bottom: 18px; }
    label { display: block; font-size: 13px; font-weight: 600; color: #cbd5e1; margin-bottom: 8px; }
    select, input[type="text"], input[type="password"] {
      width: 100%;
      padding: 12px 14px;
      background: rgba(15, 23, 42, 0.7);
      border: 1px solid rgba(148, 163, 184, 0.25);
      border-radius: 10px;
      color: #fff;
      font-size: 14px;
      outline: none;
      transition: all 0.2s;
    }
    select:focus, input:focus {
      border-color: var(--accent);
      box-shadow: 0 0 0 3px rgba(56, 189, 248, 0.2);
    }
    select { margin-bottom: 10px; cursor: pointer; }
    option { background: #1e293b; color: #fff; }
    .pass-wrap { position: relative; }
    .btn-toggle {
      position: absolute;
      right: 10px;
      top: 50%;
      transform: translateY(-50%);
      background: transparent;
      border: none;
      color: var(--accent);
      font-size: 12px;
      font-weight: 600;
      cursor: pointer;
      padding: 4px 8px;
    }
    .btn-submit {
      width: 100%;
      padding: 14px;
      background: var(--accent-btn);
      border: none;
      border-radius: 12px;
      color: #fff;
      font-size: 15px;
      font-weight: 700;
      letter-spacing: 0.5px;
      cursor: pointer;
      box-shadow: 0 4px 15px rgba(37, 99, 235, 0.4);
      transition: all 0.2s;
      margin-top: 6px;
    }
    .btn-submit:hover {
      box-shadow: 0 6px 20px rgba(37, 99, 235, 0.6);
      transform: translateY(-1px);
    }
    .btn-submit:active { transform: translateY(1px); }
    .links { text-align: center; margin-top: 16px; }
    .links a { color: var(--accent); text-decoration: none; font-size: 13px; }
    .links a:hover { text-decoration: underline; }
    .footer { text-align: center; margin-top: 20px; font-size: 11px; color: #64748b; }
  </style>
</head>
<body>
  <div class="card">
    <div class="header">
      <div class="badge">Cold Chain System</div>
      <h1>Wi-Fi Setup</h1>
      <p class="sub">Configure wireless connection for IoT Unit</p>
    </div>
    <div class="meta">
      <span>Device: <b>CCU-HW-001</b></span>
      <span>Setup IP: <b>192.168.4.1</b></span>
    </div>
    <form action="/save" method="POST">
      <div class="form-group">
        <label for="ssid">Select Network</label>
        <select id="ssid_select" onchange="pickNet(this.value)">
          <option value="">-- Choose nearby network --</option>
          {{NETWORKS}}
          <option value="__manual__">-- Other (Enter manually) --</option>
        </select>
        <input type="text" id="ssid" name="ssid" placeholder="Or enter Wi-Fi SSID" required autocomplete="off">
      </div>
      <div class="form-group">
        <label for="password">Wi-Fi Password</label>
        <div class="pass-wrap">
          <input type="password" id="password" name="password" placeholder="Enter password (if secured)" autocomplete="off">
          <button type="button" class="btn-toggle" onclick="togglePass()">Show</button>
        </div>
      </div>
      <button type="submit" class="btn-submit">SAVE &amp; CONNECT</button>
    </form>
    <div class="links">
      <a href="/">&#x21bb; Rescan Networks</a>
    </div>
    <div class="footer">
      Cold Chain Remote Monitor &bull; Cloud Backend Ready
    </div>
  </div>
  <script>
    function pickNet(val) {
      var inp = document.getElementById('ssid');
      if (val === '__manual__') {
        inp.value = '';
        inp.focus();
      } else if (val) {
        inp.value = val;
      }
    }
    function togglePass() {
      var p = document.getElementById('password');
      var b = event.target;
      if (p.type === 'password') {
        p.type = 'text';
        b.innerText = 'Hide';
      } else {
        p.type = 'password';
        b.innerText = 'Show';
      }
    }
  </script>
</body>
</html>
)rawliteral";

static const char SUCCESS_HTML[] PROGMEM = R"rawliteral(<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Credentials Saved</title>
  <style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
      background: linear-gradient(135deg, #0b0f19 0%, #111827 50%, #1e293b 100%);
      color: #fff;
      min-height: 100vh;
      display: flex;
      align-items: center;
      justify-content: center;
      padding: 16px;
      text-align: center;
    }
    .card {
      width: 100%;
      max-width: 420px;
      background: rgba(30, 41, 59, 0.75);
      backdrop-filter: blur(16px);
      border: 1px solid rgba(255, 255, 255, 0.12);
      border-radius: 20px;
      padding: 36px 24px;
      box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5);
    }
    .icon {
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: rgba(16, 185, 129, 0.2);
      border: 2px solid #10b981;
      color: #10b981;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 28px;
      margin: 0 auto 18px;
    }
    h2 { font-size: 22px; margin-bottom: 8px; }
    p { color: #94a3b8; font-size: 14px; line-height: 1.6; }
    .ssid { color: #38bdf8; font-weight: 700; }
    .spinner {
      width: 32px;
      height: 32px;
      border: 3px solid rgba(255, 255, 255, 0.15);
      border-top-color: #38bdf8;
      border-radius: 50%;
      animation: spin 1s infinite linear;
      margin: 22px auto;
    }
    @keyframes spin { 0% { transform: rotate(0deg); } 100% { transform: rotate(360deg); } }
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">&#10004;</div>
    <h2>Credentials Saved</h2>
    <p>Connecting to <span class="ssid">{{SSID}}</span>...</p>
    <div class="spinner"></div>
    <p>ESP32 is restarting now.<br>You may now disconnect from <b>ColdChain-Setup</b>.</p>
  </div>
</body>
</html>
)rawliteral";

// ==========================================
// Module State & Structures
// ==========================================
struct Packet { char json[2048]; };
static QueueHandle_t queue = nullptr;
static std::atomic<uint32_t> lastSuccess{0}, dropped{0}, sequence{0}, riskAt{0};
static std::atomic<float> advisoryRisk{NAN};
static char bootID[33];
static std::atomic<bool> clockSynchronized{false};

static std::atomic<WifiState> currentWifiState{WifiState::CONNECTING};
static String activeSSID = "";
static String activePassword = "";
static std::atomic<uint32_t> popupUntil{0};
static WebServer* apServer = nullptr;
static DNSServer* apDnsServer = nullptr;
static bool shouldRestart = false;
static uint32_t restartAt = 0;

// ==========================================
// Wi-Fi State & NVS Management
// ==========================================
WifiState networkWifiState() {
  return currentWifiState.load();
}

const char* networkCurrentSsid() {
  if (currentWifiState.load() == WifiState::SETUP_AP) return "ColdChain-Setup";
  if (activeSSID.length() > 0) return activeSSID.c_str();
  return "None";
}

static String loadSavedSSID() {
  Preferences p;
  p.begin("coldchain", true);
  String s = p.getString("wifi_ssid", "");
  p.end();
  s.trim();
  return s;
}

static String loadSavedPassword() {
  Preferences p;
  p.begin("coldchain", true);
  String pass = p.getString("wifi_password", "");
  p.end();
  return pass;
}

static void saveWifiCredentials(const String& ssid, const String& pass) {
  Preferences p;
  p.begin("coldchain", false);
  p.putString("wifi_ssid", ssid);
  p.putString("wifi_password", pass);
  p.end();
}

void wifiResetCredentials() {
  Preferences p;
  p.begin("coldchain", false);
  p.remove("wifi_ssid");
  p.remove("wifi_password");
  p.end();
  Serial.println("[WiFi] Wi-Fi credentials cleared.");
  Serial.println("[WiFi] Restarting into ColdChain-Setup mode...");
  delay(500);
  ESP.restart();
}

void wifiPrintStatus() {
  WifiState st = currentWifiState.load();
  const char* statusStr = "DISCONNECTED";
  String ssid = activeSSID;
  String ip = "0.0.0.0";

  if (st == WifiState::SETUP_AP) {
    statusStr = "AP_MODE";
    ssid = "ColdChain-Setup";
    ip = WiFi.softAPIP().toString();
  } else if (WiFi.status() == WL_CONNECTED) {
    statusStr = "CONNECTED";
    if (ssid.isEmpty()) ssid = WiFi.SSID();
    ip = WiFi.localIP().toString();
  } else if (st == WifiState::CONNECTING) {
    statusStr = "CONNECTING";
  }

  String backend = BACKEND_URL;
  int apiIdx = backend.indexOf("/api/");
  if (apiIdx >= 0) backend = backend.substring(0, apiIdx);

  Serial.printf("WiFi: %s\n", statusStr);
  Serial.printf("SSID: %s\n", ssid.isEmpty() ? "None" : ssid.c_str());
  Serial.printf("IP: %s\n", ip.c_str());
  Serial.printf("Backend: %s\n", backend.c_str());
}

// ==========================================
// Wi-Fi Scanning & Setup AP Portal
// ==========================================
static String getScannedNetworkOptions() {
  int n = WiFi.scanNetworks(false, false);
  String opts = "";
  if (n > 0) {
    std::vector<std::pair<String, int>> scanList;
    for (int i = 0; i < n; ++i) {
      String s = WiFi.SSID(i);
      s.trim();
      if (s.isEmpty()) continue;
      int rssi = WiFi.RSSI(i);
      bool exists = false;
      for (auto& item : scanList) {
        if (item.first == s) {
          if (rssi > item.second) item.second = rssi;
          exists = true;
          break;
        }
      }
      if (!exists) scanList.push_back({s, rssi});
    }

    std::sort(scanList.begin(), scanList.end(), [](const std::pair<String, int>& a, const std::pair<String, int>& b) {
      return a.second > b.second;
    });

    for (const auto& item : scanList) {
      int quality = 0;
      if (item.second <= -100) quality = 0;
      else if (item.second >= -50) quality = 100;
      else quality = 2 * (item.second + 100);
      opts += "<option value=\"" + item.first + "\">" + item.first + " (" + String(quality) + "% / " + String(item.second) + " dBm)</option>\n";
    }
  } else {
    opts += "<option value=\"\" disabled>No networks discovered nearby</option>\n";
  }
  WiFi.scanDelete();
  return opts;
}

static void startSetupAP() {
  currentWifiState = WifiState::SETUP_AP;
  WiFi.disconnect(true, true);
  vTaskDelay(pdMS_TO_TICKS(100));

  WiFi.mode(WIFI_AP_STA);
  WiFi.softAP("ColdChain-Setup");
  IPAddress apIP = WiFi.softAPIP();

  Serial.println("[AP] Access Point started: ColdChain-Setup");
  Serial.printf("[AP] Local IP address: %s\n", apIP.toString().c_str());
  Serial.println("[AP] Connect phone/laptop and open http://192.168.4.1");

  if (!apDnsServer) {
    apDnsServer = new DNSServer();
  }
  apDnsServer->start(53, "*", apIP);

  if (!apServer) {
    apServer = new WebServer(80);

    auto sendSetupPage = []() {
      String html = FPSTR(SETUP_HTML);
      html.replace("{{NETWORKS}}", getScannedNetworkOptions());
      apServer->send(200, "text/html", html);
    };

    apServer->on("/", HTTP_GET, sendSetupPage);
    apServer->on("/generate_204", HTTP_GET, sendSetupPage);
    apServer->on("/gen_204", HTTP_GET, sendSetupPage);
    apServer->on("/hotspot-detect.html", HTTP_GET, sendSetupPage);
    apServer->on("/canonical.html", HTTP_GET, sendSetupPage);
    apServer->on("/connecttest.txt", HTTP_GET, sendSetupPage);
    apServer->on("/ncsi.txt", HTTP_GET, sendSetupPage);
    apServer->on("/redirect", HTTP_GET, sendSetupPage);

    apServer->on("/save", HTTP_POST, []() {
      String ssid = apServer->arg("ssid");
      String pass = apServer->arg("password");
      ssid.trim();
      pass.trim();

      if (ssid.isEmpty()) {
        apServer->send(400, "text/plain", "Error: SSID cannot be empty.");
        return;
      }

      saveWifiCredentials(ssid, pass);
      Serial.printf("[WiFi] New credentials saved for SSID: %s\n", ssid.c_str());
      Serial.println("[WiFi] Restarting ESP32...");

      String html = FPSTR(SUCCESS_HTML);
      html.replace("{{SSID}}", ssid);
      apServer->send(200, "text/html", html);

      shouldRestart = true;
      restartAt = millis() + 1500;
    });

    apServer->onNotFound([]() {
      apServer->sendHeader("Location", "http://192.168.4.1/", true);
      apServer->send(302, "text/plain", "");
    });

    apServer->begin();
  }
}

// ==========================================
// Cloud Backend & NTP Helpers
// ==========================================
static bool beginRequest(HTTPClient& http, WiFiClient& plain, WiFiClientSecure& secure, const String& url) {
  bool ready = false;
  if (url.startsWith("https://")) {
    if (strlen(ROOT_CA) > 0) secure.setCACert(ROOT_CA);
    else secure.setInsecure();
    ready = http.begin(secure, url);
  } else if (ALLOW_LAB_HTTP && url.startsWith("http://")) {
    ready = http.begin(plain, url);
  }
  if (ready) {
    http.setConnectTimeout(1500);
    http.setTimeout(1500);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("X-Device-Token", DEVICE_TOKEN);
  }
  return ready && strlen(DEVICE_TOKEN) > 0;
}

static void acknowledgeLocalDecision() {
  String root = BACKEND_URL;
  int api = root.indexOf("/api/");
  if (api < 0) return;
  root = root.substring(0, api);

  HTTPClient http;
  WiFiClient plain;
  WiFiClientSecure secure;
  String pending = root + "/api/v1/control/" + DEVICE_ID + "/pending";
  if (!beginRequest(http, plain, secure, pending)) { http.end(); return; }
  int code = http.GET();
  String response = (code == 200) ? http.getString() : String();
  http.end();
  if (code != 200) return;

  JsonDocument result;
  if (deserializeJson(result, response) || !result["command_available"].as<bool>()) return;
  JsonObject command = result["command"].as<JsonObject>();
  int id = command["id"] | 0;
  const char* boot = command["boot_id"] | "";
  if (id <= 0 || strcmp(boot, bootID) != 0) return;

  bool primary = primaryObserved(), backup = backupObserved();
  bool matches = command["based_on_sequence"].as<uint32_t>() <= sequence &&
                 command["primary_cooling"].as<bool>() == primary &&
                 command["backup_cooling"].as<bool>() == backup;

  JsonDocument ack;
  ack["device_id"] = DEVICE_ID;
  ack["boot_id"] = bootID;
  ack["sequence"] = (uint32_t)sequence.load();
  ack["outcome"] = matches ? "APPLIED" : "REJECTED";
  ack["primary_cooling"] = primary;
  ack["backup_cooling"] = backup;
  ack["reason"] = matches ? "Local safety loop agrees; GPIO command state reported"
                          : "Local safety loop disagrees; remote override inhibited";
  String body;
  serializeJson(ack, body);

  String target = root + "/api/v1/control/" + String(id) + "/acknowledge";
  if (beginRequest(http, plain, secure, target)) {
    int status = http.POST(body);
    Serial.printf("{\"event\":\"command_ack\",\"id\":%d,\"http\":%d,\"local_match\":%s}\n", id, status, matches ? "true" : "false");
  }
  http.end();
}

static void syncNTP() {
  Serial.println("[BOOT] NTP starting...");
  configTime(0, 0, "pool.ntp.org", "time.google.com", "time.cloudflare.com");
  for (int attempt = 1; attempt <= 30; attempt++) {
    time_t now = time(nullptr);
    if (now > 1700000000) {
      clockSynchronized = true;
      Serial.println("[BOOT] NTP OK");
      return;
    }
    vTaskDelay(pdMS_TO_TICKS(1000));
  }
  Serial.println("[BOOT] NTP timeout");
}

// ==========================================
// Network Background Worker Task
// ==========================================
static void worker(void*) {
  String savedSSID = loadSavedSSID();
  String savedPass = loadSavedPassword();
  activePassword = savedPass;

  if (savedSSID.isEmpty()) {
    Serial.println("[BOOT] No saved Wi-Fi credentials found.");
    Serial.println("[BOOT] Entering ColdChain-Setup Access Point mode...");
    startSetupAP();
  } else {
    activeSSID = savedSSID;
    currentWifiState = WifiState::CONNECTING;
    Serial.printf("[BOOT] Saved Wi-Fi found. Connecting to SSID: %s\n", savedSSID.c_str());
    WiFi.mode(WIFI_STA);
    WiFi.setAutoReconnect(true);
    WiFi.persistent(false);
    WiFi.begin(savedSSID.c_str(), savedPass.c_str());

    uint32_t connectStartedAt = millis();
    bool connected = false;

    while (millis() - connectStartedAt < 20000) {
      if (WiFi.status() == WL_CONNECTED) {
        connected = true;
        break;
      }
      vTaskDelay(pdMS_TO_TICKS(500));
    }

    if (!connected) {
      Serial.println("[BOOT] Wi-Fi connection failed or timed out after 20s.");
      Serial.println("[BOOT] Entering ColdChain-Setup Access Point mode...");
      WiFi.disconnect(true, false);
      vTaskDelay(pdMS_TO_TICKS(200));
      startSetupAP();
    } else {
      Serial.println("[BOOT] Wi-Fi connected successfully!");
      Serial.printf("[BOOT] IP: %s\n", WiFi.localIP().toString().c_str());
      Serial.printf("[BOOT] RSSI: %d dBm\n", WiFi.RSSI());
      currentWifiState = WifiState::CONNECTED_POPUP;
      popupUntil = millis() + 2000;
      syncNTP();
    }
  }

  uint32_t lastNtpRetry = millis();
  uint32_t retryMs = 1000;
  uint32_t staReconnectAttempt = millis();
  bool wasConnected = (WiFi.status() == WL_CONNECTED);
  static Packet packet;
  bool holding = false;

  for (;;) {
    // 1. AP Setup Mode
    if (currentWifiState.load() == WifiState::SETUP_AP) {
      if (apDnsServer) apDnsServer->processNextRequest();
      if (apServer) apServer->handleClient();
      if (shouldRestart && millis() >= restartAt) {
        Serial.println("[WiFi] Restarting now...");
        vTaskDelay(pdMS_TO_TICKS(100));
        ESP.restart();
      }
      vTaskDelay(pdMS_TO_TICKS(5));
      continue;
    }

    // 2. Station Mode
    wl_status_t status = WiFi.status();

    if (status != WL_CONNECTED) {
      wasConnected = false;
      currentWifiState = WifiState::DISCONNECTED;
      uint32_t now = millis();

      if (now - staReconnectAttempt >= 15000) {
        Serial.println("[WiFi] Reconnecting in background...");
        WiFi.disconnect(false, false);
        vTaskDelay(pdMS_TO_TICKS(100));
        WiFi.begin(activeSSID.c_str(), activePassword.c_str());
        staReconnectAttempt = now;
      }

      vTaskDelay(pdMS_TO_TICKS(500));
      continue;
    }

    if (!wasConnected) {
      wasConnected = true;
      staReconnectAttempt = millis();
      Serial.println("[WiFi] connected");
      Serial.printf("[WiFi] IP: %s\n", WiFi.localIP().toString().c_str());
      Serial.printf("[WiFi] RSSI: %d dBm\n", WiFi.RSSI());
      if (currentWifiState.load() != WifiState::CONNECTED_POPUP) {
        currentWifiState = WifiState::CONNECTED_NORMAL;
      }
      syncNTP();
      lastNtpRetry = millis();
    } else if (currentWifiState.load() == WifiState::CONNECTED_POPUP && millis() >= popupUntil) {
      currentWifiState = WifiState::CONNECTED_NORMAL;
    } else if (!clockSynchronized && (millis() - lastNtpRetry >= 30000)) {
      lastNtpRetry = millis();
      syncNTP();
    }

    if (!clockSynchronized) {
      vTaskDelay(pdMS_TO_TICKS(500));
      continue;
    }

    if (!holding) holding = (xQueueReceive(queue, &packet, pdMS_TO_TICKS(100)) == pdTRUE);
    if (!holding) continue;

    HTTPClient http;
    WiFiClient plain;
    WiFiClientSecure secure;
    bool configured = false;
    if (strncmp(BACKEND_URL, "https://", 8) == 0) {
      if (strlen(ROOT_CA) > 0) secure.setCACert(ROOT_CA);
      else secure.setInsecure();
      configured = http.begin(secure, BACKEND_URL);
    } else if (ALLOW_LAB_HTTP && strncmp(BACKEND_URL, "http://", 7) == 0) {
      configured = http.begin(plain, BACKEND_URL);
    }

    int status_code = -1;
    if (configured && strlen(DEVICE_TOKEN)) {
      http.setConnectTimeout(2500);
      http.setTimeout(2500);
      http.addHeader("Content-Type", "application/json");
      http.addHeader("X-Device-Token", DEVICE_TOKEN);
      Serial.printf("Sending telemetry to %s...\n", BACKEND_URL);
      status_code = http.POST(reinterpret_cast<uint8_t*>(packet.json), strlen(packet.json));
      Serial.printf("HTTP Response Code: %d\n", status_code);
      if (status_code >= 200 && status_code < 300) {
        JsonDocument response;
        if (!deserializeJson(response, http.getString()) && !response["archived"].as<bool>() &&
            !response["prediction"]["ensemble_probability"].isNull()) {
          float risk = response["prediction"]["ensemble_probability"].as<float>();
          if (isfinite(risk) && risk >= 0 && risk <= 1) {
            advisoryRisk = risk;
            riskAt = millis();
          }
        }
      }
    }
    http.end();

    if (status_code >= 200 && status_code < 300) {
      lastSuccess = millis();
      holding = false;
      retryMs = 1000;
      acknowledgeLocalDecision();
    } else if (status_code == 400 || status_code == 409 || status_code == 422) {
      dropped++;
      holding = false;
      Serial.printf("{\"event\":\"telemetry_rejected\",\"http\":%d,\"dropped\":%lu}\n", status_code, (unsigned long)dropped);
    } else {
      JsonDocument doc;
      deserializeJson(doc, packet.json);
      doc["buffered"] = true;
      serializeJson(doc, packet.json, sizeof(packet.json));
      Serial.printf("{\"event\":\"backend_retry\",\"http\":%d,\"queued\":%u}\n", status_code, uxQueueMessagesWaiting(queue));
      vTaskDelay(pdMS_TO_TICKS(retryMs));
      retryMs = min(retryMs * 2, uint32_t(10000));
    }
  }
}

void networkBegin() {
  snprintf(bootID, sizeof(bootID), "%08lx%08lx", (unsigned long)esp_random(), (unsigned long)esp_random());
  queue = xQueueCreate(8, sizeof(Packet));
  if (queue) {
    xTaskCreatePinnedToCore(worker, "telemetry", 16384, nullptr, 1, nullptr, 0);
  }
}

void networkEnqueue(const SensorData& s, const coldchain::Output& o, uint32_t now, const char* injection) {
  if (!queue) return;
  time_t nowTime = time(nullptr);
  if (nowTime <= 1700000000) return;

  struct tm utcTime;
  gmtime_r(&nowTime, &utcTime);
  char timestamp[32];
  strftime(timestamp, sizeof(timestamp), "%Y-%m-%dT%H:%M:%SZ", &utcTime);

  JsonDocument j;
  j["schema_version"] = "1.0";
  j["device_id"] = DEVICE_ID;
  j["boot_id"] = bootID;
  j["sequence"] = (uint32_t)(++sequence);
  j["timestamp"] = timestamp;
  j["uptime_ms"] = now;
  j["mode"] = "HARDWARE";

  auto number = [&](const char* key, float value, bool valid) {
    if (valid && isfinite(value)) j[key] = value;
    else j[key] = nullptr;
  };

  number("chamber_temp_c", s.chamber, s.chamberOK);
  j["chamber_source"] = "DERIVED";
  j["chamber_formula"] = "heatsink_temp_c - 10.0";
  if (s.rawChamberOK && isfinite(s.rawChamber)) {
    j["raw_chamber_temp_c"] = s.rawChamber;
  } else {
    j["raw_chamber_temp_c"] = nullptr;
  }
  number("heatsink_temp_c", s.heatsink, s.heatsinkOK);
  number("sht31_temp_c", s.shtTemp, s.shtOK);
  number("humidity_pct", s.humidity, s.shtOK);

  const bool isManualSmps = (PIN_COOLING_CONFIRM >= 0 && s.manualCoolingOk);

  bool currentAvailable = false;
  float currentVal = 0.0f;
  const char* currentSource = "NONE";
  if (s.currentOK && CURRENT_CALIBRATED) {
    currentAvailable = true;
    currentVal = s.current;
    currentSource = "ACS712";
  } else if (ENABLE_EMULATED_CURRENT) {
    currentAvailable = true;
    currentSource = "EMULATED";
    currentVal = isManualSmps
                   ? (s.manualCoolingOn ? EMULATED_PRIMARY_CURRENT_A : 0.0f)
                   : (primaryObserved() ? EMULATED_PRIMARY_CURRENT_A : 0.0f);
  }
  if (currentAvailable) j["primary_current_a"] = currentVal;
  else j["primary_current_a"] = nullptr;
  j["current_source"] = currentSource;
  j["current_calibrated"] = CURRENT_CALIBRATED;

  if (s.doorOK) j["door_open"] = s.doorOpen; else j["door_open"] = nullptr;
  j["door_open_s"] = (s.doorOK && s.doorOpen) ? s.doorSeconds : 0;

  auto gps = j["gps"].to<JsonObject>();
  gps["fix"] = s.gpsFix;
  gps["source"] = s.gpsFix ? "GPS" : "NONE";
  if (s.gpsFix) {
    gps["latitude"] = s.latitude;
    gps["longitude"] = s.longitude;
    gps["age_s"] = s.gpsAge;
    if (isfinite(s.speed)) gps["speed_kmph"] = s.speed; else gps["speed_kmph"] = nullptr;
  } else {
    gps["latitude"] = nullptr;
    gps["longitude"] = nullptr;
    gps["speed_kmph"] = nullptr;
    gps["age_s"] = nullptr;
  }
  gps["satellites"] = s.satellites;

  j["cooling_control_mode"] = isManualSmps ? "MANUAL_SMPS" : "GPIO_CONTROLLED";
  if (isManualSmps) {
    j["manual_cooling_confirmed"] = s.manualCoolingOn;
  } else {
    j["manual_cooling_confirmed"] = nullptr;
  }

  bool reportedPrimary = isManualSmps ? s.manualCoolingOn : primaryObserved();
  j["primary_cooling"] = reportedPrimary;

  bool virtualBackup = false;
  if (o.backup || o.state == coldchain::State::BACKUP_ACTIVE || o.state == coldchain::State::RECOVERY) {
    virtualBackup = true;
  }
  if (reportedPrimary && virtualBackup) {
    virtualBackup = false;
  }
  if (s.heatsinkOK && s.heatsink >= 50.0f) {
    virtualBackup = false;
  }
  j["backup_cooling"] = virtualBackup;
  j["backup_source"] = "VIRTUAL";
  j["backup_commissioned"] = false;

  j["system_state"] = coldchain::name(o.state);
  auto health = j["sensor_health"].to<JsonObject>();
  health["chamber"] = s.chamberOK;
  health["heatsink"] = s.heatsinkOK;
  health["sht31"] = s.shtOK;
  health["current"] = s.currentOK;
  health["door"] = s.doorOK;
  j["fault_injection"] = injection;
  j["buffered"] = (WiFi.status() != WL_CONNECTED);

  Packet packet;
  if (measureJson(j) >= sizeof(packet.json)) { dropped++; return; }
  serializeJson(j, packet.json, sizeof(packet.json));
  if (xQueueSend(queue, &packet, 0) != pdTRUE) {
    Packet old;
    xQueueReceive(queue, &old, 0);
    dropped++;
    xQueueSend(queue, &packet, 0);
  }

  char chStr[16], hsStr[16], shtStr[16], humStr[16], curStr[32], doorStr[24], gpsStr[16];
  if (s.chamberOK) snprintf(chStr, sizeof(chStr), "%.2f C", s.chamber); else snprintf(chStr, sizeof(chStr), "null");
  if (s.heatsinkOK) snprintf(hsStr, sizeof(hsStr), "%.2f C", s.heatsink); else snprintf(hsStr, sizeof(hsStr), "null");
  if (s.shtOK) {
    snprintf(shtStr, sizeof(shtStr), "%.2f C", s.shtTemp);
    snprintf(humStr, sizeof(humStr), "%.1f %%", s.humidity);
  } else {
    snprintf(shtStr, sizeof(shtStr), "null");
    snprintf(humStr, sizeof(humStr), "null");
  }
  if (s.currentOK) {
    snprintf(curStr, sizeof(curStr), "%.2f A", s.current);
  } else if (ENABLE_EMULATED_CURRENT) {
    snprintf(curStr, sizeof(curStr), "%.2f A (EMULATED)", currentVal);
  } else {
    snprintf(curStr, sizeof(curStr), "UNCALIBRATED");
  }
  if (s.doorOK) {
    if (s.doorOpen) snprintf(doorStr, sizeof(doorStr), "OPEN (%.1fs)", s.doorSeconds);
    else snprintf(doorStr, sizeof(doorStr), "CLOSED");
  } else {
    snprintf(doorStr, sizeof(doorStr), "UNKNOWN");
  }
  snprintf(gpsStr, sizeof(gpsStr), s.gpsFix ? "FIX" : "NO_FIX");

  Serial.printf("[SAMPLE] seq=%lu chamber=%s heatsink=%s sht31=%s humidity=%s door=%s vib=%s gps=%s sats=%lu current=%s\n",
                (unsigned long)sequence, chStr, hsStr, shtStr, humStr, doorStr,
                s.vibrationDetected ? "DETECTED" : "NORMAL", gpsStr, (unsigned long)s.satellites, curStr);
}

bool networkHealthy() {
  return lastSuccess > 0 && millis() - lastSuccess < 20000;
}

float networkAdvisoryRisk() {
  return riskAt > 0 && millis() - riskAt < 20000 ? advisoryRisk.load() : NAN;
}
