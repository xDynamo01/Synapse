use crate::{
    contracts::{CoreError, CoreResult, ModelManifest, SkillManifest, bounded, scope},
    store,
};
use rusqlite::{OptionalExtension, Transaction, params};
use serde_json::{Value, json};

pub(crate) fn model_register(tx: &Transaction<'_>, model: &ModelManifest) -> CoreResult<Value> {
    if let Some(generation) = &model.generation {
        generation.validate()?;
    }
    bounded(&model.id, "model_id", 128)?;
    bounded(&model.provider, "provider", 128)?;
    bounded(&model.endpoint, "endpoint", 1024)?;
    if model.capabilities.is_empty() || model.capabilities.len() > 32 {
        return Err(CoreError::invalid("Invalid model capabilities"));
    }
    for capability in &model.capabilities {
        bounded(capability, "capability", 128)?;
    }
    let exists: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM models WHERE id=?1)",
        [&model.id],
        |r| r.get(0),
    )?;
    if exists {
        return Err(CoreError::new(
            "already_exists",
            "Model ID already registered",
        ));
    }
    tx.execute(
        "INSERT INTO models(id,manifest) VALUES(?1,?2)",
        params![model.id, serde_json::to_string(model)?],
    )?;
    store::event(tx, "model_registered", json!({"model_id":model.id}))?;
    Ok(json!({"model":model,"operational":false}))
}

fn page(after: u64, limit: u32) -> CoreResult<()> {
    if after > i64::MAX as u64 || !(1..=100).contains(&limit) {
        return Err(CoreError::invalid(
            "Invalid registry cursor or limit (1..100)",
        ));
    }
    Ok(())
}

pub(crate) fn models_list(tx: &Transaction<'_>, after: u64, limit: u32) -> CoreResult<Value> {
    page(after, limit)?;
    let mut q =
        tx.prepare("SELECT rowid,manifest FROM models WHERE rowid>?1 ORDER BY rowid LIMIT ?2")?;
    let rows = q.query_map(params![after as i64, (limit + 1) as i64], |r| {
        Ok((r.get::<_, i64>(0)?, r.get::<_, String>(1)?))
    })?;
    let mut models = Vec::new();
    let mut bytes = 0;
    let mut next_cursor = after;
    let mut has_more = false;
    for row in rows {
        let (cursor, raw) = row?;
        if models.len() >= limit as usize {
            has_more = true;
            break;
        }
        let manifest: ModelManifest = serde_json::from_str(&raw)?;
        let item = json!({"id":manifest.id,"provider":manifest.provider,"capabilities":manifest.capabilities,"memory_bytes":manifest.memory_bytes,"operational":false});
        let size = serde_json::to_vec(&item)?.len();
        if bytes + size > 220_000 {
            if models.is_empty() {
                return Err(CoreError::new(
                    "response_too_large",
                    "A model summary exceeds page byte budget",
                ));
            }
            has_more = true;
            break;
        }
        bytes += size;
        next_cursor = cursor as u64;
        models.push(item);
    }
    Ok(json!({"models":models,"next_cursor":next_cursor,"has_more":has_more}))
}

pub(crate) fn resolve_chat_model<'a>(
    tx: &Transaction<'_>,
    model_id: &'a str,
    budget: Option<u64>,
) -> CoreResult<std::borrow::Cow<'a, str>> {
    match budget {
        None => Ok(model_id.into()),
        Some(budget) if model_id.is_empty() => {
            let selected = select_model(tx, "chat", budget)?;
            Ok(selected.id.into())
        }
        Some(_) => Err(CoreError::invalid("Choose a model ID or a routing budget")),
    }
}

pub(crate) fn model_route(
    tx: &Transaction<'_>,
    capability: &str,
    memory_budget_bytes: u64,
) -> CoreResult<Value> {
    let selected = select_model(tx, capability, memory_budget_bytes)?;
    Ok(json!({"model_id":selected.id,"capability":capability,"memory_bytes":selected.memory_bytes}))
}

fn select_model(
    tx: &Transaction<'_>,
    capability: &str,
    memory_budget_bytes: u64,
) -> CoreResult<ModelManifest> {
    bounded(capability, "model_capability", 128)?;
    if memory_budget_bytes == 0 {
        return Err(CoreError::invalid("Model memory budget must be positive"));
    }
    let mut query = tx.prepare("SELECT manifest FROM models ORDER BY id")?;
    let rows = query.query_map([], |row| row.get::<_, String>(0))?;
    let mut selected: Option<ModelManifest> = None;
    for row in rows {
        let candidate: ModelManifest = serde_json::from_str(&row?)?;
        if (capability == "chat" && !local_chat_model(&candidate))
            || candidate.memory_bytes == 0
            || candidate.memory_bytes > memory_budget_bytes
            || !candidate
                .capabilities
                .iter()
                .any(|entry| entry == capability)
        {
            continue;
        }
        if selected
            .as_ref()
            .is_none_or(|model| candidate.memory_bytes < model.memory_bytes)
        {
            selected = Some(candidate);
        }
    }
    selected.ok_or_else(|| {
        CoreError::new(
            "no_matching_model",
            "No registered model matches the capability and memory budget",
        )
    })
}

