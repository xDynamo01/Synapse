# Vision and Capture

`local_image_metadata` and `mss_local` project independently as Vision and Capture
providers. `not_configured` remains the availability of the null OCR/Camera ports
and is deliberately not registered as an identity. Cancellation is not claimed for
the local metadata implementation because its current `cancel` returns false.

`CaptureRuntime` owns explicit screen capture, image validation, short-lived raw
storage, authorization, source enumeration, and deletion. `VisionRuntime` owns
provider execution and converts real provider outputs to Perception signals. It
does not decide user intent or actions.

`VisionProvider`, `OCRProvider`, `CameraProvider`, and `ScreenCaptureProvider`
are provider-neutral protocols. The default local vision provider validates
image decoding, dimensions, MIME, checksum, and size; it clearly reports that
semantic analysis is not configured. OCR and camera default to
`not_configured`, do not degrade global readiness, and never start
automatically. Controlled implementations are injected only by tests.

Screenshots are explicit, policy-gated operations. Raw screenshots are deleted
after analysis by default. Uploaded images and camera frames receive short
retention and can be deleted explicitly. API/events expose IDs and checksums,
never absolute filesystem paths. Missing evidence remains `null` or absent;
identity, emotion, and intent are not inferred.
