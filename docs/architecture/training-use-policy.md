# Training-use policy

The preparatory contract records `prohibited`, `local_evaluation_only`,
`local_training_allowed`, `local_fine_tuning_allowed`,
`local_distillation_allowed`, `tenant_training_allowed`,
`external_training_prohibited` or `explicit_consent_required`.

This phase implements no training, fine-tuning, distillation, LoRA, Private
Evals runtime or dataset builder. Derived assets preserve source restrictions;
a prohibited source contaminates a future dataset for unauthorized use.