fn local_chat_model(model: &ModelManifest) -> bool {
    if model.provider != "lm_studio" {
        return false;
    }
    let Some(endpoint) = model.endpoint.strip_prefix("http://") else {
        return false;
    };
    let address = endpoint.strip_suffix("/v1").unwrap_or(endpoint);
    address
        .strip_prefix("127.0.0.1:")
        .or_else(|| address.strip_prefix("[::1]:"))
        .and_then(|port| port.parse::<u16>().ok())
        .is_some_and(|port| port != 0)
}

pub(crate) fn model_get(tx: &Transaction<'_>, id: &str) -> CoreResult<Value> {
    bounded(id, "model_id", 128)?;
    let manifest: Option<String> = tx
        .query_row("SELECT manifest FROM models WHERE id=?1", [id], |r| {
            r.get(0)
        })
        .optional()?;
    let manifest = manifest.ok_or_else(|| CoreError::new("not_found", "Model not found"))?;
    Ok(json!({"model":serde_json::from_str::<Value>(&manifest)?,"operational":false}))
}

fn inspect_skill_package(package: &crate::contracts::SkillPackage) -> CoreResult<Value> {
    let skill = &package.manifest;
    validate_skill(skill)?;
    bounded(&package.license, "skill_license", 128)?;
    if let Some(source) = &package.source_url {
        let url =
            url::Url::parse(source).map_err(|_| CoreError::invalid("Invalid Skill source URL"))?;
        let policy =
            crate::browser_policy::NavigationPolicy::new(&url.origin().ascii_serialization())
                .map_err(|_| CoreError::invalid("Invalid Skill source origin"))?;
        policy
            .destination(source)
            .map_err(|_| CoreError::invalid("Invalid Skill source URL"))?;
    }
    if !skill.tools.is_empty() || !skill.permissions.is_empty() {
        return Err(CoreError::invalid(
            "Imported guidance must declare no tools or permissions",
        ));
    }
    Ok(json!({"package":package,"inspected_digest":store::digest(package)?}))
}

pub(crate) fn skill_inspect(
    tx: &Transaction<'_>,
    package: &crate::contracts::SkillPackage,
) -> CoreResult<Value> {
    let result = inspect_skill_package(package)?;
    store::event(
        tx,
        "skill_package_inspected",
        json!({
            "scope": package.manifest.scope,
            "inspected_digest": result["inspected_digest"],
        }),
    )?;
    Ok(result)
}

pub(crate) fn skill_install(
    tx: &Transaction<'_>,
    package: &crate::contracts::SkillPackage,
    inspected_digest: &str,
) -> CoreResult<Value> {
    let inspection = inspect_skill_package(package)?;
    if inspection["inspected_digest"].as_str() != Some(inspected_digest) {
        return Err(CoreError::new(
            "contract_conflict",
            "Skill package differs from inspection",
        ));
    }
    let reviewed: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM events WHERE kind='skill_package_inspected'
         AND json_extract(payload,'$.scope')=?1
         AND json_extract(payload,'$.inspected_digest')=?2)",
        params![package.manifest.scope, inspected_digest],
        |row| row.get(0),
    )?;
    if !reviewed {
        return Err(CoreError::new(
            "contract_conflict",
            "Skill package inspection was not recorded",
        ));
    }
    let registered = skill_register(tx, &package.manifest)?;
    store::event(
        tx,
        "skill_package_installed",
        json!({
            "scope":package.manifest.scope,"skill_id":package.manifest.id,
            "version":package.manifest.version,"license":package.license,
            "inspected_digest":inspected_digest,"source_url":package.source_url
        }),
    )?;
    Ok(registered)
}

pub(crate) fn guidance_only(
    tx: &Transaction<'_>,
    pin: &crate::contracts::SkillPin,
) -> CoreResult<bool> {
    Ok(tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM events WHERE kind IN ('skill_package_installed','skill_guidance_inherited')
         AND json_extract(payload,'$.scope')=?1 AND json_extract(payload,'$.skill_id')=?2
         AND json_extract(payload,'$.version')=?3)",
        params![pin.scope, pin.id, pin.version],
        |row| row.get(0),
    )?)
}

fn validate_skill(skill: &SkillManifest) -> CoreResult<()> {
    bounded(&skill.id, "skill_id", 128)?;
    bounded(&skill.version, "skill_version", 64)?;
    scope(&skill.scope)?;
    bounded(&skill.provenance, "skill_provenance", 2048)?;
    bounded(&skill.instructions, "skill_instructions", 32_768)?;
    if skill.tools.len() > 64 || skill.permissions.len() > 64 {
        return Err(CoreError::invalid("Skill declarations exceed limits"));
    }
    for tool in &skill.tools {
        bounded(tool, "skill_tool", 128)?;
    }
    for permission in &skill.permissions {
        bounded(permission, "skill_permission", 128)?;
    }
    Ok(())
}

