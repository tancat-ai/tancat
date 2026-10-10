# Install

## Requirements

| Requirement | Why |
|---|---|
| Python 3.14 or newer | `requires-python = ">=3.14"` in `pyproject.toml`. |
| [uv](https://docs.astral.sh/uv/) | The package manager. TanCat uses `uv sync`, not `pip`. |
| Chromium (Playwright) | The browser the generated tests run in. |
| An LLM endpoint | llama.cpp, Ollama, LM Studio, or a cloud provider. See [Configure your LLM](configure-llm.md). |
| Docker (optional) | Only if you want the container image. |

## Install from source

```bash
git clone https://github.com/tancat-ai/tancat.git
cd tancat
uv sync
uv run playwright install chromium
```

`uv sync` creates `.venv/` and installs the pinned dependency set from
`uv.lock`. `uv run playwright install chromium` downloads the browser build that
matches the Playwright version in the lockfile.

!!! tip "No `pip`"
    Use `uv add <package>` and `uv sync`. TanCat does not support a bare
    `pip install` workflow.

## Run it

=== "Streamlit UI"

    ```bash
    bash launch_ui.sh
    ```

    The launcher syncs dependencies and starts Streamlit. You should see:

    ```
    🚀  Starting UI at http://localhost:8501
    ```

    Open <http://localhost:8501>.

=== "CLI"

    ```bash
    bash launch_cli.sh
    ```

    The launcher starts the interactive menu. You should see the TanCat header
    and a numbered main menu.

=== "Docker"

    ```bash
    docker build -t tancat .
    docker run --rm -p 8501:8080 tancat
    ```

    The image runs the Streamlit UI on port 8080 inside the container. Mapping it
    to host port 8501 avoids the common clash with a llama.cpp server already
    using 8080. Open <http://localhost:8501>.

## Share a project between the UI and the CLI

The UI and the interactive CLI keep their learned locators in one store per
project. Name a project in the UI and the interactive CLI follows it
automatically. To point a headless `tancat run` or any other command at the
same project, set the same two variables:

```bash
AITEST_WORKSPACE=<project> AITEST_RAG_SCOPE=<project> tancat run --story story.md --url https://staging.example.com
```

`AITEST_WORKSPACE` chooses the store (`<root>/<project>/evidence/rag_store.db`);
`AITEST_RAG_SCOPE` tags each learned pattern `scope:<project>` so it follows the
project across a new port or host. `tancat run --workspace <project>` sets the
store half too, but not the scope. Leave both unset and the CLI keeps the legacy
`default` workspace and the host[:port] identity.

## Docker Compose

`docker-compose.yml` starts the app together with a bundled Ollama service and
runs the app against it:

```bash
docker compose up
```

The bundled Ollama is the Compose default and is **not** changed by your `.env` -
that file is host-oriented (`openai-local` and localhost URLs). To run a
different provider inside Compose, set `COMPOSE_LLM_PROVIDER` (and its base URL,
for example `OPENAI_BASE_URL`) in `.env`.

By design the Compose file publishes **no host port** - the app and Ollama talk
over the `playwright-network` bridge, and the app is on port 8080 inside that
network. If you want the UI on your machine, use the `docker run` command above
instead.

## Update

```bash
git pull
uv sync
```

Re-run `uv run playwright install chromium` after a Playwright version bump - a
new driver needs its matching browser build.

## Next

- [Configure your LLM](configure-llm.md)
- [Your first run](first-run.md)
