# Visual Privacy

Visual behavior is controlled by `DATA_DIR/config/perception_policy.yaml`.
Screenshots may be disabled globally; camera and OCR are disabled by default.
Application/window deny rules block capture before a raw file is written.
Sensitive captures can require an explicit approved policy context. Operating
system capture restrictions are honored and reported as structured errors.

Raw visual data has minute-scale retention and is excluded from events. Screen
raws are removed after analysis by default. OCR or provider-detected text is not
persisted unless the input policy context explicitly permits it. Events contain
only identifiers, counts, checksums, classifications, and safe error types.

The implementation does not provide continuous capture, background camera
startup, face identity recognition, or mechanisms to bypass protected screens.