pub(crate) fn skill_register(tx: &Transaction<'_>, skill: &SkillManifest) -> CoreResult<Value> {
    validate_skill(skill)?;
    insert_skill(tx, skill)
}

fn insert_skill(tx: &Transaction<'_>, skill: &SkillManifest) -> CoreResult<Value> {
    let exists: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM skills WHERE scope=?1 AND id=?2 AND version=?3)",
        params![skill.scope, skill.id, skill.version],
        |r| r.get(0),
    )?;
    if exists {
        return Err(CoreError::new(
            "already_exists",
            "Skill version is immutable",
        ));
    }
    let digest = store::digest(skill)?;
    tx.execute(
        "INSERT INTO skills(id,version,scope,manifest,digest) VALUES(?1,?2,?3,?4,?5)",
        params![
            skill.id,
            skill.version,
            skill.scope,
            serde_json::to_string(skill)?,
            digest
        ],
    )?;
    store::event(
        tx,
        "skill_registered",
        json!({"skill_id":skill.id,"version":skill.version,"scope":skill.scope,"digest":digest}),
    )?;
    Ok(json!({"skill":skill,"digest":digest,"operational":false}))
}

pub(crate) fn skill_revise(
    tx: &Transaction<'_>,
    parent: &crate::contracts::SkillPin,
    version: &str,
    instructions: &str,
    rationale: &str,
) -> CoreResult<Value> {
    bounded(rationale, "skill_revision_rationale", 2048)?;
    let record = skill_get(tx, &parent.scope, &parent.id, &parent.version)?;
    if record["digest"].as_str() != Some(parent.digest.as_str()) {
        return Err(CoreError::new(
            "contract_conflict",
            "Parent Skill digest differs",
        ));
    }
    let mut revision: SkillManifest = serde_json::from_value(record["skill"].clone())?;
    if version == revision.version || instructions == revision.instructions {
        return Err(CoreError::invalid(
            "Skill revision requires a new version and changed instructions",
        ));
    }
    let occupied: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM skills WHERE scope=?1 AND id=?2 AND version=?3)",
        params![revision.scope, revision.id, version],
        |row| row.get(0),
    )?;
    if occupied {
        return Err(CoreError::new(
            "already_exists",
            "Skill version is immutable",
        ));
    }
    let shared_prefix_bytes = revision
        .instructions
        .chars()
        .zip(instructions.chars())
        .take_while(|(before, after)| before == after)
        .map(|(character, _)| character.len_utf8())
        .sum::<usize>();
    let shared_suffix_bytes = revision.instructions[shared_prefix_bytes..]
        .chars()
        .rev()
        .zip(instructions[shared_prefix_bytes..].chars().rev())
        .take_while(|(before, after)| before == after)
        .map(|(character, _)| character.len_utf8())
        .sum::<usize>();
    let instruction_change = json!({
        "before_digest": store::digest(&revision.instructions)?,
        "after_digest": store::digest(&instructions)?,
        "start_byte": shared_prefix_bytes,
        "end_byte": revision.instructions.len() - shared_suffix_bytes,
        "replacement_end_byte": instructions.len() - shared_suffix_bytes,
    });
    revision.version = version.to_owned();
    revision.instructions = instructions.to_owned();
    validate_skill(&revision)?;
    let digest = store::digest(&revision)?;
    let pin = json!({
        "scope":revision.scope,"id":revision.id,"version":revision.version,"digest":digest
    });
    let proposal_cursor = store::event(
        tx,
        "skill_revision_proposed",
        json!({
            "scope":revision.scope,"parent":parent,"revision":pin,"rationale":rationale,
            "instructions":revision.instructions,"instruction_change":instruction_change
        }),
    )?;
    Ok(
        json!({"parent":parent,"revision":pin,"rationale":rationale,"candidate":revision,"proposal_cursor":proposal_cursor,"instruction_change":instruction_change}),
    )
}

pub(crate) fn skill_proposal(tx: &Transaction<'_>, proposal_cursor: u64) -> CoreResult<Value> {
    let cursor = i64::try_from(proposal_cursor)
        .map_err(|_| CoreError::invalid("Invalid Skill proposal cursor"))?;
    let proposal: String = tx
        .query_row(
            "SELECT payload FROM events WHERE cursor=?1 AND kind='skill_revision_proposed'",
            [cursor],
            |row| row.get(0),
        )
        .optional()?
        .ok_or_else(|| CoreError::new("not_found", "Skill proposal not found"))?;
    Ok(serde_json::from_str(&proposal)?)
}

