use crate::{
    contracts::{CoreError, CoreResult, ModelManifest, bounded},
    conversation::{self, Launch},
    mission_run, registry, store,
};
use rusqlite::{OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize};
use serde_json::{Value, json};
use sha2::{Digest, Sha256};
use std::{collections::BTreeMap, io::Read, path::Path};

const DEFAULT_BUDGET: u64 = (1_u64 << 53) - 1;

#[derive(Clone, Copy, Default, Deserialize, PartialEq, Serialize)]
#[serde(rename_all = "SCREAMING_SNAKE_CASE")]
enum ResourcePolicy {
    #[default]
    Responsive,
    Economical,
}

#[derive(Clone, Copy, Default, Deserialize, Serialize)]
#[serde(rename_all = "snake_case")]
enum ModelMode {
    #[default]
    Automatic,
    Manual,
}

#[derive(Deserialize, Serialize)]
struct Settings {
    resource_policy: ResourcePolicy,
    model_mode: ModelMode,
    memory_budget_bytes: u64,
    assignments: BTreeMap<String, String>,
    #[serde(default)]
    purpose_modes: BTreeMap<String, ModelMode>,
}

impl Default for Settings {
    fn default() -> Self {
        Self {
            resource_policy: ResourcePolicy::Responsive,
            model_mode: ModelMode::Automatic,
            memory_budget_bytes: DEFAULT_BUDGET,
            assignments: BTreeMap::new(),
            purpose_modes: BTreeMap::new(),
        }
    }
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct SettingsPatch {
    resource_policy: Option<ResourcePolicy>,
    model_mode: Option<ModelMode>,
    memory_budget_bytes: Option<u64>,
    assignments: Option<BTreeMap<String, Option<String>>>,
    purpose_modes: Option<BTreeMap<String, Option<ModelMode>>>,
}

pub(crate) fn migrate(tx: &Transaction<'_>) -> CoreResult<()> {
    tx.execute_batch(
        "CREATE TABLE IF NOT EXISTS orchestration_profiles(
            id TEXT PRIMARY KEY, settings TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS orchestration_transitions(
            id TEXT PRIMARY KEY, profile TEXT NOT NULL, mission_id TEXT NOT NULL,
            contract_digest TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('requested','preparing','active','failed','ended')),
            reason TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS orchestration_live_profile
            ON orchestration_transitions(profile)
            WHERE status IN ('requested','preparing','active');
        CREATE UNIQUE INDEX IF NOT EXISTS orchestration_live_mission
            ON orchestration_transitions(mission_id)
            WHERE status IN ('requested','preparing','active');
        CREATE TABLE IF NOT EXISTS model_reservations(
            id INTEGER PRIMARY KEY, job_id TEXT NOT NULL, profile TEXT NOT NULL, model_id TEXT NOT NULL,
            purpose TEXT NOT NULL, declared_model_bytes INTEGER NOT NULL,
            estimated_peak_bytes INTEGER NOT NULL, host_capacity_bytes INTEGER,
            memory_budget_bytes INTEGER NOT NULL, resource_policy TEXT NOT NULL,
            status TEXT NOT NULL CHECK(status IN ('requested','acquired','released','reconciliation_required')),
            reason TEXT, acquired_cursor INTEGER, endpoint_hash TEXT NOT NULL, lease_hash TEXT
        );
        CREATE UNIQUE INDEX IF NOT EXISTS orchestration_model_slot
            ON model_reservations((1)) WHERE status IN ('requested','acquired');
        CREATE INDEX IF NOT EXISTS orchestration_reservations_job ON model_reservations(job_id);",
    )?;
    Ok(())
}

fn settings(tx: &Transaction<'_>, profile: &str) -> CoreResult<Settings> {
    bounded(profile, "profile", 128)?;
    let raw: Option<String> = tx
        .query_row(
            "SELECT settings FROM orchestration_profiles WHERE id=?1",
            [profile],
            |row| row.get(0),
        )
        .optional()?;
    raw.map(|value| serde_json::from_str(&value).map_err(Into::into))
        .unwrap_or_else(|| Ok(Settings::default()))
}

fn transition(tx: &Transaction<'_>, profile: &str) -> CoreResult<Option<Value>> {
    Ok(tx
        .query_row(
            "SELECT id,mission_id,contract_digest,status,reason FROM orchestration_transitions
         WHERE profile=?1 ORDER BY rowid DESC LIMIT 1",
            [profile],
            |row| {
                Ok(json!({
                    "id":row.get::<_,String>(0)?,"mission_id":row.get::<_,String>(1)?,
                    "contract_digest":row.get::<_,String>(2)?,"status":row.get::<_,String>(3)?,
                    "reason":row.get::<_,Option<String>>(4)?,
                    "requested_regime":"SWARM"
                }))
            },
        )
        .optional()?)
}

pub(crate) fn settings_get(tx: &Transaction<'_>, profile: &str) -> CoreResult<Value> {
    let mut value = serde_json::to_value(settings(tx, profile)?)?;
    let transition = transition(tx, profile)?;
    let active = transition
        .as_ref()
        .is_some_and(|entry| entry["status"] == "active");
    value["profile"] = json!(profile);
    value["execution_regime"] = json!(if active { "SWARM" } else { "NORMAL" });
    value["transition"] = json!(transition);
    Ok(value)
}

pub(crate) fn settings_put(
    tx: &Transaction<'_>,
    profile: &str,
    patch: &Value,
) -> CoreResult<Value> {
    let patch: SettingsPatch = serde_json::from_value(patch.clone())
        .map_err(|_| CoreError::invalid("Invalid orchestration preferences"))?;
    let mut current = settings(tx, profile)?;
    if let Some(policy) = patch.resource_policy {
        current.resource_policy = policy;
    }
    if let Some(mode) = patch.model_mode {
        current.model_mode = mode;
    }
    if let Some(budget) = patch.memory_budget_bytes {
        check_budget(budget)?;
        current.memory_budget_bytes = budget;
    }
    if let Some(modes) = patch.purpose_modes {
        for (purpose, mode) in modes {
            validate_purpose(&purpose)?;
            if let Some(mode) = mode {
                current.purpose_modes.insert(purpose, mode);
            } else {
                current.purpose_modes.remove(&purpose);
            }
        }
    }
    if let Some(assignments) = patch.assignments {
        for (purpose, model_id) in assignments {
            validate_purpose(&purpose)?;
            if let Some(model_id) = model_id {
                let model = conversation::registered_model(tx, &model_id)?;
                ensure_local(&model)?;
                current.assignments.insert(purpose, model_id);
            } else {
                current.assignments.remove(&purpose);
            }
        }
    }
    tx.execute(
        "INSERT INTO orchestration_profiles(id,settings) VALUES(?1,?2)
         ON CONFLICT(id) DO UPDATE SET settings=excluded.settings",
        params![profile, serde_json::to_string(&current)?],
    )?;
    store::event(
        tx,
        "orchestration_preferences_changed",
        json!({"profile":profile}),
    )?;
    settings_get(tx, profile)
}

fn change_transition(
    tx: &Transaction<'_>,
    id: &str,
    status: &str,
    reason: Option<&str>,
) -> CoreResult<()> {
    tx.execute(
        "UPDATE orchestration_transitions SET status=?2,reason=?3 WHERE id=?1",
        params![id, status, reason],
    )?;
    store::event(
        tx,
        "execution_regime_transition",
        json!({
            "transition_id":id,"status":status,"reason":reason
        }),
    )?;
    Ok(())
}

pub(crate) fn transition_request(
    tx: &Transaction<'_>,
    profile: &str,
    request_id: &str,
    regime: &str,
    mission_id: Option<&str>,
) -> CoreResult<Value> {
    bounded(profile, "profile", 128)?;
    let existing = transition(tx, profile)?;
    if regime == "NORMAL" {
        if let Some(entry) = existing {
            match entry["status"].as_str() {
                Some("active") => {
                    return Err(CoreError::new(
                        "swarm_active",
                        "Finish or cancel the active mission",
                    ));
                }
                Some("requested" | "preparing") => {
                    let id = entry["id"].as_str().unwrap_or_default();
                    change_transition(tx, id, "ended", Some("withdrawn"))?;
                }
                _ => {}
            }
        }
        return settings_get(tx, profile);
    }
    if regime != "SWARM" {
        return Err(CoreError::invalid("Unknown execution regime"));
    }
    if existing.as_ref().is_some_and(|entry| {
        matches!(
            entry["status"].as_str(),
            Some("requested" | "preparing" | "active")
        )
    }) {
        return Err(CoreError::new(
            "transition_pending",
            "The profile already has a Swarm transition",
        ));
    }
    let mission_id = mission_id.ok_or_else(|| CoreError::invalid("Swarm requires a mission"))?;
    bounded(mission_id, "mission_id", 128)?;
    let digest: String = tx
        .query_row(
            "SELECT contract_digest FROM missions WHERE id=?1 AND state IN ('proposed','approved')
         AND json_type(contract,'$.execution')='object'
         AND NOT EXISTS(SELECT 1 FROM mission_runs WHERE mission_id=?1)",
            [mission_id],
            |row| row.get(0),
        )
        .optional()?
        .ok_or_else(|| {
            CoreError::new(
                "swarm_mission_unavailable",
                "Swarm requires an unstarted executable mission",
            )
        })?;
    let reserved: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM orchestration_transitions
                       WHERE mission_id=?1 AND status IN ('requested','preparing','active'))",
        [mission_id],
        |row| row.get(0),
    )?;
    if reserved {
        return Err(CoreError::new(
            "transition_pending",
            "The mission already has a Swarm transition",
        ));
    }
    tx.execute(
        "INSERT INTO orchestration_transitions(id,profile,mission_id,contract_digest,status)
         VALUES(?1,?2,?3,?4,'requested')",
        params![request_id, profile, mission_id, digest],
    )?;
    store::event(
        tx,
        "execution_regime_transition",
        json!({
            "transition_id":request_id,"status":"requested","profile":profile,
            "mission_id":mission_id,"contract_digest":digest
        }),
    )?;
    settings_get(tx, profile)
}

