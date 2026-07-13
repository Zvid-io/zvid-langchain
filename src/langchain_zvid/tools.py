"""LangChain StructuredTools over the official ``zvid`` Python SDK.

Build the tools once (optionally with your own configured client) and hand
them to any LangChain agent::

    from langchain_zvid import get_zvid_tools

    tools = get_zvid_tools()  # reads ZVID_API_KEY / ZVID_BASE_URL

Every tool returns JSON-serializable dicts so results flow straight back
into the model context.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from langchain_core.tools import BaseTool, StructuredTool
from pydantic import BaseModel, Field

from zvid import Zvid
from zvid.models import JobStatus

__all__ = ["get_zvid_tools", "ZvidToolkit"]


def _job_dict(job: JobStatus) -> Dict[str, Any]:
    return {
        "jobId": job.id,
        "state": job.state,
        "progressPercent": job.progress_percent,
        "outputUrl": job.output_url,
        "thumbnailUrl": job.thumbnail_url,
        "failedReason": job.failed_reason,
    }


class CreateRenderInput(BaseModel):
    payload: Dict[str, Any] = Field(
        description=(
            "Full Zvid project JSON. Minimal video: {'visuals': [{'type': 'TEXT', "
            "'text': 'Hello'}], 'duration': 5}. For a still image set "
            "'type': 'image' (and no duration/audio/video elements)."
        )
    )
    webhook_url: Optional[str] = Field(
        default=None, description="Optional one-off webhook URL notified when the render finishes."
    )


class RenderFromTemplateInput(BaseModel):
    template_id: str = Field(description="Stored template id (tpl_…). Use zvid_list_templates to discover ids.")
    variables: Optional[Dict[str, Any]] = Field(
        default=None, description="Variable values merged over the template defaults."
    )
    webhook_url: Optional[str] = Field(
        default=None, description="Optional one-off webhook URL notified when the render finishes."
    )


class GetRenderInput(BaseModel):
    job_id: str = Field(description="Render job id returned by a render tool.")


class WaitForRenderInput(BaseModel):
    job_id: str = Field(description="Render job id returned by a render tool.")
    timeout: float = Field(default=300, description="Give up after this many seconds.")
    poll_interval: float = Field(default=2, description="Seconds between status polls.")


class ListTemplatesInput(BaseModel):
    page: int = Field(default=1, description="Page number (20 templates per page).")


class PreviewTemplateInput(BaseModel):
    template_id: str = Field(description="Stored template id (tpl_…).")
    variables: Optional[Dict[str, Any]] = Field(
        default=None, description="Variable values to resolve the template with."
    )


def get_zvid_tools(client: Optional[Zvid] = None) -> List[BaseTool]:
    """Return the Zvid tool suite bound to ``client`` (or a default one).

    Tools: zvid_create_render, zvid_render_from_template, zvid_get_render,
    zvid_wait_for_render, zvid_list_templates, zvid_preview_template.
    """
    zvid_client = client or Zvid()

    def create_render(payload: Dict[str, Any], webhook_url: Optional[str] = None) -> Dict[str, Any]:
        is_image = payload.get("type") == "image"
        create = zvid_client.renders.create_image if is_image else zvid_client.renders.create
        job = create(payload=payload, webhook_url=webhook_url)
        return {
            "jobId": job.job_id,
            "status": job.status,
            "creditsReserved": job.credits_reserved,
            "note": "Render is asynchronous — use zvid_wait_for_render or zvid_get_render.",
        }

    def render_from_template(
        template_id: str,
        variables: Optional[Dict[str, Any]] = None,
        webhook_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        job = zvid_client.renders.create(
            template=template_id, variables=variables, webhook_url=webhook_url
        )
        return {
            "jobId": job.job_id,
            "status": job.status,
            "creditsReserved": job.credits_reserved,
            "note": "Render is asynchronous — use zvid_wait_for_render or zvid_get_render.",
        }

    def get_render(job_id: str) -> Dict[str, Any]:
        return _job_dict(zvid_client.jobs.get(job_id))

    def wait_for_render(job_id: str, timeout: float = 300, poll_interval: float = 2) -> Dict[str, Any]:
        job = zvid_client.wait_for_render(
            job_id, timeout=timeout, poll_interval=poll_interval, raise_on_failure=False
        )
        return _job_dict(job)

    def list_templates(page: int = 1) -> Dict[str, Any]:
        result = zvid_client.templates.list(page=page)
        return {
            "templates": [
                {
                    "id": t.id,
                    "name": t.name,
                    "type": t.type,
                    "description": t.description,
                    "variables": [
                        {"name": v.name, "type": v.type, "default": v.default}
                        for v in t.variables_summary
                    ],
                }
                for t in result.templates
            ],
            "page": result.pagination.page,
            "totalPages": result.pagination.total_pages,
        }

    def preview_template(template_id: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        preview = zvid_client.templates.preview(template_id, variables=variables)
        return {"project": preview.project, "stats": preview.stats}

    return [
        StructuredTool.from_function(
            func=create_render,
            name="zvid_create_render",
            description=(
                "Render a video or still image from a full Zvid project JSON payload. "
                "Costs credits. Returns a jobId immediately (rendering is asynchronous)."
            ),
            args_schema=CreateRenderInput,
        ),
        StructuredTool.from_function(
            func=render_from_template,
            name="zvid_render_from_template",
            description=(
                "Render from a stored Zvid template (tpl_…) with per-render variable values. "
                "Costs credits. Returns a jobId immediately (rendering is asynchronous)."
            ),
            args_schema=RenderFromTemplateInput,
        ),
        StructuredTool.from_function(
            func=get_render,
            name="zvid_get_render",
            description="Get the current state, progress, and output URL of a Zvid render job.",
            args_schema=GetRenderInput,
        ),
        StructuredTool.from_function(
            func=wait_for_render,
            name="zvid_wait_for_render",
            description=(
                "Block until a Zvid render job finishes (or the timeout passes) and return its "
                "final state including the output URL. Prefer this right after starting a render."
            ),
            args_schema=WaitForRenderInput,
        ),
        StructuredTool.from_function(
            func=list_templates,
            name="zvid_list_templates",
            description="List the account's stored Zvid render templates with their variables.",
            args_schema=ListTemplatesInput,
        ),
        StructuredTool.from_function(
            func=preview_template,
            name="zvid_preview_template",
            description=(
                "Dry-run a Zvid template with variable values: returns the fully resolved project "
                "JSON and stats WITHOUT spending credits or rendering anything."
            ),
            args_schema=PreviewTemplateInput,
        ),
    ]


class ZvidToolkit:
    """Convenience wrapper: ``ZvidToolkit(client=...).get_tools()``."""

    def __init__(self, client: Optional[Zvid] = None) -> None:
        self._client = client

    def get_tools(self) -> List[BaseTool]:
        return get_zvid_tools(self._client)