pub(crate) fn check_benchmark_expectation(
    tx: &Transaction<'_>,
    proposal_cursor: u64,
    prompt_digest: &str,
    expected_digest: &str,
) -> CoreResult<()> {
    let stored: Option<String> = tx
        .query_row(
            "SELECT json_extract(payload,'$.expected_digest') FROM events
         WHERE kind='skill_benchmark_case_started'
           AND json_extract(payload,'$.proposal_cursor')=?1
           AND json_extract(payload,'$.prompt_digest')=?2
           AND json_type(payload,'$.expected_digest')='text'
         ORDER BY cursor LIMIT 1",
            params![proposal_cursor as i64, prompt_digest],
            |row| row.get(0),
        )
        .optional()?;
    if stored
        .as_deref()
        .is_some_and(|stored| stored != expected_digest)
    {
        return Err(CoreError::new(
            "contract_conflict",
            "Benchmark expectation is already fixed for this prompt",
        ));
    }
    Ok(())
}

pub(crate) fn skill_benchmark_receipt(
    tx: &Transaction<'_>,
    proposal_cursor: u64,
) -> CoreResult<Value> {
    skill_proposal(tx, proposal_cursor)?;
    let (cursor, payload): (i64, String) = tx
        .query_row(
            "SELECT cursor,payload FROM events WHERE kind='skill_benchmark_reviewed'
         AND json_extract(payload,'$.proposal_cursor')=?1 ORDER BY cursor DESC LIMIT 1",
            [proposal_cursor as i64],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?
        .ok_or_else(|| CoreError::new("not_found", "Benchmark review not found"))?;
    Ok(json!({"cursor":cursor,"receipt":serde_json::from_str::<Value>(&payload)?}))
}

/// The owner reviews the exact evaluated instructions before they can cross
/// project boundaries. Only the guidance and aggregate scores enter the
/// reusable manifest, never project manifests, prompts, job IDs or provenance.
pub(crate) fn skill_global_promote(
    tx: &Transaction<'_>,
    proposal_cursor: u64,
    reviewed_instructions_digest: &str,
) -> CoreResult<Value> {
    let proposal = skill_proposal(tx, proposal_cursor)?;
    let pin: crate::contracts::SkillPin = serde_json::from_value(proposal["revision"].clone())?;
    if skill_active(tx, &pin.scope, &pin.id)? != proposal["revision"] {
        return Err(CoreError::new(
            "contract_conflict",
            "Skill revision is not active",
        ));
    }
    let receipt = skill_benchmark_receipt(tx, proposal_cursor)?;
    let receipt = &receipt["receipt"];
    let external = receipt["passing_evaluation_scopes"]
        .as_array()
        .into_iter()
        .flatten()
        .filter_map(Value::as_str)
        .filter(|scope| *scope != pin.scope)
        .count();
    if external < 2 || receipt["review"]["regressions"] != 0 {
        return Err(CoreError::new(
            "contract_conflict",
            "Global Skill requires passing evaluations in two other projects without regression",
        ));
    }
    let instructions: String = serde_json::from_value(proposal["instructions"].clone())?;
    if reviewed_instructions_digest != store::digest(&instructions)? {
        return Err(CoreError::new(
            "contract_conflict",
            "Reviewed instructions differ",
        ));
    }
    let skill = SkillManifest {
        id: pin.id.clone(),
        version: pin.version.clone(),
        scope: "global".into(),
        provenance: "Generalized guidance reviewed by the owner".into(),
        instructions,
        tools: vec![],
        permissions: vec![],
    };
    let result = insert_skill(tx, &skill)?;
    store::event(
        tx,
        "skill_global_promoted",
        json!({
            "skill_id":skill.id,"version":skill.version,"digest":result["digest"],
            "projects_passed":external,"source_pin":pin,"review": {
                "baseline":receipt["review"]["baseline"],
                "candidate":receipt["review"]["candidate"],
                "regressions":receipt["review"]["regressions"]
            }
        }),
    )?;
    Ok(result)
}

pub(crate) fn skill_benchmark_review(
    tx: &Transaction<'_>,
    proposal_cursor: u64,
    cases: &[crate::contracts::SkillBenchmarkPair],
) -> CoreResult<Value> {
    if cases.is_empty() || cases.len() > 32 {
        return Err(CoreError::invalid("Skill benchmark requires 1 to 32 pairs"));
    }
    let proposal = skill_proposal(tx, proposal_cursor)?;
    let mut used = std::collections::HashSet::new();
    let mut prompts = std::collections::HashSet::new();
    let mut evidence = Vec::new();
    let mut earliest_case = i64::MAX;
    let mut benchmark_configuration = None;
    let mut evaluation_scopes = std::collections::BTreeSet::new();
    let mut scoped_results = std::collections::BTreeMap::new();
    let mut review = crate::contracts::SkillReviewEvidence {
        reviewer: "core_exact_match".into(),
        benchmark: store::digest(&cases)?,
        baseline: 0,
        candidate: 0,
        regressions: 0,
        approved: true,
    };
    for case in cases {
        bounded(&case.expected, "benchmark_expected_output", 4096)?;
        let expected_digest = store::digest(&case.expected.trim())?;
        let mut pair = Vec::new();
        for (id, candidate) in [(&case.baseline_job, false), (&case.candidate_job, true)] {
            bounded(id, "benchmark_job_id", 128)?;
            if !used.insert(id) {
                return Err(CoreError::invalid("Benchmark jobs must be unique"));
            }
            let (cursor, event): (i64, String) = tx
                .query_row(
                    "SELECT cursor,payload FROM events WHERE kind='skill_benchmark_case_started'
                 AND json_extract(payload,'$.job_id')=?1",
                    [id],
                    |row| Ok((row.get(0)?, row.get(1)?)),
                )
                .optional()?
                .ok_or_else(|| CoreError::new("not_found", "Benchmark case not found"))?;
            let already_reviewed: bool = tx.query_row(
                "SELECT EXISTS(SELECT 1 FROM events, json_each(events.payload,'$.cases') AS pair
                 WHERE kind='skill_benchmark_reviewed'
                   AND json_extract(events.payload,'$.proposal_cursor')=?1
                   AND (json_extract(pair.value,'$.baseline_job')=?2
                     OR json_extract(pair.value,'$.candidate_job')=?2))",
                params![proposal_cursor as i64, id],
                |row| row.get(0),
            )?;
            if already_reviewed {
                return Err(CoreError::new(
                    "already_exists",
                    "Benchmark job already reviewed",
                ));
            }
            earliest_case = earliest_case.min(cursor);
            let event: Value = serde_json::from_str(&event)?;
            let job = crate::conversation::get(tx, id)?;
            if event["proposal_cursor"] != proposal_cursor
                || event["candidate"] != candidate
                || job["status"] != "succeeded"
            {
                return Err(CoreError::new(
                    "contract_conflict",
                    "Benchmark job does not match a completed case",
                ));
            }
            if event["expected_digest"] != expected_digest {
                return Err(CoreError::new(
                    "contract_conflict",
                    "Expected output differs from the benchmark case commitment",
                ));
            }
            let correct = job["content"]
                .as_str()
                .is_some_and(|answer| answer.trim() == case.expected.trim());
            let configuration = if let Some(digest) = event["model_config_digest"].as_str() {
                digest.to_owned()
            } else {
                let endpoint: String =
                    tx.query_row("SELECT endpoint FROM ai_jobs WHERE id=?1", [id], |row| {
                        row.get(0)
                    })?;
                bounded(&endpoint, "benchmark_endpoint", 1024)?;
                let generation: crate::contracts::Generation =
                    serde_json::from_value(job["generation"].clone())?;
                store::digest(&(&job["model_id"], endpoint, generation))?
            };
            pair.push((event, configuration, correct));
        }
        let [
            (baseline_event, baseline_config, baseline),
            (candidate_event, candidate_config, candidate),
        ] = pair.as_slice()
        else {
            unreachable!("two benchmark jobs")
        };
        let prompt = baseline_event["prompt_digest"]
            .as_str()
            .ok_or_else(|| CoreError::invalid("Benchmark case has no prompt digest"))?;
        if candidate_config != baseline_config
            || benchmark_configuration.get_or_insert_with(|| baseline_config.clone())
                != baseline_config
            || candidate_event["evaluation_scope"] != baseline_event["evaluation_scope"]
            || candidate_event["prompt_digest"] != prompt
            || !prompts.insert(prompt.to_owned())
        {
            return Err(CoreError::new(
                "contract_conflict",
                "Benchmark cases require one model configuration and a unique matching prompt per pair",
            ));
        }
        if let Some(scope) = baseline_event["evaluation_scope"].as_str() {
            evaluation_scopes.insert(scope.to_owned());
            scoped_results
                .entry(scope.to_owned())
                .and_modify(|passed| *passed &= *candidate)
                .or_insert(*candidate);
        }
        review.baseline += u32::from(*baseline);
        review.candidate += u32::from(*candidate);
        review.regressions += u32::from(*baseline && !*candidate);
        evidence.push(
            json!({"baseline_job":case.baseline_job,"candidate_job":case.candidate_job,
            "baseline_passed":baseline,"candidate_passed":candidate,"prompt_digest":prompt,
            "evaluation_scope":baseline_event["evaluation_scope"]}),
        );
    }
    let revision: crate::contracts::SkillPin =
        serde_json::from_value(proposal["revision"].clone())?;
    let mut result = if skill_active(tx, &revision.scope, &revision.id)? == proposal["revision"] {
        let activation_cursor: i64 = tx.query_row(
            "SELECT MAX(cursor) FROM events WHERE kind='skill_active_changed'
             AND json_extract(payload,'$.scope')=?1 AND json_extract(payload,'$.skill_id')=?2",
            params![revision.scope, revision.id],
            |row| row.get(0),
        )?;
        if earliest_case <= activation_cursor {
            return Err(CoreError::new(
                "contract_conflict",
                "Active Skill review requires fresh benchmark results after activation",
            ));
        }
        let restored = if review.regressions > 0 {
            skill_rollback(tx, &revision)?
        } else {
            Value::Null
        };
        json!({
            "proposal_cursor":proposal_cursor,"scope":revision.scope,
            "revision":revision,"review":review,"promoted":false,"restored":restored
        })
    } else {
        apply_skill_review(tx, proposal_cursor, &review)?
    };
    result["cases"] = json!(evidence);
    result["model_config_digest"] = json!(benchmark_configuration);
    result["evaluation_scopes"] = json!(evaluation_scopes);
    let passing_scopes: Vec<_> = scoped_results
        .into_iter()
        .filter_map(|(scope, passed)| passed.then_some(scope))
        .collect();
    result["passing_evaluation_scopes"] = json!(passing_scopes);
    store::event(tx, "skill_benchmark_reviewed", result.clone())?;
    Ok(result)
}

