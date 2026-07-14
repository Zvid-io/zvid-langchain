import json
from typing import Dict, List, Optional, Tuple

import httpx
import pytest

from langchain_zvid import ZvidToolkit, get_zvid_tools
from zvid import Zvid

EXPECTED_TOOLS = [
    "zvid_get_project_schema",
    "zvid_list_supported_elements",
    "zvid_get_element_docs",
    "zvid_get_example_project",
    "zvid_repair_project",
    "zvid_validate_project",
    "zvid_create_render",
    "zvid_render_from_template",
    "zvid_get_render",
    "zvid_wait_for_render",
    "zvid_list_templates",
    "zvid_get_template",
    "zvid_create_template",
    "zvid_update_template",
    "zvid_duplicate_template",
    "zvid_preview_template",
    "zvid_delete_template",
]


class Routes:
    def __init__(self) -> None:
        self.routes: Dict[Tuple[str, str], List[httpx.Response]] = {}
        self.requests: List[httpx.Request] = []

    def add(self, method: str, path: str, body: Optional[dict] = None, status: int = 200) -> None:
        self.routes.setdefault((method.upper(), path), []).append(
            httpx.Response(status, json=body or {})
        )

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        queue = self.routes.get((request.method, request.url.path))
        if not queue:
            return httpx.Response(500, json={"error": "unmocked"})
        return queue.pop(0) if len(queue) > 1 else queue[0]


@pytest.fixture()
def routes() -> Routes:
    return Routes()


@pytest.fixture()
def tools(routes: Routes):
    http = httpx.Client(transport=httpx.MockTransport(routes.handler))
    client = Zvid(api_key="zvid_" + "a" * 64, base_url="https://api.test", http_client=http)
    return {tool.name: tool for tool in get_zvid_tools(client)}


def test_tool_suite_names(tools):
    assert sorted(tools) == sorted(EXPECTED_TOOLS)


def test_toolkit_matches_factory():
    toolkit_tools = ZvidToolkit(
        Zvid(api_key="zvid_" + "a" * 64, base_url="https://api.test")
    ).get_tools()
    assert [t.name for t in toolkit_tools] == EXPECTED_TOOLS


def test_tools_have_schemas(tools):
    for tool in tools.values():
        schema = tool.args_schema.model_json_schema()
        assert "properties" in schema, tool.name
        assert tool.description


def test_authoring_tools_retrieve_live_context_and_validate(tools, routes):
    routes.add(
        "GET",
        "/api/render/schema/api-key",
        {
            "schemaVersion": "1.0.0",
            "target": "project",
            "jsonSchema": {},
            "authoringGuidelines": ["Use scenes"],
        },
    )
    routes.add(
        "GET",
        "/api/render/elements/TEXT/api-key",
        {"schemaVersion": "1.0.0", "element": {"type": "TEXT"}},
    )
    routes.add(
        "GET",
        "/api/render/examples/promo-video/api-key",
        {"schemaVersion": "1.0.0", "example": {"name": "promo-video"}},
    )
    routes.add(
        "POST",
        "/api/render/validate/api-key",
        {"valid": True, "payload": {"duration": 5}, "warnings": []},
    )

    assert tools["zvid_get_project_schema"].invoke({})["schemaVersion"] == "1.0.0"
    assert tools["zvid_get_element_docs"].invoke({"element": "TEXT"})["element"]["type"] == "TEXT"
    assert (
        tools["zvid_get_example_project"].invoke({"name": "promo-video"})["example"]["name"]
        == "promo-video"
    )
    assert tools["zvid_validate_project"].invoke({"payload": {"duration": 5}})["valid"] is True


def test_create_render_routes_images(tools, routes):
    routes.add("POST", "/api/render/image/api-key", {"jobId": "j1", "status": "queued", "creditsReserved": 1}, 202)
    result = tools["zvid_create_render"].invoke(
        {"payload": {"type": "image", "visuals": [{"type": "TEXT", "text": "x"}]}}
    )
    assert result["jobId"] == "j1"
    assert routes.requests[0].url.path == "/api/render/image/api-key"


