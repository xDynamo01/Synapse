from __future__ import annotations

from typing import Any

from synapse.desktop_automation.errors import ProviderUnavailable, TargetNotFound
from synapse.desktop_automation.models import Bounds, ElementSelector, UIElement
from synapse.desktop_automation.providers.common import stable_id


class ScreenRuntime:
    """Authorized transient capture bridge to the frozen VisionRuntime."""

    def __init__(self, vision: Any) -> None:
        self.vision = vision

    def available(self, mode: str) -> bool:
        if mode == "ocr":
            policy = self.vision.capture.policy.load() if self.vision.capture else {}
            return bool(self.vision.ocr_provider.health().configured and policy.get("ocr_enabled"))
        capabilities = set(self.vision.vision_provider.capabilities())
        return bool(
            self.vision.vision_provider.health().configured
            and capabilities.intersection({"object_detection", "icon_detection", "layout_analysis"})
        )

    def find(self, selector: ElementSelector, *, mode: str, limit: int = 20) -> list[UIElement]:
        if not self.available(mode):
            raise ProviderUnavailable(f"{mode} fallback is not configured")
        image = self.vision.capture_screenshot(
            owner="desktop_automation",
            policy_context={"purpose": "desktop_element_location", "persist_detected_text": False},
        )
        try:
            result = self.vision.analyze_image(
                image,
                use_ocr=mode == "ocr",
                delete_raw_after=True,
            )
        finally:
            if self.vision.capture:
                self.vision.capture.delete_raw_asset(image)
        candidates = (
            self._ocr_candidates(result, selector)
            if mode == "ocr"
            else self._vision_candidates(result, selector)
        )
        if not candidates:
            raise TargetNotFound(f"No {mode} candidate matched the requested element")
        return candidates[: max(1, min(limit, 100))]

    def _ocr_candidates(self, result: Any, selector: ElementSelector) -> list[UIElement]:
        expected = str(selector.name or selector.value or "").casefold()
        candidates = []
        for region in result.regions:
            text = str(region.get("text", ""))
            box = region.get("bounding_box") or region.get("region")
            if not text or not box or (expected and expected not in text.casefold()):
                continue
            candidates.append(self._element("ocr", text, box, result.provider))
        return candidates

    def _vision_candidates(self, result: Any, selector: ElementSelector) -> list[UIElement]:
        expected = str(selector.name or selector.role or selector.control_type or "").casefold()
        candidates = []
        for item in result.objects:
            if not item.region or (expected and expected not in item.label.casefold()):
                continue
            candidates.append(self._element("vision", item.label, item.region, result.provider))
        return candidates

    @staticmethod
    def _element(kind: str, name: str, box: dict[str, Any], provider: str | None) -> UIElement:
        left = int(box.get("x", box.get("left", 0)))
        top = int(box.get("y", box.get("top", 0)))
        width = int(box.get("width", 0))
        height = int(box.get("height", 0))
        bounds = Bounds(left, top, width, height)
        return UIElement(
            element_id=stable_id(kind, name, bounds),
            window_id="visual:screen",
            automation_id=None,
            role="visual_candidate",
            control_type="visual_candidate",
            name=name[:240],
            description=None,
            value=None,
            enabled=True,
            focused=False,
            selected=None,
            expanded=None,
            toggled=None,
            range_value=None,
            bounds=bounds,
            patterns=[kind],
            provider=provider or kind,
        )