pub(crate) fn skill_review(
    tx: &Transaction<'_>,
    proposal_cursor: u64,
    review: &crate::contracts::SkillReviewEvidence,
) -> CoreResult<Value> {
    skill_proposal(tx, proposal_cursor)?;
    if review.reviewer == "core_exact_match" {
        return Err(CoreError::invalid("Reserved benchmark reviewer"));
    }
    let has_benchmark: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM events WHERE kind='skill_benchmark_case_started'
         AND json_extract(payload,'$.proposal_cursor')=?1)",
        [proposal_cursor as i64],
        |row| row.get(0),
    )?;
    if has_benchmark {
        return Err(CoreError::new(
            "contract_conflict",
            "Review must use recorded benchmark results",
        ));
    }
    bounded(&review.reviewer, "skill_reviewer", 128)?;
    bounded(&review.benchmark, "skill_benchmark", 2048)?;
    let result = json!({"proposal_cursor":proposal_cursor,"review":review,"promoted":false});
    store::event(tx, "skill_revision_owner_reviewed", result.clone())?;
    Ok(result)
}

fn apply_skill_review(
    tx: &Transaction<'_>,
    proposal_cursor: u64,
    review: &crate::contracts::SkillReviewEvidence,
) -> CoreResult<Value> {
    let proposal = skill_proposal(tx, proposal_cursor)?;
    bounded(&review.reviewer, "skill_reviewer", 128)?;
    bounded(&review.benchmark, "skill_benchmark", 2048)?;
    let cursor = proposal_cursor as i64;
    let resolved: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM events WHERE kind='skill_revision_reviewed' AND json_extract(payload,'$.proposal_cursor')=?1)",
        [cursor],
        |row| row.get(0),
    )?;
    if resolved {
        return Err(CoreError::new(
            "already_exists",
            "Skill proposal already reviewed",
        ));
    }
    let promoted = review.approved && review.candidate > review.baseline && review.regressions == 0;
    if promoted {
        let parent: crate::contracts::SkillPin =
            serde_json::from_value(proposal["parent"].clone())?;
        let pin: crate::contracts::SkillPin = serde_json::from_value(proposal["revision"].clone())?;
        let record = skill_get(tx, &parent.scope, &parent.id, &parent.version)?;
        if record["digest"].as_str() != Some(&parent.digest) {
            return Err(CoreError::new(
                "contract_conflict",
                "Parent Skill digest differs",
            ));
        }
        let mut skill: SkillManifest = serde_json::from_value(record["skill"].clone())?;
        skill.version = pin.version;
        skill.instructions = serde_json::from_value(proposal["instructions"].clone())?;
        if store::digest(&skill)? != pin.digest {
            return Err(CoreError::new(
                "contract_conflict",
                "Reviewed Skill digest differs",
            ));
        }
        let active = skill_active(tx, &parent.scope, &parent.id)?;
        if !active.is_null() && active != proposal["parent"] {
            return Err(CoreError::new(
                "contract_conflict",
                "Skill proposal is based on an inactive version",
            ));
        }
        skill_register(tx, &skill)?;
        if guidance_only(tx, &parent)? {
            store::event(
                tx,
                "skill_guidance_inherited",
                json!({
                    "scope":skill.scope,"skill_id":skill.id,"version":skill.version,
                    "parent_inspection":record["inspection"]
                }),
            )?;
        }
        store::event(
            tx,
            "skill_active_changed",
            json!({
                "scope":parent.scope,"skill_id":parent.id,
                "active":proposal["revision"],"previous":parent
            }),
        )?;
    }
    let result = json!({
        "proposal_cursor":proposal_cursor,"scope":proposal["scope"],"revision":proposal["revision"],
        "review":review,"promoted":promoted
    });
    store::event(tx, "skill_revision_reviewed", result.clone())?;
    Ok(result)
}

