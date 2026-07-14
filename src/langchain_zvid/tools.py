"""LangChain StructuredTools over the official ``zvid`` Python SDK.

Build the tools once (optionally with your own configured client) and hand
them to any LangChain agent::

    from langchain_zvid import get_zvid_tools

    tools = get_zvid_tools()  # reads ZVID_API_KEY / ZVID_BASE_URL

Every tool returns JSON-serializable dicts so results flow straight back
into the model context.
"""

from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional

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


class GetTemplateInput(BaseModel):
    template_id: str = Field(description="Owned stored template id (tpl_â€¦).")


class CreateTemplateInput(BaseModel):
    name: str = Field(description="Human-readable template name.", min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    payload: Dict[str, Any] = Field(description="Complete reusable Zvid project JSON.")


class UpdateTemplateInput(BaseModel):
    template_id: str = Field(description="Owned active template id (tpl_â€¦).")
    name: Optional[str] = Field(default=None, min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=2000)
    payload: Optional[Dict[str, Any]] = Field(
        default=None, description="Complete replacement project JSON."
    )


class PreviewTemplateInput(BaseModel):
    template_id: str = Field(description="Stored template id (tpl_…).")
    variables: Optional[Dict[str, Any]] = Field(
        default=None, description="Variable values to resolve the template with."
    )


class GetProjectSchemaInput(BaseModel):
    target: Literal["project", "render-request"] = Field(
        default="project",
        description="Use project for a payload or render-request for the full API envelope.",
    )


class EmptyInput(BaseModel):
    pass


class GetElementDocsInput(BaseModel):
    element: Literal["IMAGE", "VIDEO", "GIF", "SVG", "TEXT", "AUDIO", "SUBTITLE", "SCENE"]


class GetExampleProjectInput(BaseModel):
    name: Literal[
        "promo-video", "template-render", "still-image", "subtitles", "webhook-flow"
    ] = "promo-video"


class ProjectJsonInput(BaseModel):
    payload: Dict[str, Any] = Field(description="Complete AI-authored Zvid project JSON.")


def get_zvid_tools(client: Optional[Zvid] = None) -> List[BaseTool]:
    """Return the Zvid tool suite bound to ``client`` (or a default one).

    Includes plan-aware schema/docs/examples/repair/validation tools plus the
    render, status, and template tools.
    """
    zvid_client = client or Zvid()

    def get_project_schema(target: str = "project") -> Dict[str, Any]:
        return zvid_client.authoring.get_schema(target)

    def list_supported_elements() -> Dict[str, Any]:
        return zvid_client.authoring.list_elements()

    def get_element_docs(element: str) -> Dict[str, Any]:
        return zvid_client.authoring.get_element_docs(element)

    def get_example_project(name: str = "promo-video") -> Dict[str, Any]:
        return zvid_client.authoring.get_examples(name)

    def repair_project(payload: Dict[str, Any]) -> Dict[str, Any]:
        return zvid_client.authoring.repair(payload)

    def validate_project(payload: Dict[str, Any]) -> Dict[str, Any]:
        return zvid_client.authoring.validate(payload=payload)

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

    def get_template(template_id: str) -> Dict[str, Any]:
        return zvid_client.templates.get(template_id).model_dump(mode="json", by_alias=True)

    def create_template(
        name: str,
        payload: Dict[str, Any],
        description: Optional[str] = None,
    ) -> Dict[str, Any]:
        return zvid_client.templates.create(
            name, payload, description=description
        ).model_dump(mode="json", by_alias=True)

    def update_template(
        template_id: str,
        name: Optional[str] = None,
        description: Optional[str] = None,
        payload: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        return zvid_client.templates.update(
            template_id,
            name=name,
            description=description,
            payload=payload,
        ).model_dump(mode="json", by_alias=True)

    def duplicate_template(template_id: str) -> Dict[str, Any]:
        return zvid_client.templates.duplicate(template_id).model_dump(
            mode="json", by_alias=True
        )

    def delete_template(template_id: str) -> Dict[str, Any]:
        return zvid_client.templates.archive(template_id)

    def preview_template(template_id: str, variables: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        preview = zvid_client.templates.preview(template_id, variables=variables)
        return {"project": preview.project, "stats": preview.stats}

    return [
        StructuredTool.from_function(
            func=get_project_schema,
            name="zvid_get_project_schema",
            description=(
                "Read this before authoring JSON. Returns the caller-plan-aware schema, "
                "validation notes, professional layout guidelines, and required workflow."
            ),
            args_schema=GetProjectSchemaInput,
        ),
        StructuredTool.from_function(
            func=list_supported_elements,
            name="zvid_list_supported_elements",
            description=(
                "List every supported visual/audio/subtitle/scene element and required fields. "
                "Use zvid_get_element_docs for each type needed by the brief."
            ),
            args_schema=EmptyInput,
        ),
        StructuredTool.from_function(
            func=get_element_docs,
            name="zvid_get_element_docs",
            description="Get fields, constraints, gotchas, and a valid example for one element type.",
            args_schema=GetElementDocsInput,
        ),
        StructuredTool.from_function(
            func=get_example_project,
            name="zvid_get_example_project",
            description="Get a validated, layout-clean project to use as the authoring starting point.",
            args_schema=GetExampleProjectInput,
        ),
        StructuredTool.from_function(
            func=repair_project,
            name="zvid_repair_project",
            description=(
                "Conservatively repair mechanical project JSON mistakes and return changes, "
                "remaining errors, and professional layout warnings."
            ),
            args_schema=ProjectJsonInput,
        ),
        StructuredTool.from_function(
            func=validate_project,
            name="zvid_validate_project",
            description=(
                "Required before rendering. Validate against the real backend and plan limits "
                "for free; fix every error and professional layout warning."
            ),
            args_schema=ProjectJsonInput,
        ),
        StructuredTool.from_function(
            func=create_render,
            name="zvid_create_render",
            description=(
                "Render a video or still image from a full Zvid project JSON payload. "
                "Costs credits; call zvid_validate_project first and do not render with "
                "errors or layout warnings. Returns a jobId immediately."
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
            func=get_template,
            name="zvid_get_template",
            description=(
                "Get one owned template including complete project JSON, variables, version, and "
                "status. Use this before updating so existing fields are not lost."
            ),
            args_schema=GetTemplateInput,
        ),
        StructuredTool.from_function(
            func=create_template,
            name="zvid_create_template",
            description=(
                "Create a reusable video or image template. Retrieve the project schema first; "
                "placeholders need safe defaults and video scenes need explicit durations."
            ),
            args_schema=CreateTemplateInput,
        ),
        StructuredTool.from_function(
            func=update_template,
            name="zvid_update_template",
            description=(
                "Update an owned active template's name, description, and/or complete project JSON. "
                "Get it first; replacement JSON is validated before saving."
            ),
            args_schema=UpdateTemplateInput,
        ),
        StructuredTool.from_function(
            func=duplicate_template,
            name="zvid_duplicate_template",
            description=(
                "Create an active editable copy of an owned template. The copy consumes one "
                "template quota slot."
            ),
            args_schema=GetTemplateInput,
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
        StructuredTool.from_function(
            func=delete_template,
            name="zvid_delete_template",
            description=(
                "Archive an owned active template. It cannot be rendered or updated afterward; "
                "use only when the user explicitly asks to remove it."
            ),
            args_schema=GetTemplateInput,
        ),
    ]


class ZvidToolkit:
    """Convenience wrapper: ``ZvidToolkit(client=...).get_tools()``."""

    def __init__(self, client: Optional[Zvid] = None) -> None:
        self._client = client

    def get_tools(self) -> List[BaseTool]:
        return get_zvid_tools(self._client)
