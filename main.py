# src/main.py
import datetime
import os
import re
import subprocess
import sys
from pathlib import Path

from src.test_generator import TestGenerator

GENERATED_TESTS_DIR = Path.cwd() / "generated_tests"
MOCK_SITE_DIR = GENERATED_TESTS_DIR
MOCK_SITE_PORT = 8080
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen3.5:35b")

# Initialize the client (implicitly used via the chat function in python-ollama)
# If you need explicit client management, you can do:
# from ollama import Client
# client = Client(host="http://localhost:11434")


def slugify(text: str, max_length: int = 100) -> str:
    """Convert feature name to a valid Python variable name, truncated to max_length.

    Windows has a 255 character filename limit, so we truncate to prevent
    OSError: [Errno 22] Invalid argument on long filenames.
    """
    slug = re.sub(r"[^a-zA-Z0-9]", "_", text)
    slug = slug.strip("_")
    slug = slug.lower()

    # Truncate to max_length to avoid Windows filename length issues
    if len(slug) > max_length:
        slug = slug[:max_length]

    return slug


def save_generated_test(feature_name: str, code: str, base_dir: Path) -> Path | None:
    """Save generated test code to a file with proper naming and overwrite handling.

    Returns the saved file path, or None if the user cancelled.
    """
    slug = slugify(feature_name)
    test_filename = f"test_{slug}.py"
    target_path = base_dir / test_filename

    # Handle existing files
    counter = 1
    while target_path.exists():
        print("\n" + "─" * 50)
        print(f"⚠️  {test_filename} already exists!")
        print("─" * 50)
        choice = input(f"[1] Overwrite | [2] Rename to test_{slug}_{counter}.py | [3] Cancel: ").strip()

        if choice == "1":
            break
        elif choice == "2":
            test_filename = f"test_{slug}_{counter}.py"
            target_path = base_dir / test_filename
            counter += 1
        elif choice == "3":
            print("❌ File save cancelled.")
            return None

    # Create directory if it doesn't exist
    base_dir.mkdir(parents=True, exist_ok=True)

    # Write the file
    with open(target_path, "w", encoding="utf-8") as f:
        f.write(f"# Auto-generated test for: {feature_name}\n")
        f.write(f"# Generated on: {datetime.datetime.now()}\n")
        f.write("#\n")
        f.write("# The locators in this test may need to be adjusted to match your current application.\n\n")
        f.write(code)

    print(f"\n✅ File saved to: {target_path.absolute()}")
    return target_path


def generate_playwright_tests(feature_name: str) -> str:
    """Generate Playwright pytest tests using the shared TestGenerator pipeline."""
    generator = TestGenerator()
    request = f"Generate Playwright pytest tests for feature: {feature_name}"
    path = generator.generate_and_save(request)
    with open(path, encoding="utf-8") as f:
        return f.read()


def start_mock_server(port: int = MOCK_SITE_PORT) -> None:
    """Start a simple HTTP server for the mock insurance site.

    Opens a browser window automatically and keeps the server running.
    """
    mock_html = MOCK_SITE_DIR / "mock_insurance_site.html"
    if not mock_html.exists():
        print(f"\n❌ ERROR: Mock site not found at {mock_html}")
        print(f"Please ensure you're running from: {Path.cwd()}")
        print("Run: python main.py serve\n")
        return

    base_url = f"http://localhost:{port}"

    print("\n" + "═" * 50)
    print("🚀 Mock Server Started")
    print("═" * 50)
    print(f"📍 URL: {base_url}")
    print(f"📁 Serving from: {MOCK_SITE_DIR.absolute()}")
    print("🌐 Browser will open automatically...")
    print("⏹️  Press Ctrl+C to stop the server")
    print("─" * 50 + "\n")

    # Start the server in a subprocess
    server = subprocess.Popen(
        [sys.executable, "-m", "http.server", str(port)],
        cwd=MOCK_SITE_DIR,
        creationflags=subprocess.CREATE_NEW_CONSOLE if sys.platform == "win32" else 0,  # type: ignore[attr-defined]
    )

    # Open browser
    try:
        import webbrowser

        print("🌐 Opening browser...")
        webbrowser.open(base_url)
    except Exception:
        print("⚠️  Could not open browser automatically.")
        print(f"   Open: {base_url} in your browser\n")

    try:
        server.wait()
    except KeyboardInterrupt:
        print("\n" + "─" * 50)
        print("🛑 Stopping server...")
        print("─" * 50)
        server.terminate()