fn skill_activation(tx: &Transaction<'_>, scope: &str, id: &str) -> CoreResult<Value> {
    crate::contracts::scope(scope)?;
    bounded(id, "skill_id", 128)?;
    let event: Option<String> = tx
        .query_row(
            "SELECT payload FROM events WHERE kind='skill_active_changed'
         AND json_extract(payload,'$.scope')=?1 AND json_extract(payload,'$.skill_id')=?2
         ORDER BY cursor DESC LIMIT 1",
            params![scope, id],
            |row| row.get(0),
        )
        .optional()?;
    Ok(event
        .map(|raw| serde_json::from_str(&raw))
        .transpose()?
        .unwrap_or(Value::Null))
}

pub(crate) fn skill_active(tx: &Transaction<'_>, scope: &str, id: &str) -> CoreResult<Value> {
    Ok(skill_activation(tx, scope, id)?["active"].clone())
}

pub(crate) fn skill_rollback(
    tx: &Transaction<'_>,
    current: &crate::contracts::SkillPin,
) -> CoreResult<Value> {
    let event = skill_activation(tx, &current.scope, &current.id)?;
    if event["active"] != serde_json::to_value(current)? {
        return Err(CoreError::new(
            "contract_conflict",
            "Active Skill differs from rollback request",
        ));
    }
    let previous = event["previous"].clone();
    if previous.is_null() {
        return Err(CoreError::new(
            "not_found",
            "No prior Skill version for rollback",
        ));
    }
    let previous_activation: Option<String> = tx
        .query_row(
            "SELECT payload FROM events WHERE kind='skill_active_changed'
         AND json_extract(payload,'$.scope')=?1 AND json_extract(payload,'$.skill_id')=?2
         AND json_extract(payload,'$.active.digest')=?3 ORDER BY cursor DESC LIMIT 1",
            params![current.scope, current.id, previous["digest"].as_str()],
            |row| row.get(0),
        )
        .optional()?;
    let ancestor = previous_activation
        .map(|raw| serde_json::from_str::<Value>(&raw))
        .transpose()?
        .map(|activation| activation["previous"].clone())
        .unwrap_or(Value::Null);
    store::event(
        tx,
        "skill_active_changed",
        json!({
            "scope":current.scope,"skill_id":current.id,"active":previous,"previous":ancestor,
            "rolled_back":current
        }),
    )?;
    Ok(previous)
}

