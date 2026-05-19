"""
╔══════════════════════════════════════════════════════════╗
║           FOOD SERVER                                   ║
║   Serves live_data.json to the browser                  ║
║   Browser + Scanner now read EXACT same data!           ║
╚══════════════════════════════════════════════════════════╝

SETUP:
------
1. Run data_engine.py first (Terminal 1)
2. Run this file (Terminal 2) 
3. Run deal_scanner.py (Terminal 3)
4. Open browser artifact

No extra installs needed — uses Python built-in http.server!
"""

import json
import http.server
import socketserver
from pathlib import Path
from datetime import datetime

PORT = 8765
LIVE_FILE = Path("live_data.json")
BASE_FILE = Path("restaurants_data.json")

HTML_FILE = Path("food_browser.html")

class FoodServerHandler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path == "/" or self.path == "/index.html":
            self.serve_html()
        elif self.path == "/live_data.json" or self.path.startswith("/live_data.json?"):
            self.serve_data()
        elif self.path == "/health":
            self.serve_health()
        else:
            self.send_error(404)

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_cors_headers()
        self.end_headers()

    def send_cors_headers(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")

    def serve_html(self):
        """Serve the browser HTML file"""
        try:
            if HTML_FILE.exists():
                content = HTML_FILE.read_bytes()
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_cors_headers()
                self.end_headers()
                self.wfile.write(content)
                print(f"[{datetime.now().strftime('%I:%M:%S %p')}] 🌐 Served browser to Chrome")
            else:
                self.send_error(404, "food_browser.html not found")
        except Exception as e:
            self.send_error(500, str(e))

    def serve_data(self):
        """Serve live_data.json or fallback to base file"""
        try:
            if LIVE_FILE.exists():
                data = LIVE_FILE.read_text(encoding="utf-8")
                source = "live_data.json"
            elif BASE_FILE.exists():
                data = BASE_FILE.read_text(encoding="utf-8")
                source = "restaurants_data.json (fallback)"
            else:
                self.send_error(404, "No data file found")
                return

            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_cors_headers()
            self.end_headers()
            self.wfile.write(data.encode("utf-8"))

            print(f"[{datetime.now().strftime('%I:%M:%S %p')}] ✅ Served {source} to browser")

        except Exception as e:
            self.send_error(500, str(e))
            print(f"[ERROR] {e}")

    def serve_health(self):
        """Health check endpoint"""
        status = {
            "status": "running",
            "live_file": LIVE_FILE.exists(),
            "base_file": BASE_FILE.exists(),
            "time": datetime.now().isoformat()
        }
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_cors_headers()
        self.end_headers()
        self.wfile.write(json.dumps(status).encode())

    def log_message(self, format, *args):
        pass  # Suppress default logs, we have our own


def main():
    print("╔══════════════════════════════════════╗")
    print("║         FOOD SERVER                  ║")
    print("╠══════════════════════════════════════╣")
    print(f"║  Port:      {PORT}                     ║")
    print(f"║  Data:      {'live_data.json ✅' if LIVE_FILE.exists() else 'restaurants_data.json ⚠'}     ║")
    print("║  Status:    Running...               ║")
    print("╚══════════════════════════════════════╝")
    print()

    if not LIVE_FILE.exists() and not BASE_FILE.exists():
        print("❌ ERROR: No data file found!")
        print("   Run data_engine.py first to create live_data.json")
        return

    if not LIVE_FILE.exists():
        print("⚠  live_data.json not found — run data_engine.py!")
        print("   Using restaurants_data.json as fallback for now")

    print(f"✅ Server running at:  http://localhost:{PORT}")
    print(f"🌐 Open browser at:    http://localhost:{PORT}")
    print(f"📄 Data endpoint:      http://localhost:{PORT}/live_data.json")
    print(f"❤  Health check:       http://localhost:{PORT}/health")
    print()
    print("Open Chrome and go to: http://localhost:8765")
    print("Keep this running while using the browser!")
    print("Press Ctrl+C to stop\n")

    with socketserver.TCPServer(("", PORT), FoodServerHandler) as httpd:
        httpd.allow_reuse_address = True
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\n👋 Server stopped!")


if __name__ == "__main__":
    main()
