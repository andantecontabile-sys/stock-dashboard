import http.server
import socketserver
import subprocess
import json
import os

PORT = 8080

class DashboardHandler(http.server.SimpleHTTPRequestHandler):
    def do_POST(self):
        if self.path == '/api/update' or self.path.startswith('/api/update'):
            try:
                res = subprocess.run(["python3", "scripts/build.py"], capture_output=True, text=True)
                print("Build script output:", res.stdout)
                if res.stderr:
                    print("Build script stderr:", res.stderr)
                
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                response = json.dumps({"status": "ok", "message": "Updated successfully", "output": res.stdout})
                self.wfile.write(response.encode('utf-8'))
            except Exception as e:
                self.send_response(500)
                self.send_header('Content-type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.end_headers()
                err_resp = json.dumps({"status": "error", "message": str(e)})
                self.wfile.write(err_resp.encode('utf-8'))
        else:
            self.send_error(404, "Not Found")

    def do_GET(self):
        if self.path == '/api/update' or self.path.startswith('/api/update'):
            self.do_POST()
        else:
            super().do_GET()

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

if __name__ == "__main__":
    script_dir = os.path.dirname(os.path.abspath(__file__))
    if script_dir:
        os.chdir(script_dir)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), DashboardHandler) as httpd:
        print(f"Serving Stock Dashboard API & Static Files at http://localhost:{PORT}")
        httpd.serve_forever()
