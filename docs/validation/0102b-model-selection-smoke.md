# 0102B Validation: Plug-and-Play Model Selection and LLM Recommendations

Goal: confirm that the packaged app exposes recommendations, lets the user pick
a local model, and forwards that choice into local chat.

## Automated checks

Run:

```bash
cd backend
python -m pytest tests/test_llm_recommendations.py tests/test_system_insight.py tests/test_local_chat_runtime.py -q

cd ../frontend
npm test -- --run src/modules/InsightModule.test.tsx src/modules/ModelManagementModule.test.tsx src/modules/ConversationsModule.test.tsx
```

Expected result: all tests pass.

## Manual smoke checklist

1. Start the desktop app in release mode.
2. Open the Insight screen and confirm:
   - hardware facts render;
   - GPU/VRAM remain honestly marked as unavailable when not detected;
   - the LLM recommendation section is visible.
3. Open the Modelos screen and confirm:
   - the current model card renders;
   - recommended models are listed;
   - a model card exposes collapsed technical details;
   - clicking "Usar este modelo" updates the current selection.
4. Open Novo Chat / Conversas and confirm:
   - the session model selector is visible;
   - the selector lists intelligence profiles and detected models;
   - choosing a detected model updates the session selection chip/button.
5. Send a local-chat message and confirm:
   - the request succeeds;
   - the backend receives the selected `model_provider_id` and `model_name`;
   - the response is shown in the conversation history.

## What this does not validate

- It does not validate automatic downloads or model switching.
- It does not validate provider execution beyond the existing local-chat path.
- It does not change the Model Hub refresh contract.
