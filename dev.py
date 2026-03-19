import subprocess
from livereload import Server

def build():
    # Rebuild generated JSON whenever source data, scripts, or docs change during local work.
    print("🔧 Building site...")
    subprocess.run(["python3", "scripts/build_site.py"])

if __name__ == "__main__":
    build()

    server = Server()

    # Watch both pipeline inputs and frontend assets so local preview stays fresh.
    server.watch("data/", build)
    server.watch("scripts/", build)
    server.watch("docs/")

    print("🚀 Dev server running at http://localhost:8000")
    server.serve(root="docs", port=8000)