def test_create_render_video_endpoint(tools, routes):
    routes.add("POST", "/api/render/api-key", {"jobId": "j2", "status": "queued"}, 202)
    result = tools["zvid_create_render"].invoke({"payload": {"duration": 5}})
    assert result["jobId"] == "j2"
    assert routes.requests[0].url.path == "/api/render/api-key"


def test_render_from_template(tools, routes):
    routes.add("POST", "/api/render/api-key", {"jobId": "j3", "status": "queued"}, 202)
    result = tools["zvid_render_from_template"].invoke(
        {"template_id": "tpl_x", "variables": {"title": "Hi"}}
    )
    assert result["jobId"] == "j3"
    body = json.loads(routes.requests[0].content)
    assert body == {"template": "tpl_x", "variables": {"title": "Hi"}}


def test_get_render(tools, routes):
    routes.add("GET", "/api/jobs/j1", {"id": "j1", "state": "completed", "progress": 100, "result": "https://cdn/x.png"})
    result = tools["zvid_get_render"].invoke({"job_id": "j1"})
    assert result["state"] == "completed"
    assert result["outputUrl"] == "https://cdn/x.png"


def test_wait_for_render_returns_failure_instead_of_raising(tools, routes):
    routes.add("GET", "/api/jobs/j1", {"id": "j1", "state": "active", "progress": 10})
    routes.add("GET", "/api/jobs/j1", {"id": "j1", "state": "failed", "failedReason": "boom"})
    result = tools["zvid_wait_for_render"].invoke({"job_id": "j1", "poll_interval": 0.01})
    assert result["state"] == "failed"
    assert result["failedReason"] == "boom"


def test_list_templates(tools, routes):
    routes.add(
        "GET",
        "/api/templates",
        {
            "templates": [
                {
                    "id": "tpl_1",
                    "name": "Promo",
                    "type": "video",
                    "version": 1,
                    "status": "active",
                    "variablesSummary": [{"name": "title", "type": "string", "default": "Hi"}],
                }
            ],
            "pagination": {"page": 1, "limit": 20, "total": 1, "totalPages": 1},
        },
    )
    result = tools["zvid_list_templates"].invoke({})
    assert result["templates"][0]["variables"][0]["name"] == "title"


def test_preview_template(tools, routes):
    routes.add("POST", "/api/templates/tpl_1/preview", {"project": {"duration": 5}, "stats": {"credits": 3}})
    result = tools["zvid_preview_template"].invoke({"template_id": "tpl_1", "variables": {"t": "x"}})
    assert result["project"]["duration"] == 5
    assert result["stats"]["credits"] == 3


def test_template_crud_tools(tools, routes):
    template = {
        "id": "tpl_1",
        "name": "Promo",
        "project": {"duration": 5},
        "type": "video",
        "version": 1,
        "status": "active",
    }
    routes.add("POST", "/api/templates", {"template": template}, 201)
    routes.add("GET", "/api/templates/tpl_1", {"template": template})
    routes.add("PUT", "/api/templates/tpl_1", {"template": {**template, "name": "Updated"}})
    routes.add(
        "POST",
        "/api/templates/tpl_1/duplicate",
        {"template": {**template, "id": "tpl_2", "name": "Copy of Promo"}},
        201,
    )
    routes.add("DELETE", "/api/templates/tpl_1", {"archived": True, "id": "tpl_1"})

    assert tools["zvid_create_template"].invoke(
        {"name": "Promo", "payload": {"duration": 5}}
    )["id"] == "tpl_1"
    assert tools["zvid_get_template"].invoke({"template_id": "tpl_1"})["project"]["duration"] == 5
    assert tools["zvid_update_template"].invoke(
        {"template_id": "tpl_1", "name": "Updated"}
    )["name"] == "Updated"
    assert tools["zvid_duplicate_template"].invoke({"template_id": "tpl_1"})["id"] == "tpl_2"
    assert tools["zvid_delete_template"].invoke({"template_id": "tpl_1"})["archived"] is True
