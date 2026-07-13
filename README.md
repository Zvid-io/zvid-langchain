# langchain-zvid — LangChain tools for Zvid

Give any LangChain agent the ability to render videos and images with
[Zvid](https://zvid.io). Thin `StructuredTool` wrappers over the official
[`zvid` Python SDK](../sdk-python).

```bash
pip install langchain-zvid   # pulls in zvid + langchain-core
```

## Usage

```python
from langchain_zvid import get_zvid_tools

tools = get_zvid_tools()  # reads ZVID_API_KEY (and ZVID_BASE_URL)

# e.g. with a LangChain agent
from langchain.agents import create_agent   # or your framework of choice
agent = create_agent(model, tools=tools)
agent.invoke({"messages": [("user", "Render a 1080p title card that says 'Ship it'")]})
```

Bring your own configured client if you need a custom base URL or timeout:

```python
from zvid import Zvid
from langchain_zvid import ZvidToolkit

tools = ZvidToolkit(Zvid(api_key="zvid_…", base_url="http://localhost:4000")).get_tools()
```

## Tools

| Tool | What it does | Credits |
| --- | --- | --- |
| `zvid_create_render` | Render a video **or image** from full project JSON (image payloads auto-route to the image endpoint) | yes |
| `zvid_render_from_template` | Render a stored template (`tpl_…`) with variable values | yes |
| `zvid_get_render` | State / progress / output URL of a render job | no |
| `zvid_wait_for_render` | Block until a job finishes; returns final state + output URL (never raises on render failure — the failure state is data for the agent) | no |
| `zvid_list_templates` | List stored templates with their variables | no |
| `zvid_preview_template` | **Dry-run** a template — resolved JSON + stats, nothing rendered | no |

All tools return JSON-serializable dicts. Renders are asynchronous: the create
tools return a `jobId` plus a note telling the model to call
`zvid_wait_for_render`.

## Development

```bash
python -m venv .venv && .venv/Scripts/activate
pip install -e ../sdk-python -e ".[dev]"
pytest
```

## Publishing (manual)

Not published yet — `python -m build && twine upload dist/*` (PyPI project
`langchain-zvid`), after publishing the `zvid` package it depends on.