pub(crate) fn transition_confirm(
    tx: &Transaction<'_>,
    profile: &str,
    transition_id: &str,
) -> CoreResult<Value> {
    bounded(profile, "profile", 128)?;
    let (mission, digest, status): (String, String, String) = tx
        .query_row(
            "SELECT mission_id,contract_digest,status FROM orchestration_transitions
         WHERE id=?1 AND profile=?2",
            params![transition_id, profile],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .optional()?
        .ok_or_else(|| {
            CoreError::new("transition_unavailable", "Swarm transition is unavailable")
        })?;
    if status == "preparing" || status == "active" {
        return settings_get(tx, profile);
    }
    if status != "requested" {
        return Err(CoreError::new(
            "transition_unavailable",
            "Swarm transition has already ended",
        ));
    }
    let approved: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM missions WHERE id=?1 AND contract_digest=?2 AND state='approved')",
        params![mission, digest],
        |row| row.get(0),
    )?;
    if !approved || mission_run::swarm_consent(tx, &mission, &digest)?.is_none() {
        return Err(CoreError::new(
            "swarm_consent_required",
            "Approve this mission and its Swarm roles first",
        ));
    }
    change_transition(tx, transition_id, "preparing", None)?;
    settings_get(tx, profile)
}

/// Older clients express the owner's confirmation in MissionApprove.swarm itself.
pub(crate) fn legacy_swarm_confirmation(
    tx: &Transaction<'_>,
    request_id: &str,
    mission: &str,
) -> CoreResult<()> {
    let current = settings_get(tx, "default")?;
    let transition = &current["transition"];
    if transition["mission_id"] == mission
        && matches!(
            transition["status"].as_str(),
            Some("requested" | "preparing" | "active")
        )
    {
        return Ok(());
    }
    let id = format!("swarm-{}", &store::digest(&request_id)?[..48]);
    transition_request(tx, "default", &id, "SWARM", Some(mission))?;
    transition_confirm(tx, "default", &id)?;
    Ok(())
}