def main() -> None:
    """Main entry point for the test generator."""
    print("AI Playwright Test Generator")
    print("=" * 40)
    print("\nOptions:")
    print("[1] Generate Playwright test (standard mode)")
    print("[2] Generate test with auto-open mock site")
    print("[3] Start mock server only")
    print("[4] Generate test (headless, no UI)")
    print("[x] Exit")
    print()

    choice = input("Choose an option: ").strip()

    if choice == "1":
        # Standard mode - generate and save test
        user_input = input("Enter the feature to test (e.g., 'User Login', 'Checkout Process'): ")

        if not user_input.strip():
            print("❌ Input cannot be empty.")
            return

        print(f"\n🧠 Generating tests with {OLLAMA_MODEL}...")
        generated_code = generate_playwright_tests(user_input)

        print("\n" + "=" * 40)
        print("📄 Generated Playwright Test Code")
        print("=" * 40)
        print(generated_code)
        print("=" * 40)

        saved_file = save_generated_test(user_input, generated_code, GENERATED_TESTS_DIR)

        if saved_file:
            print("\n📋 Generated Test Options")
            print("=" * 40)
            print("[1] Save to file and run pytest")
            print("[2] Save to file only")
            print("[3] Display test command only")
            print("[4] Generate another test")
            print("[5] Exit")
            print("=" * 40)

            while True:
                test_choice = input("\nChoose an option: ").strip()

                if test_choice == "1":
                    print(f"\n🧪 Running pytest on {saved_file}...")
                    os.system(f"pytest {saved_file}")
                    break
                elif test_choice == "2":
                    print("\n✅ Test saved successfully!")
                    print(f"Run with: pytest {saved_file}")
                    break
                elif test_choice == "3":
                    print(f"\n🧪 To run this test, execute: pytest {saved_file}")
                    break
                elif test_choice == "4":
                    main()
                    return
                elif test_choice == "5":
                    print("👋 Goodbye!")
                    return
                else:
                    print("❌ Invalid option. Please choose 1-5.")

    elif choice == "2":
        # Generate test with mock site open
        user_input = input("Enter the feature to test (e.g., 'User Login', 'Checkout Process'): ")

        if not user_input.strip():
            print("❌ Input cannot be empty.")
            return

        # Start mock server in background
        import threading

        server_thread = threading.Thread(target=start_mock_server, daemon=True)
        server_thread.start()

        # Wait a moment for server to start
        import time

        time.sleep(2)

        print(f"\n🧠 Generating tests with {OLLAMA_MODEL}...")
        generated_code = generate_playwright_tests(user_input)

        print("\n" + "=" * 40)
        print("📄 Generated Playwright Test Code")
        print("=" * 40)
        print(generated_code)
        print("=" * 40)

        saved_file = save_generated_test(user_input, generated_code, GENERATED_TESTS_DIR)

        if saved_file:
            print(f"\n✅ Test saved to: {saved_file}")
            print("Open your browser to http://localhost:8080 to see the mock site")
            print(f"Run tests with: pytest {saved_file}")

    elif choice == "3":
        # Serve mock site only
        start_mock_server()

    elif choice == "4":
        # Headless mode - just output code
        user_input = input("Enter the feature to test: ")
        if not user_input.strip():
            print("❌ Input cannot be empty.")
            return

        generated_code = generate_playwright_tests(user_input)
        print("\n" + "=" * 40)
        print("📄 Generated Playwright Test Code (Headless)")
        print("=" * 40)
        print(generated_code)
        print("=" * 40)

    elif choice.lower() in ["x", "quit", "exit"]:
        print("👋 Goodbye!")

    else:
        print("❌ Invalid option. Please choose 1-4 or x to exit.")


if __name__ == "__main__":
    main()