pub(crate) fn skill_available(
    tx: &Transaction<'_>,
    project: &str,
    pin: &crate::contracts::SkillPin,
) -> CoreResult<bool> {
    if pin.scope == project {
        return Ok(true);
    }
    if pin.scope != "global" {
        return Ok(false);
    }
    let source: Option<String> = tx.query_row(
        "SELECT json_extract(payload,'$.source_pin') FROM events WHERE kind='skill_global_promoted'
         AND json_extract(payload,'$.digest')=?1",
        [&pin.digest],
        |row| row.get(0),
    ).optional()?;
    let Some(source) = source else {
        return Ok(false);
    };
    let source: crate::contracts::SkillPin = serde_json::from_str(&source)?;
    Ok(skill_active(tx, &source.scope, &source.id)? == serde_json::to_value(source)?)
}

pub(crate) fn planning_skill_candidates(
    tx: &Transaction<'_>,
    project_scope: &str,
) -> CoreResult<Vec<Value>> {
    scope(project_scope)?;
    let mut query = tx.prepare(
        "WITH activations AS (
            SELECT json_extract(payload,'$.skill_id') AS id,
                   json_extract(payload,'$.active.digest') AS digest,
                   ROW_NUMBER() OVER (
                      PARTITION BY json_extract(payload,'$.skill_id') ORDER BY cursor DESC
                   ) AS position
            FROM events WHERE kind='skill_active_changed'
              AND json_extract(payload,'$.scope')=?1
         ), ranked AS (
            SELECT s.id,s.version,s.digest,s.rowid,
                   COALESCE(a.digest=s.digest,0) AS active,
                   ROW_NUMBER() OVER (
                      PARTITION BY s.id ORDER BY COALESCE(a.digest=s.digest,0) DESC,s.rowid DESC
                   ) AS position
            FROM skills s LEFT JOIN activations a ON a.id=s.id AND a.position=1
            WHERE s.scope=?1
         )
         SELECT id,version,digest,active FROM ranked WHERE position=1
         ORDER BY active DESC,rowid DESC LIMIT 8",
    )?;
    let rows = query.query_map([project_scope], |row| {
        Ok(json!({
            "id":row.get::<_, String>(0)?,"version":row.get::<_, String>(1)?,
            "digest":row.get::<_, String>(2)?,"scope":project_scope,
            "active":row.get::<_, bool>(3)?
        }))
    })?;
    let mut candidates = rows.collect::<Result<Vec<_>, _>>()?;
    let mut global = tx
        .prepare("SELECT id,version,digest FROM skills WHERE scope='global' ORDER BY rowid DESC")?;
    let pins = global.query_map([], |row| {
        Ok(crate::contracts::SkillPin {
            scope: "global".into(),
            id: row.get(0)?,
            version: row.get(1)?,
            digest: row.get(2)?,
        })
    })?;
    let mut global_ids = std::collections::HashSet::new();
    for pin in pins {
        if candidates.len() >= 12 {
            break;
        }
        let pin = pin?;
        if skill_available(tx, project_scope, &pin)? && global_ids.insert(pin.id.clone()) {
            candidates.push(json!({
                "scope":pin.scope,"id":pin.id,"version":pin.version,"digest":pin.digest,"active":true
            }));
        }
    }
    Ok(candidates)
}