pub(crate) fn mission_started(tx: &Transaction<'_>, mission_id: &str) -> CoreResult<()> {
    let parent: Option<String> = tx.query_row(
        "SELECT p.mission_id FROM task_graph_planner_roots p JOIN task_graph_missions c ON c.graph_id=p.graph_id WHERE c.mission_id=?1",[mission_id],|row|row.get(0)).optional()?;
    if let Some(parent) = parent {
        mission_started(tx, &parent)?;
    }
    let pending: Option<(String, String)> = tx
        .query_row(
            "SELECT id,status FROM orchestration_transitions WHERE mission_id=?1
         AND status IN ('requested','preparing')",
            [mission_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?;
    if let Some((id, status)) = pending {
        if status != "preparing" {
            return Err(CoreError::new(
                "swarm_consent_required",
                "Confirm the Swarm transition before starting",
            ));
        }
        let approved: bool = tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM orchestration_transitions t JOIN missions m ON m.id=t.mission_id
             WHERE t.id=?1 AND m.state='approved' AND t.contract_digest=m.contract_digest)",
            [&id],
            |row| row.get(0),
        )?;
        if !approved {
            return Err(CoreError::new(
                "swarm_consent_required",
                "Swarm approval no longer matches the mission",
            ));
        }
        change_transition(tx, &id, "active", None)?;
    }
    Ok(())
}

pub(crate) fn mission_finished(tx: &Transaction<'_>, mission_id: &str) -> CoreResult<()> {
    let Some((id, mission_status)) = tx
        .query_row(
            "SELECT t.id, COALESCE(i.status,r.status,m.state) FROM orchestration_transitions t
         JOIN missions m ON m.id=t.mission_id LEFT JOIN mission_runs r ON r.mission_id=m.id
         LEFT JOIN mission_integrations i ON i.mission_id=m.id
         WHERE t.mission_id=?1 AND t.status IN ('requested','preparing','active')",
            [mission_id],
            |row| Ok((row.get::<_, String>(0)?, row.get::<_, String>(1)?)),
        )
        .optional()?
    else {
        return Ok(());
    };
    let graph = crate::task_graph::planner_root(tx, mission_id)?;
    let mission_status = graph
        .as_ref()
        .and_then(|graph| graph["state"].as_str())
        .unwrap_or(&mission_status);
    let terminal = match mission_status {
        "integrated" | "cancelled" | "revoked" | "rolled_back" => "ended",
        "failed" | "interrupted" | "recovery_required" | "rejected" => "failed",
        _ => return Ok(()),
    };
    change_transition(tx, &id, terminal, Some(&mission_status))
}

fn validate_purpose(purpose: &str) -> CoreResult<()> {
    if !matches!(
        purpose,
        "conversation" | "planning" | "review" | "translation"
    ) {
        return Err(CoreError::invalid("Unknown model purpose"));
    }
    Ok(())
}

fn check_budget(budget: u64) -> CoreResult<()> {
    if budget == 0 || budget > DEFAULT_BUDGET {
        return Err(CoreError::invalid(
            "Model memory budget must be a positive integer in the supported range",
        ));
    }
    Ok(())
}

fn ensure_local(model: &ModelManifest) -> CoreResult<()> {
    let local = model
        .endpoint
        .strip_prefix("http://")
        .is_some_and(|endpoint| {
            let address = endpoint.strip_suffix("/v1").unwrap_or(endpoint);
            address
                .strip_prefix("127.0.0.1:")
                .or_else(|| address.strip_prefix("[::1]:"))
                .and_then(|port| port.parse::<u16>().ok())
                .is_some_and(|port| port != 0)
        });
    if !local {
        return Err(CoreError::new(
            "invalid_endpoint",
            "Model provider must use a local endpoint",
        ));
    }
    Ok(())
}

