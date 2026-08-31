from synapse.core.exceptions import NotFound, ValidationError


class MultimodalFusionInvalid(ValidationError):
    code = "multimodal_fusion_invalid"
    status_code = 422

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": str(self), "details": {}}


class MultimodalFusionFailed(MultimodalFusionInvalid):
    code = "multimodal_fusion_failed"
    status_code = 500


class MultimodalObservationNotFound(NotFound):
    code = "multimodal_observation_not_found"
    status_code = 404

    def to_dict(self) -> dict[str, object]:
        return {"code": self.code, "message": str(self), "details": {}}
