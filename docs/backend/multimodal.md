# Multimodal Fusion

`MultimodalCommunicationRuntime` retains its communication-session contract and
adds durable `MultimodalObservation` records. Fusion accepts active Perception
observation IDs or a correlation ID, applies a bounded temporal window, and
requires at least two modalities.

The result preserves every source observation and signal provenance. Its
interpretation records modality and observation types without blindly joining
text. Fusion confidence is the minimum of supplied confidences; it remains
`null` when sources provide none. Relevance is the mean of supplied relevance
values. Registered Perception conflicts are attached and never silently
resolved. The Context Fusion preview is structured and does not build a final
model prompt.