pub(crate) fn model_choice(
    tx: &Transaction<'_>,
    profile: &str,
    purpose: &str,
    explicit: Option<&str>,
    budget: Option<u64>,
) -> CoreResult<(String, Option<u64>)> {
    let settings = settings(tx, profile)?;
    if let Some(id) = explicit.filter(|id| !id.is_empty()) {
        let model = conversation::registered_model(tx, id)?;
        ensure_local(&model)?;
        return Ok((id.into(), None));
    }
    let mode = settings
        .purpose_modes
        .get(purpose)
        .copied()
        .unwrap_or(settings.model_mode);
    if matches!(mode, ModelMode::Manual) {
        let id = settings.assignments.get(purpose).ok_or_else(|| {
            CoreError::new(
                "model_assignment_required",
                "Assign a model for this purpose or select automatic routing",
            )
        })?;
        let model = conversation::registered_model(tx, id)?;
        ensure_local(&model)?;
        return Ok((id.clone(), None));
    }
    let budget = budget
        .unwrap_or(settings.memory_budget_bytes)
        .min(settings.memory_budget_bytes)
        .min(host_capacity().unwrap_or(DEFAULT_BUDGET));
    check_budget(budget)?;
    if settings.resource_policy == ResourcePolicy::Responsive {
        let recent: Option<String> = tx
            .query_row(
                "SELECT r.model_id FROM model_reservations r JOIN models m ON m.id=r.model_id
             WHERE r.profile=?1 AND r.purpose=?2 AND r.status='released' AND r.reason='completed'
               AND r.declared_model_bytes > 0 AND r.declared_model_bytes <= ?3
             ORDER BY r.acquired_cursor DESC LIMIT 1",
                params![profile, purpose, budget as i64],
                |row| row.get(0),
            )
            .optional()?;
        if let Some(id) = recent {
            let model = conversation::registered_model(tx, &id)?;
            if ensure_local(&model).is_ok()
                && estimate_peak(model.memory_bytes).is_some_and(|peak| peak <= budget)
            {
                return Ok((id, None));
            }
        }
    }
    let declared_budget = budget - budget.div_ceil(5);
    if declared_budget == 0 {
        return Err(CoreError::new(
            "no_matching_model",
            "No model fits the estimated memory budget",
        ));
    }
    let model = registry::resolve_chat_model(tx, "", Some(declared_budget))?;
    Ok((model.into_owned(), None))
}

fn estimate_peak(declared: u64) -> Option<u64> {
    // Allow for runtime allocations above the catalog's declared model memory.
    // The estimate is separate from both the declaration and host capacity.
    declared.checked_add(declared.div_ceil(4))
}

#[cfg(target_os = "windows")]
fn host_capacity() -> Option<u64> {
    #[repr(C)]
    struct MemoryStatus {
        length: u32,
        load: u32,
        total_physical: u64,
        available_physical: u64,
        total_page_file: u64,
        available_page_file: u64,
        total_virtual: u64,
        available_virtual: u64,
        available_extended_virtual: u64,
    }
    #[link(name = "kernel32")]
    unsafe extern "system" {
        fn GlobalMemoryStatusEx(status: *mut MemoryStatus) -> i32;
    }
    // The Win32 API initializes the structure after the caller provides its size.
    let mut status: MemoryStatus = unsafe { std::mem::zeroed() };
    status.length = std::mem::size_of::<MemoryStatus>() as u32;
    (unsafe { GlobalMemoryStatusEx(&mut status) } != 0).then_some(status.total_physical)
}

#[cfg(target_os = "linux")]
fn host_capacity() -> Option<u64> {
    std::fs::read_to_string("/proc/meminfo")
        .ok()?
        .lines()
        .find_map(|line| line.strip_prefix("MemTotal:"))?
        .split_ascii_whitespace()
        .next()?
        .parse::<u64>()
        .ok()?
        .checked_mul(1024)
}

#[cfg(not(any(target_os = "windows", target_os = "linux")))]
fn host_capacity() -> Option<u64> {
    None
}

pub(crate) fn reserve(tx: &Transaction<'_>, profile: &str, launch: &Launch) -> CoreResult<()> {
    let settings = settings(tx, profile)?;
    let occupied: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM model_reservations WHERE status IN ('requested','acquired'))",
        [],
        |row| row.get(0),
    )?;
    if occupied {
        return Err(CoreError::new(
            "model_capacity_busy",
            "Another job already owns the model slot",
        ));
    }
    crate::operational_store::admit(tx, launch)?;
    let purpose = match launch.purpose {
        conversation::Purpose::Conversation => "conversation",
        conversation::Purpose::MissionPlan | conversation::Purpose::MissionGenerate => "planning",
        conversation::Purpose::MissionReview => "review",
        conversation::Purpose::Translation => "translation",
        conversation::Purpose::Learning => "learning",
    };
    let model = conversation::registered_model(tx, &launch.model_id)?;
    let declared = model.memory_bytes;
    let peak = estimate_peak(declared)
        .ok_or_else(|| CoreError::invalid("Model memory estimate overflow"))?;
    let host = host_capacity().filter(|capacity| *capacity <= DEFAULT_BUDGET);
    let budget = settings
        .memory_budget_bytes
        .min(host.unwrap_or(DEFAULT_BUDGET));
    if peak > budget || (declared == 0 && settings.memory_budget_bytes != DEFAULT_BUDGET) {
        return Err(CoreError::new(
            "model_capacity_exceeded",
            "The model estimate exceeds the memory budget or is unavailable",
        ));
    }
    tx.execute(
        "INSERT INTO model_reservations(job_id,profile,model_id,purpose,declared_model_bytes,
          estimated_peak_bytes,host_capacity_bytes,memory_budget_bytes,resource_policy,status,endpoint_hash)
         VALUES(?1,?2,?3,?4,?5,?6,?7,?8,?9,'requested',?10)",
        params![
            launch.id,
            profile,
            launch.model_id,
            purpose,
            declared as i64,
            peak as i64,
            host.map(|bytes| bytes as i64),
            budget as i64,
            if settings.resource_policy == ResourcePolicy::Responsive {
                "RESPONSIVE"
            } else {
                "ECONOMICAL"
            },
            endpoint_hash(&model.endpoint)
        ],
    )?;
    store::event(
        tx,
        "model_reservation_requested",
        json!({
            "job_id":launch.id,"profile":profile,"model_id":launch.model_id,
            "declared_model_bytes":declared,"estimated_peak_bytes":peak,"host_capacity_bytes":host,
            "memory_budget_bytes":budget
        }),
    )?;
    let cursor = store::event(
        tx,
        "model_reservation_acquired",
        json!({"job_id":launch.id}),
    )?;
    tx.execute(
        "UPDATE model_reservations SET status='acquired',acquired_cursor=?2,lease_hash=?3 WHERE job_id=?1 AND status='requested'",
        params![launch.id, cursor as i64, hash(&format!("{}:{cursor}", launch.id))],
    )?;
    crate::operational_store::begin(tx, launch, &format!("{}:{cursor}", launch.id))?;
    Ok(())
}