pub(crate) fn skills_list(
    tx: &Transaction<'_>,
    project_scope: &str,
    after: u64,
    limit: u32,
) -> CoreResult<Value> {
    scope(project_scope)?;
    page(after, limit)?;
    let mut q = tx.prepare("SELECT rowid,id,version,digest FROM skills WHERE scope=?1 AND rowid>?2 ORDER BY rowid LIMIT ?3")?;
    let rows = q.query_map(
        params![project_scope, after as i64, (limit + 1) as i64],
        |r| {
            Ok((
                r.get::<_, i64>(0)?,
                r.get::<_, String>(1)?,
                r.get::<_, String>(2)?,
                r.get::<_, String>(3)?,
            ))
        },
    )?;
    let mut skills = Vec::new();
    let mut bytes = 0;
    let mut next_cursor = after;
    let mut has_more = false;
    for row in rows {
        let (cursor, id, version, digest) = row?;
        if skills.len() >= limit as usize {
            has_more = true;
            break;
        }
        let item = json!({"id":id,"version":version,"scope":project_scope,"digest":digest,"operational":false});
        let size = serde_json::to_vec(&item)?.len();
        if bytes + size > 220_000 {
            if skills.is_empty() {
                return Err(CoreError::new(
                    "response_too_large",
                    "A Skill summary exceeds page byte budget",
                ));
            }
            has_more = true;
            break;
        }
        bytes += size;
        next_cursor = cursor as u64;
        skills.push(item);
    }
    Ok(json!({"scope":project_scope,"skills":skills,"next_cursor":next_cursor,"has_more":has_more}))
}

pub(crate) fn skill_get(
    tx: &Transaction<'_>,
    project_scope: &str,
    id: &str,
    version: &str,
) -> CoreResult<Value> {
    if project_scope != "global" {
        scope(project_scope)?;
    }
    bounded(id, "skill_id", 128)?;
    bounded(version, "skill_version", 64)?;
    let row: Option<(String, String)> = tx
        .query_row(
            "SELECT manifest,digest FROM skills WHERE scope=?1 AND id=?2 AND version=?3",
            params![project_scope, id, version],
            |r| Ok((r.get(0)?, r.get(1)?)),
        )
        .optional()?;
    let (manifest, digest) =
        row.ok_or_else(|| CoreError::new("not_found", "Skill version not found"))?;
    let mut result = json!({"skill":serde_json::from_str::<Value>(&manifest)?,"digest":digest,"operational":false});
    let inspection: Option<String> = tx
        .query_row(
            "SELECT payload FROM events WHERE kind IN ('skill_package_installed','skill_guidance_inherited')
         AND json_extract(payload,'$.scope')=?1 AND json_extract(payload,'$.skill_id')=?2
         AND json_extract(payload,'$.version')=?3 ORDER BY cursor DESC LIMIT 1",
            params![project_scope, id, version],
            |row| row.get(0),
        )
        .optional()?;
    if let Some(inspection) = inspection {
        let event: Value = serde_json::from_str(&inspection)?;
        if let Some(parent) = event
            .get("parent_inspection")
            .filter(|value| value.is_object())
        {
            result["inspection"] = parent.clone();
        } else if event.get("inspected_digest").is_some() {
            result["inspection"] = json!({
                "license":event["license"],"source_url":event["source_url"],
                "inspected_digest":event["inspected_digest"]
            });
        }
    }
    Ok(result)
}

pub(crate) fn capabilities() -> Value {
    json!({"capabilities":[
        {"id":"core_storage","status":"operational"},
        {"id":"chats","status":"operational"},
        {"id":"canonical_memory","status":"operational"},
        {"id":"mission_contracts","status":"operational"},
        {"id":"model_registry","status":"operational"},
        {"id":"skill_registry","status":"operational"},
        {"id":"skill_guidance","status":"implemented","requires":"explicit exact project Skill pin and an available conversation model; no discovery, evolution or execution authority"},
        {"id":"inference","status":"implemented","requires":"registered lm_studio chat model and configured Python executable"},
        {"id":"voice_turn","status":"implemented","requires":"detected pt-BR or en-US transcript, registered local model and saved chat"},
        {"id":"voice_translator","status":"implemented","requires":"registered local model and reliable pt-BR/en-US turn detection"},
        {"id":"workspace_tools","status":"implemented","requires":"Windows and an approved exact mission"},
        {"id":"project_check","status":"implemented","requires":"Windows LPAC, configured native toolchain and approved sealed mission"},
        {"id":"mission_candidate_review","status":"implemented","requires":"approved sealed mission, configured native checks and local models"},
        {"id":"mission_execution","status":"implemented","requires":"Windows, approved sealed mission, supported Git or non-Git Workspace, configured local models and native checks"}
    ]})
}
