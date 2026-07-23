"""Serve the LV mock insurance site for eval scraping."""

import http.server
import socketserver
import sys

PORT = int(sys.argv[1]) if len(sys.argv) > 1 else 8779


class Handler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format, *args):
        print(f"[{self.client_address[0]}] {args[0]}")


with socketserver.TCPServer(("", PORT), Handler) as httpd:
    print(f"LV Mock Insurance Site running on http://localhost:{PORT}/generated_tests/mock_insurance_site.html")
    httpd.serve_forever()