pub(crate) fn release(tx: &Transaction<'_>, job_id: &str, reason: &str) -> CoreResult<()> {
    let uncertain = matches!(
        reason,
        "worker_crashed"
            | "worker_interrupted"
            | "model_release_uncertain"
            | "worker_protocol"
            | "model_ownership_unavailable"
            | "provider_timeout"
            | "provider_unavailable"
            | "provider_malformed"
    );
    update_reservation_status(tx, job_id, reason, uncertain)
}

fn update_reservation_status(
    tx: &Transaction<'_>,
    job_id: &str,
    reason: &str,
    uncertain: bool,
) -> CoreResult<()> {
    let status = if uncertain {
        "reconciliation_required"
    } else {
        "released"
    };
    if tx.execute(
        "UPDATE model_reservations SET status=?2,reason=?3
         WHERE job_id=?1 AND status IN ('requested','acquired')",
        params![job_id, status, reason],
    )? > 0
    {
        store::event(
            tx,
            "model_reservation_finished",
            json!({
                "job_id":job_id,"status":status,"reason":reason
            }),
        )?;
    }
    Ok(())
}

pub(crate) fn finish(
    tx: &Transaction<'_>,
    ownership_dir: &Path,
    job_id: &str,
    reason: &str,
) -> CoreResult<()> {
    let owners: Option<(String, String)> = tx
        .query_row(
            "SELECT lease_hash,endpoint_hash FROM model_reservations
         WHERE job_id=?1 AND status='acquired'",
            [job_id],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?;
    let Some((lease, endpoint)) = owners else {
        return Ok(());
    };
    let uncertain = matches!(
        reason,
        "model_release_uncertain" | "model_ownership_unavailable"
    ) || provider_lease_present(ownership_dir, &endpoint, &lease).unwrap_or(true);
    update_reservation_status(tx, job_id, reason, uncertain)?;
    acknowledge(tx, ownership_dir)
}

pub(crate) fn recover(tx: &Transaction<'_>) -> CoreResult<()> {
    crate::operational_store::recover(tx)?;
    let jobs = tx
        .prepare("SELECT job_id FROM model_reservations WHERE status IN ('requested','acquired')")?
        .query_map([], |row| row.get::<_, String>(0))?
        .collect::<Result<Vec<_>, _>>()?;
    for job in jobs {
        release(tx, &job, "worker_interrupted")?;
    }
    let missions = tx.prepare(
        "SELECT mission_id FROM orchestration_transitions WHERE status IN ('requested','preparing','active')"
    )?.query_map([], |row| row.get::<_,String>(0))?.collect::<Result<Vec<_>,_>>()?;
    for mission in missions {
        mission_finished(tx, &mission)?;
    }
    Ok(())
}
fn hash(value: &str) -> String {
    Sha256::digest(value.as_bytes())
        .iter()
        .map(|byte| format!("{byte:02x}"))
        .collect()
}

fn endpoint_hash(endpoint: &str) -> String {
    hash(&format!(
        "{}/v1",
        endpoint.strip_suffix("/v1").unwrap_or(endpoint)
    ))
}

pub(crate) fn lease_token(tx: &Transaction<'_>, job_id: &str) -> CoreResult<String> {
    let cursor: i64 = tx
        .query_row(
            "SELECT acquired_cursor FROM model_reservations WHERE job_id=?1 AND status='acquired'",
            [job_id],
            |row| row.get(0),
        )
        .optional()?
        .ok_or_else(|| {
            CoreError::new("model_ownership_unavailable", "No active model reservation")
        })?;
    Ok(format!("{job_id}:{cursor}"))
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ReleaseProof {
    lease: String,
    endpoint: String,
    instance: String,
    kind: String,
}

fn is_link(metadata: &std::fs::Metadata) -> bool {
    #[cfg(windows)]
    {
        use std::os::windows::fs::MetadataExt;
        const FILE_ATTRIBUTE_REPARSE_POINT: u32 = 0x400;
        metadata.file_attributes() & FILE_ATTRIBUTE_REPARSE_POINT != 0
    }
    #[cfg(not(windows))]
    metadata.file_type().is_symlink()
}

fn read_owned_file(path: &Path) -> std::io::Result<Option<Vec<u8>>> {
    let metadata = match path.symlink_metadata() {
        Ok(metadata) => metadata,
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Ok(None),
        Err(error) => return Err(error),
    };
    if !metadata.file_type().is_file() || is_link(&metadata) {
        return Err(std::io::Error::from(std::io::ErrorKind::InvalidData));
    }
    let mut bytes = Vec::new();
    std::fs::File::open(path)?
        .take(4097)
        .read_to_end(&mut bytes)?;
    if bytes.len() > 4096 {
        return Err(std::io::Error::from(std::io::ErrorKind::InvalidData));
    }
    Ok(Some(bytes))
}

fn provider_lease_present(ownership_dir: &Path, endpoint: &str, lease: &str) -> Option<bool> {
    if !ownership_dir.is_absolute() || !is_digest(endpoint) || !is_digest(lease) {
        return None;
    }
    match ownership_dir.symlink_metadata() {
        Ok(metadata) if metadata.file_type().is_dir() && !is_link(&metadata) => {}
        Err(error) if error.kind() == std::io::ErrorKind::NotFound => return Some(false),
        _ => return None,
    }
    let Some(bytes) = read_owned_file(&ownership_dir.join(format!("{endpoint}.json"))).ok()? else {
        return Some(false);
    };
    let journal: Value = serde_json::from_slice(&bytes).ok()?;
    let owner = journal["lease"].as_str()?;
    let model = journal["model"].as_str()?;
    let kind = journal["kind"].as_str()?;
    let phase = journal["phase"].as_str()?;
    let instance = journal.get("instance")?;
    if !is_digest(owner)
        || model.is_empty()
        || model.len() > 512
        || !matches!(phase, "pending" | "acquired")
        || journal.as_object()?.len() != 5
    {
        return None;
    }
    if !match kind {
        "cli" => instance
            .as_str()
            .is_some_and(|instance| is_cli_instance(instance, owner)),
        "rest" => {
            (phase == "pending" && instance.is_null())
                || instance
                    .as_str()
                    .is_some_and(|instance| !instance.is_empty() && instance.len() <= 512)
        }
        _ => false,
    } {
        return None;
    }
    Some(owner == lease)
}

fn is_digest(digest: &str) -> bool {
    digest.len() == 64 && digest.bytes().all(|byte| byte.is_ascii_hexdigit())
}

fn is_cli_instance(instance: &str, lease: &str) -> bool {
    instance
        .strip_prefix(&format!("synapse-{}-", &lease[..12]))
        .is_some_and(|nonce| {
            nonce.len() == 32 && nonce.bytes().all(|byte| byte.is_ascii_hexdigit())
        })
}

fn release_proof(path: &Path) -> Option<ReleaseProof> {
    serde_json::from_slice(&read_owned_file(path).ok()??).ok()
}

pub(crate) fn acknowledge(tx: &Transaction<'_>, ownership_dir: &Path) -> CoreResult<()> {
    if !ownership_dir.is_absolute()
        || !ownership_dir
            .symlink_metadata()
            .is_ok_and(|metadata| metadata.file_type().is_dir() && !is_link(&metadata))
    {
        return Ok(());
    }
    let pending = tx
        .prepare(
            "SELECT id,job_id,lease_hash,endpoint_hash FROM model_reservations
         WHERE status='reconciliation_required' AND lease_hash IS NOT NULL ORDER BY id",
        )?
        .query_map([], |row| {
            Ok((
                row.get::<_, i64>(0)?,
                row.get::<_, String>(1)?,
                row.get::<_, String>(2)?,
                row.get::<_, String>(3)?,
            ))
        })?
        .collect::<Result<Vec<_>, _>>()?;
    for (id, job, lease, endpoint) in pending {
        if !is_digest(&lease) {
            continue;
        }
        let Some(proof) = release_proof(&ownership_dir.join(format!("released-{lease}.json")))
        else {
            continue;
        };
        if proof.lease != lease
            || proof.endpoint != endpoint
            || proof.instance.is_empty()
            || proof.instance.len() > 512
        {
            continue;
        }
        match proof.kind.as_str() {
            "cli" if is_cli_instance(&proof.instance, &lease) => {}
            "rest" => {}
            _ => continue,
        }
        tx.execute(
            "UPDATE model_reservations SET status='released',reason='provider_release_confirmed'
             WHERE id=?1 AND status='reconciliation_required'",
            [id],
        )?;
        store::event(tx, "model_reservation_reconciled", json!({"job_id":job}))?;
    }
    Ok(())
}

pub(crate) fn handle(
    tx: &Transaction<'_>,
    request_id: &str,
    action: &str,
    payload: &Value,
) -> CoreResult<Value> {
    let mut data = payload
        .as_object()
        .cloned()
        .ok_or_else(|| CoreError::invalid("Orchestration payload must be an object"))?;
    let profile = match data.remove("profile") {
        None => "default".to_owned(),
        Some(Value::String(profile)) => profile,
        _ => return Err(CoreError::invalid("Invalid profile")),
    };
    match action {
        "settings_get" if data.is_empty() => settings_get(tx, &profile),
        "settings_put" => settings_put(tx, &profile, &Value::Object(data)),
        "transition_request" => {
            let regime = data
                .remove("regime")
                .and_then(|value| value.as_str().map(str::to_owned))
                .ok_or_else(|| CoreError::invalid("Missing execution regime"))?;
            let mission = match data.remove("mission_id") {
                None => None,
                Some(Value::String(mission)) => Some(mission),
                _ => return Err(CoreError::invalid("Invalid mission ID")),
            };
            if !data.is_empty() {
                return Err(CoreError::invalid("Unexpected transition fields"));
            }
            transition_request(tx, &profile, request_id, &regime, mission.as_deref())
        }
        "transition_confirm" => {
            let transition = data
                .remove("transition_id")
                .and_then(|value| value.as_str().map(str::to_owned))
                .ok_or_else(|| CoreError::invalid("Missing transition ID"))?;
            if !data.is_empty() {
                return Err(CoreError::invalid("Unexpected transition fields"));
            }
            transition_confirm(tx, &profile, &transition)
        }
        _ => Err(CoreError::invalid(
            "Unknown orchestration action or unexpected fields",
        )),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::contracts::Generation;

    fn register(tx: &Transaction<'_>, id: &str, memory_bytes: u64) {
        registry::model_register(
            tx,
            &ModelManifest {
                id: id.to_owned(),
                provider: "lm_studio".into(),
                endpoint: "http://127.0.0.1:1234".into(),
                capabilities: vec!["chat".into()],
                memory_bytes,
                generation: None,
            },
        )
        .unwrap();
    }

    fn launch(job_id: &str, model_id: &str) -> Launch {
        Launch {
            id: job_id.into(),
            model_id: model_id.into(),
            endpoint: "http://127.0.0.1:1234".into(),
            messages: vec![],
            generation: Generation::default(),
            purpose: conversation::Purpose::Conversation,
        }
    }

    #[test]
    fn profiles_and_policy_change_automatic_selection_without_overriding_explicit_choice() {
        let state = tempfile::tempdir().unwrap();
        let mut db = store::Store::open(state.path(), state.path()).unwrap();
        let tx = db.transaction().unwrap();
        register(&tx, "small", 400);
        register(&tx, "large", 800);
        settings_put(
            &tx,
            "default",
            &json!({
                "model_mode":"manual", "memory_budget_bytes":1000,
                "assignments":{"conversation":"large","review":"large"}, "purpose_modes":{"review":"automatic"}
            }),
        )
        .unwrap();
        assert_eq!(
            model_choice(&tx, "default", "conversation", None, None)
                .unwrap()
                .0,
            "large"
        );
        assert_eq!(
            model_choice(&tx, "default", "conversation", Some("small"), Some(1))
                .unwrap()
                .0,
            "small"
        );
        assert_eq!(
            model_choice(&tx, "default", "review", None, None)
                .unwrap()
                .0,
            "small"
        );
        assert_eq!(
            model_choice(&tx, "default", "conversation", None, Some(1))
                .unwrap()
                .0,
            "large"
        );
        reserve(&tx, "default", &launch("first", "large")).unwrap();
        release(&tx, "first", "completed").unwrap();
        settings_put(&tx, "default", &json!({"model_mode":"automatic"})).unwrap();
        assert_eq!(
            model_choice(&tx, "default", "conversation", None, None)
                .unwrap()
                .0,
            "large"
        );
        assert_eq!(
            model_choice(&tx, "other", "conversation", None, None)
                .unwrap()
                .0,
            "small"
        );
        settings_put(&tx, "default", &json!({"resource_policy":"ECONOMICAL"})).unwrap();
        assert_eq!(
            model_choice(&tx, "default", "conversation", None, None)
                .unwrap()
                .0,
            "small"
        );
        tx.commit().unwrap();
        drop(db);

        let mut db = store::Store::open(state.path(), state.path()).unwrap();
        let tx = db.transaction().unwrap();
        let settings = settings_get(&tx, "default").unwrap();
        assert_eq!(settings["resource_policy"], "ECONOMICAL");
        assert_eq!(settings["assignments"]["conversation"], "large");
        assert_eq!(settings["execution_regime"], "NORMAL");
    }

    #[test]
    fn reservation_serializes_profiles_and_records_uncertain_owner_on_restart() {
        let state = tempfile::tempdir().unwrap();
        let mut db = store::Store::open(state.path(), state.path()).unwrap();
        let tx = db.transaction().unwrap();
        register(&tx, "large", 800);
        settings_put(&tx, "limited", &json!({"memory_budget_bytes":900})).unwrap();
        assert_eq!(
            reserve(&tx, "limited", &launch("fail", "large"))
                .unwrap_err()
                .code,
            "model_capacity_exceeded"
        );
        reserve(&tx, "default", &launch("owner", "large")).unwrap();
        assert_eq!(
            reserve(&tx, "other", &launch("contender", "large"))
                .unwrap_err()
                .code,
            "model_capacity_busy"
        );
        tx.commit().unwrap();
        assert!(store::Store::open(state.path(), state.path()).is_err());
        drop(db);

        let mut db = store::Store::open(state.path(), state.path()).unwrap();
        let tx = db.transaction().unwrap();
        let status: String = tx
            .query_row(
                "SELECT status FROM model_reservations WHERE job_id='owner'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(status, "reconciliation_required");
        reserve(&tx, "other", &launch("next", "large")).unwrap();
        release(&tx, "next", "cancelled").unwrap();
        release(&tx, "next", "completed").unwrap();
        let reason: String = tx
            .query_row(
                "SELECT reason FROM model_reservations WHERE job_id='next'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(reason, "cancelled");
        reserve(&tx, "other", &launch("next", "large")).unwrap();
        release(&tx, "next", "completed").unwrap();
        let attempts: i64 = tx
            .query_row(
                "SELECT COUNT(*) FROM model_reservations WHERE job_id='next' AND status='released'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(attempts, 2);
    }

    #[test]
    fn finish_keeps_a_joined_cancelled_worker_uncertain_when_its_journal_survives() {
        let state = tempfile::tempdir().unwrap();
        let ownership = state.path().join("model-ownership");
        std::fs::create_dir(&ownership).unwrap();
        let mut db = store::Store::open(state.path(), state.path()).unwrap();
        let tx = db.transaction().unwrap();
        register(&tx, "model", 1000);
        let cancelled = launch("cancelled", "model");
        let endpoint = endpoint_hash(&cancelled.endpoint);
        let journal = ownership.join(format!("{endpoint}.json"));
        reserve(&tx, "default", &cancelled).unwrap();
        let lease = hash(&lease_token(&tx, &cancelled.id).unwrap());
        std::fs::write(
            &journal,
            json!({
                "lease":lease,"model":"model","kind":"rest","instance":null,"phase":"pending"
            })
            .to_string(),
        )
        .unwrap();
        finish(&tx, &ownership, &cancelled.id, "cancelled").unwrap();
        let status = |job: &str| -> String {
            tx.query_row(
                "SELECT status FROM model_reservations WHERE job_id=?1",
                [job],
                |row| row.get(0),
            )
            .unwrap()
        };
        assert_eq!(status("cancelled"), "reconciliation_required");
        let borrowed = launch("borrowed", "model");
        reserve(&tx, "default", &borrowed).unwrap();
        finish(&tx, &ownership, &borrowed.id, "model_capacity_busy").unwrap();
        assert_eq!(status("borrowed"), "released");
        std::fs::write(&journal, b"{").unwrap();
        let malformed = launch("malformed", "model");
        reserve(&tx, "default", &malformed).unwrap();
        finish(&tx, &ownership, &malformed.id, "provider_timeout").unwrap();
        assert_eq!(status("malformed"), "reconciliation_required");
    }

    #[test]
    fn release_acknowledgement_is_bound_to_the_attempt_and_provider() {
        let state = tempfile::tempdir().unwrap();
        let ownership = state.path().join("model-ownership");
        std::fs::create_dir(&ownership).unwrap();
        let mut db = store::Store::open(state.path(), state.path()).unwrap();
        let tx = db.transaction().unwrap();
        register(&tx, "model", 1000);
        let first = launch("job", "model");
        reserve(&tx, "default", &first).unwrap();
        let token = lease_token(&tx, &first.id).unwrap();
        let lease = hash(&token);
        release(&tx, &first.id, "worker_interrupted").unwrap();
        let path = ownership.join(format!("released-{lease}.json"));
        let mut proof = json!({
            "lease":lease, "endpoint":"unrelated", "kind":"cli",
            "instance":format!("synapse-{}-{}", &lease[..12], "a".repeat(32)),
        });
        let status = |hash: &str| -> String {
            tx.query_row(
                "SELECT status FROM model_reservations WHERE lease_hash=?1",
                [hash],
                |row| row.get(0),
            )
            .unwrap()
        };
        std::fs::write(&path, proof.to_string()).unwrap();
        acknowledge(&tx, &ownership).unwrap();
        assert_eq!(status(&lease), "reconciliation_required");
        proof["endpoint"] = json!(endpoint_hash(&first.endpoint));
        std::fs::write(&path, proof.to_string()).unwrap();
        reserve(&tx, "default", &first).unwrap();
        let retry = lease_token(&tx, &first.id).unwrap();
        assert_ne!(token, retry);
        release(&tx, &first.id, "worker_interrupted").unwrap();
        acknowledge(&tx, &ownership).unwrap();
        assert_eq!(status(&lease), "released");
        assert_eq!(status(&hash(&retry)), "reconciliation_required");
    }

    #[test]
    fn swarm_requires_digest_bound_consent_under_both_resource_policies() {
        let state = tempfile::tempdir().unwrap();
        let mut db = store::Store::open(state.path(), state.path()).unwrap();
        let tx = db.transaction().unwrap();
        for (profile, policy) in [("personal", "RESPONSIVE"), ("work", "ECONOMICAL")] {
            tx.execute(
                "INSERT INTO missions VALUES(?1,'{\"execution\":{}}','sealed','approved',NULL)",
                [profile],
            )
            .unwrap();
            settings_put(&tx, profile, &json!({"resource_policy":policy})).unwrap();
            let pending =
                transition_request(&tx, profile, profile, "SWARM", Some(profile)).unwrap();
            assert_eq!(pending["execution_regime"], "NORMAL");
            assert_eq!(pending["resource_policy"], policy);
            assert_eq!(pending["transition"]["status"], "requested");
            assert_eq!(
                transition_confirm(&tx, profile, profile).unwrap_err().code,
                "swarm_consent_required"
            );
            assert_eq!(
                mission_started(&tx, profile).unwrap_err().code,
                "swarm_consent_required"
            );
            store::event(
                &tx,
                "swarm_consent_recorded",
                json!({
                    "mission_id":profile,"contract_digest":"old","source":"requested"
                }),
            )
            .unwrap();
            assert_eq!(
                transition_confirm(&tx, profile, profile).unwrap_err().code,
                "swarm_consent_required"
            );
            store::event(
                &tx,
                "swarm_consent_recorded",
                json!({
                    "mission_id":profile,"contract_digest":"sealed","source":"requested"
                }),
            )
            .unwrap();
            assert_eq!(
                transition_confirm(&tx, profile, profile).unwrap()["transition"]["status"],
                "preparing"
            );
            mission_started(&tx, profile).unwrap();
            let active = settings_get(&tx, profile).unwrap();
            assert_eq!(active["execution_regime"], "SWARM");
            assert_eq!(active["resource_policy"], policy);
            if profile == "personal" {
                tx.execute(
                    "UPDATE missions SET state='cancelled' WHERE id=?1",
                    [profile],
                )
                .unwrap();
            } else {
                tx.execute("INSERT INTO mission_runs(mission_id,contract_digest,status) VALUES(?1,'sealed','review_ready')",[profile]).unwrap();
                tx.execute(
                    "INSERT INTO mission_integrations(mission_id,status) VALUES(?1,'integrated')",
                    [profile],
                )
                .unwrap();
            }
            mission_finished(&tx, profile).unwrap();
            assert_eq!(
                settings_get(&tx, profile).unwrap()["execution_regime"],
                "NORMAL"
            );
        }
    }
}
