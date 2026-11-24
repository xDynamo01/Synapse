use std::collections::{BTreeMap, BTreeSet};

use rusqlite::{OptionalExtension, Transaction, params};
use serde::{Deserialize, Serialize, de::DeserializeOwned};
use serde_json::{Value, json};

use crate::{
    checks,
    contracts::{CandidateArtifact, CoreError, CoreResult, MissionContract, PlannedTask, bounded},
    mission_run, missions, planner, store,
};

pub(crate) fn migrate(tx: &Transaction<'_>) -> CoreResult<()> {
    tx.execute_batch(
        "CREATE TABLE IF NOT EXISTS task_rfcs(
            id TEXT PRIMARY KEY, scope TEXT NOT NULL, objective TEXT NOT NULL,
            input_id TEXT, chat_id TEXT REFERENCES chats(id), digest TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS task_graphs(
            id TEXT PRIMARY KEY, rfc_id TEXT NOT NULL UNIQUE REFERENCES task_rfcs(id),
            revision INTEGER NOT NULL, state TEXT NOT NULL, digest TEXT NOT NULL, tasks TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS task_graph_missions(
            mission_id TEXT PRIMARY KEY REFERENCES missions(id), graph_id TEXT NOT NULL REFERENCES task_graphs(id),
            task_id TEXT NOT NULL, state TEXT NOT NULL DEFAULT 'pending'
        );
        CREATE TABLE IF NOT EXISTS task_graph_revisions(
            graph_id TEXT NOT NULL REFERENCES task_graphs(id), revision INTEGER NOT NULL,
            digest TEXT NOT NULL, tasks TEXT NOT NULL, approved INTEGER NOT NULL DEFAULT 0,
            PRIMARY KEY(graph_id, revision)
        );
        CREATE TABLE IF NOT EXISTS task_graph_planner_roots(
            mission_id TEXT PRIMARY KEY REFERENCES missions(id),
            graph_id TEXT NOT NULL UNIQUE REFERENCES task_graphs(id)
        );
        CREATE TABLE IF NOT EXISTS task_graph_check_inputs(
            check_id TEXT PRIMARY KEY REFERENCES project_checks(id), digest TEXT NOT NULL
        );",
    )?;
    Ok(())
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RfcInput {
    rfc_id: String,
    scope: String,
    objective: String,
    input_id: Option<String>,
    chat_id: Option<String>,
}

#[derive(Serialize)]
struct Rfc {
    rfc_id: String,
    scope: String,
    objective: String,
    input_id: Option<String>,
    chat_id: Option<String>,
    digest: String,
}

#[derive(Clone, Deserialize, Serialize)]
#[serde(deny_unknown_fields)]
struct TaskInput {
    task_id: String,
    mission_id: String,
    #[serde(default)]
    dependencies: Vec<String>,
    #[serde(default)]
    priority: i32,
}

#[derive(Clone, Serialize, Deserialize)]
struct Task {
    #[serde(flatten)]
    input: TaskInput,
    contract_digest: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct PlanInput {
    graph_id: String,
    rfc_id: String,
    rfc_digest: String,
    tasks: Vec<TaskInput>,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct GraphInput {
    graph_id: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RevisionInput {
    graph_id: String,
    digest: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct ReplanInput {
    graph_id: String,
    digest: String,
    tasks: Vec<TaskInput>,
}

struct Graph {
    id: String,
    rfc_id: String,
    revision: u32,
    state: String,
    digest: String,
    tasks: Vec<Task>,
}

fn parse<T: DeserializeOwned>(payload: &Value) -> CoreResult<T> {
    serde_json::from_value(payload.clone()).map_err(|error| CoreError::invalid(&error.to_string()))
}

fn rfc(tx: &Transaction<'_>, id: &str) -> CoreResult<Rfc> {
    bounded(id, "rfc_id", 128)?;
    tx.query_row(
        "SELECT scope,objective,input_id,chat_id,digest FROM task_rfcs WHERE id=?1",
        [id],
        |row| {
            Ok(Rfc {
                rfc_id: id.to_owned(),
                scope: row.get(0)?,
                objective: row.get(1)?,
                input_id: row.get(2)?,
                chat_id: row.get(3)?,
                digest: row.get(4)?,
            })
        },
    )
    .optional()?
    .ok_or_else(|| CoreError::new("not_found", "Task RFC not found"))
}

fn load(tx: &Transaction<'_>, id: &str) -> CoreResult<Graph> {
    bounded(id, "graph_id", 128)?;
    let row: Option<(String, u32, String, String, String)> = tx
        .query_row(
            "SELECT rfc_id,revision,state,digest,tasks FROM task_graphs WHERE id=?1",
            [id],
            |row| {
                Ok((
                    row.get(0)?,
                    row.get(1)?,
                    row.get(2)?,
                    row.get(3)?,
                    row.get(4)?,
                ))
            },
        )
        .optional()?;
    let (rfc_id, revision, state, digest, tasks) =
        row.ok_or_else(|| CoreError::new("not_found", "Task graph not found"))?;
    Ok(Graph {
        id: id.to_owned(),
        rfc_id,
        revision,
        state,
        digest,
        tasks: serde_json::from_str(&tasks)?,
    })
}

fn mission(tx: &Transaction<'_>, id: &str) -> CoreResult<(MissionContract, String, String)> {
    let (raw, digest, state): (String, String, String) = tx
        .query_row(
            "SELECT contract,contract_digest,state FROM missions WHERE id=?1",
            [id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )
        .optional()?
        .ok_or_else(|| CoreError::new("not_found", "Task mission not found"))?;
    let contract: MissionContract = serde_json::from_str(&raw)?;
    if contract.execution.is_none() || store::digest(&contract)? != digest {
        return Err(CoreError::new(
            "contract_conflict",
            "Task mission must have a sealed execution plan",
        ));
    }
    planner::validate_seal(tx, id, &contract)?;
    Ok((contract, digest, state))
}

fn validate_dag(inputs: &[TaskInput]) -> CoreResult<()> {
    if inputs.is_empty() || inputs.len() > 32 {
        return Err(CoreError::invalid("A graph requires 1 to 32 tasks"));
    }
    let mut pending = BTreeMap::new();
    let mut mission_ids = BTreeSet::new();
    for task in inputs {
        bounded(&task.task_id, "task_id", 128)?;
        bounded(&task.mission_id, "mission_id", 128)?;
        let dependencies: BTreeSet<_> = task.dependencies.iter().map(String::as_str).collect();
        if dependencies.len() != task.dependencies.len()
            || pending
                .insert(task.task_id.as_str(), dependencies)
                .is_some()
            || !mission_ids.insert(task.mission_id.as_str())
        {
            return Err(CoreError::invalid(
                "Task IDs, missions, and dependencies must be unique",
            ));
        }
    }
    if pending
        .values()
        .flatten()
        .any(|id| !pending.contains_key(id))
    {
        return Err(CoreError::invalid("Task dependency not found in plan"));
    }
    while !pending.is_empty() {
        let ready: BTreeSet<_> = pending
            .iter()
            .filter_map(|(id, dependencies)| dependencies.is_empty().then_some(*id))
            .collect();
        if ready.is_empty() {
            return Err(CoreError::invalid("Task dependencies form a cycle"));
        }
        pending.retain(|id, dependencies| {
            dependencies.retain(|dependency| !ready.contains(dependency));
            !ready.contains(id)
        });
    }
    Ok(())
}

fn prepare_tasks(
    tx: &Transaction<'_>,
    graph_id: &str,
    rfc: &Rfc,
    inputs: Vec<TaskInput>,
) -> CoreResult<Vec<Task>> {
    validate_dag(&inputs)?;
    let mut outputs = BTreeSet::new();
    let mut tasks = Vec::with_capacity(inputs.len());
    for input in inputs {
        let (contract, contract_digest, state) = mission(tx, &input.mission_id)?;
        if contract.scope != rfc.scope {
            return Err(CoreError::new(
                "permission_denied",
                "Task mission belongs to another scope",
            ));
        }
        let policy = contract.execution.as_ref().unwrap();
        if policy.checks.is_empty()
            || policy.artifacts.is_empty()
            || policy
                .artifacts
                .iter()
                .any(|artifact| !outputs.insert(artifact.path.to_lowercase()))
        {
            return Err(CoreError::invalid(
                "Each task needs checks and exclusive output paths",
            ));
        }
        let membership: Option<(String, String)> = tx
            .query_row(
                "SELECT graph_id,task_id FROM task_graph_missions WHERE mission_id=?1",
                [&input.mission_id],
                |row| Ok((row.get(0)?, row.get(1)?)),
            )
            .optional()?;
        let belongs = membership
            .as_ref()
            .is_some_and(|(graph, task)| graph == graph_id && task == &input.task_id);
        if membership.is_some() && !belongs {
            return Err(CoreError::new(
                "contract_conflict",
                "Task mission already belongs to another graph or task",
            ));
        }
        if !belongs {
            let used: bool = tx.query_row(
                "SELECT EXISTS(SELECT 1 FROM mission_runs WHERE mission_id=?1)",
                [&input.mission_id],
                |row| row.get(0),
            )?;
            if used || !matches!(state.as_str(), "proposed" | "approved") {
                return Err(CoreError::new(
                    "invalid_transition",
                    "A new task requires an unused sealed mission",
                ));
            }
        }
        tasks.push(Task {
            input,
            contract_digest,
        });
    }
    Ok(tasks)
}

fn persist_plan(tx: &Transaction<'_>, graph: &Graph) -> CoreResult<()> {
    let tasks = serde_json::to_string(&graph.tasks)?;
    tx.execute(
        "INSERT INTO task_graphs(id,rfc_id,revision,state,digest,tasks) VALUES(?1,?2,?3,?4,?5,?6)
         ON CONFLICT(id) DO UPDATE SET revision=excluded.revision,state=excluded.state,
            digest=excluded.digest,tasks=excluded.tasks",
        params![
            graph.id,
            graph.rfc_id,
            graph.revision,
            graph.state,
            graph.digest,
            tasks
        ],
    )?;
    tx.execute(
        "INSERT INTO task_graph_revisions(graph_id,revision,digest,tasks) VALUES(?1,?2,?3,?4)",
        params![graph.id, graph.revision, graph.digest, tasks],
    )?;
    for task in &graph.tasks {
        tx.execute(
            "INSERT INTO task_graph_missions(mission_id,graph_id,task_id) VALUES(?1,?2,?3)
             ON CONFLICT(mission_id) DO NOTHING",
            params![task.input.mission_id, graph.id, task.input.task_id],
        )?;
    }
    Ok(())
}

fn require_digest(graph: &Graph, digest: &str) -> CoreResult<()> {
    if graph.digest != digest {
        return Err(CoreError::new(
            "contract_conflict",
            "Graph revision digest has changed",
        ));
    }
    Ok(())
}

fn check_receipt(tx: &Transaction<'_>, id: &str) -> CoreResult<Value> {
    match checks::get(tx, id) {
        Err(error) if error.code == "not_found" => Ok(Value::Null),
        result => result,
    }
}

#[cfg(windows)]
fn live_publication(
    tx: &Transaction<'_>,
    mission: &str,
    entries: &[crate::mission_recovery::JournalEntry],
    artifacts: &[CandidateArtifact],
) -> CoreResult<bool> {
    let database: String = tx.query_row(
        "SELECT file FROM pragma_database_list WHERE name='main'",
        [],
        |row| row.get(0),
    )?;
    let Some(state) = std::path::Path::new(&database).parent() else {
        return Ok(false);
    };
    let fallback: String = tx.query_row(
        "SELECT value FROM metadata WHERE key='workspace_root'",
        [],
        |row| row.get(0),
    )?;
    let verified = (|| -> CoreResult<bool> {
        let workspace =
            crate::projects::for_mission(tx, mission, std::path::Path::new(&fallback), state)?;
        for (entry, artifact) in entries.iter().zip(artifacts) {
            let broker = crate::tools::prepare(
                workspace.path(),
                state,
                &crate::contracts::ToolOperation::Read {
                    path: artifact.path.clone(),
                },
            )?;
            let read = broker.read_owned_guarded()?;
            if entry.identity.as_deref() != Some(read.identity.as_str())
                || read.bytes != artifact.content.as_bytes()
            {
                return Ok(false);
            }
        }
        Ok(true)
    })();
    Ok(verified.unwrap_or(false))
}

fn publication_verified(
    tx: &Transaction<'_>,
    task: &Task,
    contract: &MissionContract,
    candidate_digest: &str,
) -> CoreResult<bool> {
    let id = &task.input.mission_id;
    let (candidate, review): (String, String) = tx.query_row(
        "SELECT candidate,review FROM mission_runs WHERE mission_id=?1",
        [id],
        |row| Ok((row.get(0)?, row.get(1)?)),
    )?;
    let Ok(artifacts) = serde_json::from_str::<Vec<CandidateArtifact>>(&candidate) else {
        return Ok(false);
    };
    if store::digest(&artifacts)? != candidate_digest
        || crate::candidate::validate_artifacts(contract, &artifacts).is_err()
        || !crate::candidate::parse_review(&review).is_ok_and(|review| review["approved"] == true)
    {
        return Ok(false);
    }
    let policy = contract.execution.as_ref().unwrap();
    let entries = match crate::mission_recovery::journal(
        tx,
        id,
        &task.contract_digest,
        Some(candidate_digest),
    ) {
        Ok(entries) => entries,
        Err(error) if error.code == "journal_mismatch" => return Ok(false),
        Err(error) => return Err(error),
    };
    if entries.len() != artifacts.len()
        || entries
            .iter()
            .zip(&artifacts)
            .enumerate()
            .any(|(position, (entry, artifact))| {
                entry.position as usize != position
                    || entry.journal_status != "confirmed"
                    || entry.intent_status != "confirmed"
                    || entry.identity.is_none()
                    || entry.path != artifact.path
                    || entry.content != artifact.content
                    || entry.replacement
                        != contract
                            .artifact_previous_digests
                            .contains_key(&artifact.path)
            })
    {
        return Ok(false);
    }
    #[cfg(windows)]
    if !live_publication(tx, id, &entries, &artifacts)? {
        return Ok(false);
    }
    let dependencies = match dependency_inputs(tx, id) {
        Ok(inputs) => inputs,
        Err(error) if error.code == "task_not_ready" => return Ok(false),
        Err(error) => return Err(error),
    };
    let dependency_digest = (!dependencies.as_array().unwrap().is_empty())
        .then(|| store::digest(&dependencies))
        .transpose()?;
    for (index, recipe) in policy.checks.iter().enumerate() {
        let index = index as u32;
        let recipe_digest = checks::recipe_digest(
            &task.contract_digest,
            index,
            recipe,
            &policy.limits,
            dependency_digest.as_deref(),
        )?;
        let pre = check_receipt(tx, &mission_run::stage_id(id, &format!("check-{index}"))?)?;
        let post = check_receipt(
            tx,
            &mission_run::stage_id(id, &format!("post-check-{index}"))?,
        )?;
        if pre["mission_id"] != *id
            || post["mission_id"] != *id
            || !mission_run::valid_check(&pre, &task.contract_digest, candidate_digest, index)
            || !mission_run::valid_check(&post, &task.contract_digest, candidate_digest, index)
            || pre["check_digest"] != recipe_digest
            || post["check_digest"] != recipe_digest
            || pre["tool_digest"] != post["tool_digest"]
            || pre["dependency_digest"] != json!(dependency_digest)
            || post["dependency_digest"] != json!(dependency_digest)
        {
            return Ok(false);
        }
    }
    Ok(true)
}

fn task_status(tx: &Transaction<'_>, task: &Task) -> CoreResult<&'static str> {
    let id = &task.input.mission_id;
    let (contract, digest, mission_state) = mission(tx, id)?;
    if digest != task.contract_digest {
        return Ok("receipt_invalid");
    }
    let row: Option<(String, String, Option<String>, Option<String>)> = tx
        .query_row(
            "SELECT r.status,r.contract_digest,r.candidate_digest,i.status FROM mission_runs r
         LEFT JOIN mission_integrations i ON i.mission_id=r.mission_id WHERE r.mission_id=?1",
            [id],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
        )
        .optional()?;
    let Some((run, run_digest, candidate, integration)) = row else {
        return Ok(match mission_state.as_str() {
            "cancelled" | "revoked" => "cancelled",
            _ => "pending",
        });
    };
    if run_digest != task.contract_digest {
        return Ok("receipt_invalid");
    }
    let status = match integration.as_deref() {
        Some("publishing" | "postchecking" | "rolling_back" | "recovery_required") => {
            if integration.as_deref() == Some("recovery_required") {
                "recovery_required"
            } else {
                "running"
            }
        }
        Some("integrated") => {
            if mission_state != "approved" {
                "cancelled"
            } else if let Some(candidate) = candidate {
                if publication_verified(tx, task, &contract, &candidate)? {
                    "passed"
                } else {
                    "receipt_invalid"
                }
            } else {
                "receipt_invalid"
            }
        }
        Some("cancelled" | "revoked") => "cancelled",
        Some(_) => "failed",
        None => match run.as_str() {
            "generating" | "checking" | "reviewing" | "review_ready" => "running",
            "interrupted" => "interrupted",
            "cancelled" | "revoked" => "cancelled",
            _ => "failed",
        },
    };
    Ok(status)
}

fn states(tx: &Transaction<'_>, graph: &Graph) -> CoreResult<BTreeMap<String, &'static str>> {
    let mut states = BTreeMap::new();
    for task in &graph.tasks {
        let status = task_status(tx, task)?;
        let changed = tx.execute(
            "UPDATE task_graph_missions SET state=?2 WHERE mission_id=?1 AND state<>?2",
            params![task.input.mission_id, status],
        )?;
        if changed != 0 {
            store::event(
                tx,
                "task_graph_task_state",
                json!({
                    "graph_id":graph.id,"revision":graph.revision,"task_id":task.input.task_id,
                    "mission_id":task.input.mission_id,"status":status,
                }),
            )?;
        }
        states.insert(task.input.task_id.clone(), status);
    }
    Ok(states)
}

fn ready<'a>(graph: &'a Graph, states: &BTreeMap<String, &'static str>) -> Option<&'a Task> {
    if graph.state != "active"
        || states
            .values()
            .any(|status| matches!(*status, "running" | "recovery_required" | "receipt_invalid"))
    {
        return None;
    }
    graph
        .tasks
        .iter()
        .filter(|task| {
            states[&task.input.task_id] == "pending"
                && task
                    .input
                    .dependencies
                    .iter()
                    .all(|id| states[id] == "passed")
        })
        .min_by_key(|task| (std::cmp::Reverse(task.input.priority), &task.input.task_id))
}

pub(crate) fn admit(tx: &Transaction<'_>, mission_id: &str) -> CoreResult<()> {
    if planner_graph_id(tx, mission_id)?.is_some() {
        return Err(CoreError::new(
            "task_graph_parent",
            "The sealed parent mission runs through its task graph",
        ));
    }
    let owner: Option<String> = tx
        .query_row(
            "SELECT graph_id FROM task_graph_missions WHERE mission_id=?1",
            [mission_id],
            |row| row.get(0),
        )
        .optional()?;
    if let Some(owner) = owner {
        let graph = load(tx, &owner)?;
        if ready(&graph, &states(tx, &graph)?).map(|task| task.input.mission_id.as_str())
            != Some(mission_id)
        {
            return Err(CoreError::new(
                "task_not_ready",
                "Task is not ready in the current approved graph",
            ));
        }
    }
    Ok(())
}

/// Graph acceptance checks launch through the run coordinator on its sealed candidate.
pub(crate) fn ensure_manual_check_allowed(
    tx: &Transaction<'_>,
    mission_id: &str,
) -> CoreResult<()> {
    let owned: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM task_graph_missions WHERE mission_id=?1
         UNION ALL SELECT 1 FROM task_graph_planner_roots WHERE mission_id=?1)",
        [mission_id],
        |row| row.get(0),
    )?;
    if owned {
        return Err(CoreError::new(
            "permission_denied",
            "The task graph owns acceptance checks for this mission",
        ));
    }
    Ok(())
}

pub(crate) fn next(tx: &Transaction<'_>) -> CoreResult<Option<String>> {
    let ids = tx
        .prepare("SELECT id FROM task_graphs WHERE state<>'draft' ORDER BY id")?
        .query_map([], |row| row.get::<_, String>(0))?
        .collect::<Result<Vec<_>, _>>()?;
    let mut chosen = None;
    for id in ids {
        let graph = load(tx, &id)?;
        let states = states(tx, &graph)?;
        if let Some(task) = ready(&graph, &states) {
            let selection = (
                std::cmp::Reverse(task.input.priority),
                graph.id.clone(),
                task.input.mission_id.clone(),
            );
            if chosen.as_ref().is_none_or(|current| selection < *current) {
                chosen = Some(selection);
            }
        }
    }
    Ok(chosen.map(|(_, _, mission)| mission))
}

/// Persist a definitive pre-launch failure after the caller rolls back launch setup.
pub(crate) fn fail_start(tx: &Transaction<'_>, mission_id: &str, code: &str) -> CoreResult<()> {
    admit(tx, mission_id)?;
    let (_, digest) = mission_run::approved(tx, mission_id)?;
    tx.execute(
        "INSERT INTO mission_runs(mission_id,contract_digest,status,error,auto_integrate)
         VALUES(?1,?2,'failed',?3,0)",
        params![mission_id, digest, code],
    )?;
    store::event(
        tx,
        "mission_run_failed",
        json!({"mission_id":mission_id,"error":code}),
    )?;
    Ok(())
}

pub(crate) fn dependency_inputs(tx: &Transaction<'_>, mission_id: &str) -> CoreResult<Value> {
    let owner: Option<String> = tx
        .query_row(
            "SELECT graph_id FROM task_graph_missions WHERE mission_id=?1",
            [mission_id],
            |row| row.get(0),
        )
        .optional()?;
    let Some(owner) = owner else {
        return Ok(json!([]));
    };
    let graph = load(tx, &owner)?;
    let task = graph
        .tasks
        .iter()
        .find(|task| task.input.mission_id == mission_id)
        .ok_or_else(|| CoreError::new("task_not_ready", "Task mission has been superseded"))?;
    let mut inputs = Vec::new();
    for dependency in &task.input.dependencies {
        let predecessor = graph
            .tasks
            .iter()
            .find(|task| task.input.task_id == *dependency)
            .unwrap();
        if task_status(tx, predecessor)? != "passed" {
            return Err(CoreError::new(
                "task_not_ready",
                "Dependency lacks verified acceptance receipts",
            ));
        }
        let candidate: String = tx.query_row(
            "SELECT candidate FROM mission_runs WHERE mission_id=?1",
            [&predecessor.input.mission_id],
            |row| row.get(0),
        )?;
        let artifacts: Vec<CandidateArtifact> = serde_json::from_str(&candidate)?;
        inputs.push(json!({"task_id":dependency,"mission_id":predecessor.input.mission_id,
            "contract_digest":predecessor.contract_digest,"candidate_digest":store::digest(&artifacts)?,
            "artifacts":artifacts}));
    }
    Ok(json!(inputs))
}

fn view(tx: &Transaction<'_>, graph: &Graph) -> CoreResult<Value> {
    let statuses = states(tx, graph)?;
    let next = ready(graph, &statuses).map(|task| &task.input.task_id);
    let mut tasks = Vec::with_capacity(graph.tasks.len());
    for task in &graph.tasks {
        let (contract, _, _) = mission(tx, &task.input.mission_id)?;
        let execution = contract.execution.as_ref().unwrap();
        let mut status = statuses[&task.input.task_id];
        if status == "pending" {
            status = if graph.state == "cancelled" {
                "cancelled"
            } else if next == Some(&task.input.task_id) {
                "ready"
            } else if task
                .input
                .dependencies
                .iter()
                .any(|id| statuses[id] != "passed")
            {
                "blocked"
            } else {
                "pending"
            };
        }
        tasks.push(json!({
            "task":task, "status":status, "plan_id":execution.plan_id,
            "objective":contract.objective, "actions":contract.actions, "resources":contract.resources,
            "outputs":execution.artifacts, "acceptance":execution.checks, "limits":execution.limits,
            "model_memory_bytes":execution.primary_model.memory_bytes.max(execution.review_model.memory_bytes),
        }));
    }
    let in_flight = statuses.values().any(|status| *status == "running");
    let settled = statuses.values().all(|status| {
        matches!(*status, "passed" | "cancelled" | "failed" | "interrupted")
            || (graph.state == "cancelled" && *status == "pending")
    });
    let state = if graph.state == "active" && statuses.values().all(|status| *status == "passed") {
        "integrated"
    } else if graph.state == "active"
        && !in_flight
        && statuses.values().any(|status| {
            matches!(
                *status,
                "failed" | "interrupted" | "receipt_invalid" | "recovery_required"
            )
        })
    {
        "failed"
    } else if graph.state == "paused" && in_flight {
        "pausing"
    } else {
        &graph.state
    };
    Ok(
        json!({"graph_id":graph.id,"rfc":rfc(tx, &graph.rfc_id)?, "revision":graph.revision,
        "digest":graph.digest,"state":state,"settled":settled,"tasks":tasks}),
    )
}

fn create_rfc(tx: &Transaction<'_>, input: RfcInput) -> CoreResult<Value> {
    bounded(&input.rfc_id, "rfc_id", 128)?;
    crate::contracts::scope(&input.scope)?;
    bounded(&input.objective, "objective", 2048)?;
    let mut chat_id = input.chat_id;
    if let Some(id) = &input.input_id {
        bounded(id, "input_id", 128)?;
        let input_chat: String = tx
            .query_row(
                "SELECT chat_id FROM input_records WHERE id=?1",
                [id],
                |row| row.get(0),
            )
            .optional()?
            .ok_or_else(|| CoreError::new("not_found", "Source input not found"))?;
        if chat_id.as_ref().is_some_and(|chat| chat != &input_chat) {
            return Err(CoreError::new(
                "contract_conflict",
                "Source input belongs to another chat",
            ));
        }
        chat_id = Some(input_chat);
    }
    if let Some(chat_id) = &chat_id {
        bounded(chat_id, "chat_id", 128)?;
        let exists: bool = tx.query_row(
            "SELECT EXISTS(SELECT 1 FROM chats WHERE id=?1)",
            [chat_id],
            |row| row.get(0),
        )?;
        if !exists {
            return Err(CoreError::new("not_found", "Source chat not found"));
        }
    }
    let digest = store::digest(&(
        &input.rfc_id,
        &input.scope,
        &input.objective,
        &input.input_id,
        &chat_id,
    ))?;
    let inserted = tx.execute(
        "INSERT INTO task_rfcs(id,scope,objective,input_id,chat_id,digest) VALUES(?1,?2,?3,?4,?5,?6)
         ON CONFLICT(id) DO NOTHING",
        params![input.rfc_id,input.scope,input.objective,input.input_id,chat_id,digest],
    )?;
    let rfc = rfc(tx, &input.rfc_id)?;
    if inserted == 0 && rfc.digest != digest {
        return Err(CoreError::new(
            "contract_conflict",
            "Task RFC ID already binds another intent",
        ));
    }
    Ok(serde_json::to_value(rfc)?)
}

fn plan(tx: &Transaction<'_>, input: PlanInput) -> CoreResult<Graph> {
    bounded(&input.graph_id, "graph_id", 128)?;
    let rfc = rfc(tx, &input.rfc_id)?;
    if rfc.digest != input.rfc_digest {
        return Err(CoreError::new("contract_conflict", "RFC digest differs"));
    }
    let used: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM task_graphs WHERE id=?1 OR rfc_id=?2)",
        params![input.graph_id, input.rfc_id],
        |row| row.get(0),
    )?;
    if used {
        return Err(CoreError::new(
            "already_exists",
            "Graph ID or RFC is already bound",
        ));
    }
    let tasks = prepare_tasks(tx, &input.graph_id, &rfc, input.tasks)?;
    let digest = store::digest(&(&input.graph_id, &rfc.digest, 1u32, &tasks))?;
    let graph = Graph {
        id: input.graph_id,
        rfc_id: input.rfc_id,
        revision: 1,
        state: "draft".into(),
        digest,
        tasks,
    };
    persist_plan(tx, &graph)?;
    Ok(graph)
}

fn activate(tx: &Transaction<'_>, graph: &mut Graph, digest: &str) -> CoreResult<Vec<String>> {
    require_digest(graph, digest)?;
    if graph.state != "draft" {
        return Err(CoreError::new(
            "invalid_transition",
            "Only a draft graph can be approved",
        ));
    }
    let parent: Option<String> = tx
        .query_row(
            "SELECT mission_id FROM task_graph_planner_roots WHERE graph_id=?1",
            [&graph.id],
            |row| row.get(0),
        )
        .optional()?;
    let mut inherited_consent = None;
    if let Some(parent) = parent {
        let (contract, digest, state) = mission(tx, &parent)?;
        if state == "proposed" {
            if contract
                .execution
                .as_ref()
                .unwrap()
                .task_graph_digest
                .as_deref()
                != Some(graph.digest.as_str())
            {
                return Err(CoreError::new(
                    "contract_conflict",
                    "Parent seal differs from the task graph",
                ));
            }
            missions::approve(tx, &parent, &digest)?;
        } else if state != "approved" {
            return Err(CoreError::new(
                "invalid_transition",
                "Parent graph mission approval is unavailable",
            ));
        }
        inherited_consent = mission_run::swarm_consent(tx, &parent, &digest)?;
    }
    let mut newly_approved = Vec::new();
    for task in &graph.tasks {
        let id = &task.input.mission_id;
        let (_, digest, state) = mission(tx, id)?;
        if digest != task.contract_digest {
            return Err(CoreError::new("contract_conflict", "Task contract changed"));
        }
        match state.as_str() {
            "proposed" => {
                missions::approve(tx, id, &digest)?;
                newly_approved.push(id.clone());
            }
            "approved" => (),
            _ => {
                return Err(CoreError::new(
                    "invalid_transition",
                    "Graph has a revoked or cancelled task",
                ));
            }
        }
        if let Some(source) = &inherited_consent {
            if mission_run::swarm_consent(tx, id, &digest)?.is_none() {
                store::event(
                    tx,
                    "swarm_consent_recorded",
                    json!({
                        "mission_id":id,"contract_digest":digest,"source":source,"graph_id":graph.id,
                    }),
                )?;
            }
        }
    }
    tx.execute(
        "UPDATE task_graph_revisions SET approved=1 WHERE graph_id=?1 AND revision=?2",
        params![graph.id, graph.revision],
    )?;
    set_state(tx, graph, "active")?;
    Ok(newly_approved)
}

fn set_state(tx: &Transaction<'_>, graph: &mut Graph, state: &str) -> CoreResult<()> {
    tx.execute(
        "UPDATE task_graphs SET state=?2 WHERE id=?1",
        params![graph.id, state],
    )?;
    graph.state = state.to_owned();
    Ok(())
}

fn authority_digest(mut contract: MissionContract) -> CoreResult<String> {
    contract.execution.as_mut().unwrap().plan_id.clear();
    store::digest(&contract)
}

/// Retry the exact sealed authority, rather than asking a planner to reconstruct it.
fn retry_clone(tx: &Transaction<'_>, graph: &Graph, task: &Task) -> CoreResult<String> {
    let id = format!(
        "retry-{}",
        store::digest(&(
            &graph.id,
            graph.revision + 1,
            &task.input.task_id,
            &task.input.mission_id
        ))?
    );
    let plan_id = format!("plan-{}", store::digest(&(&id, "sealed"))?);
    let (mut contract, _, _) = mission(tx, &task.input.mission_id)?;
    let original_plan = contract.execution.as_ref().unwrap().plan_id.clone();
    contract.execution.as_mut().unwrap().plan_id = plan_id.clone();
    let sealed = serde_json::to_string(&contract)?;
    tx.execute(
        "INSERT INTO ai_jobs(id,kind,model_id,status,result,endpoint)
         SELECT ?1,kind,model_id,'succeeded',result,endpoint FROM ai_jobs WHERE id=?2",
        params![plan_id, original_plan],
    )?;
    tx.execute(
        "INSERT INTO mission_plans(mission_id,job_id,snapshot,plan,sealed_contract)
         SELECT ?1,?2,?3,plan,?3 FROM mission_plans WHERE mission_id=?4",
        params![id, plan_id, sealed, task.input.mission_id],
    )?;
    missions::propose(tx, &id, &contract)?;
    tx.execute(
        "INSERT INTO mission_project_bindings(mission_id,scope,root,identity)
         SELECT ?1,scope,root,identity FROM mission_project_bindings WHERE mission_id=?2",
        params![id, task.input.mission_id],
    )?;
    store::event(
        tx,
        "task_graph_retry_sealed",
        json!({"graph_id":graph.id,
        "task_id":task.input.task_id,"previous_mission_id":task.input.mission_id,
        "mission_id":id,"revision":graph.revision + 1}),
    )?;
    Ok(id)
}

fn replan(tx: &Transaction<'_>, input: ReplanInput) -> CoreResult<Graph> {
    let mut graph = load(tx, &input.graph_id)?;
    require_digest(&graph, &input.digest)?;
    let statuses = states(tx, &graph)?;
    if graph.state != "paused"
        || statuses
            .values()
            .any(|state| matches!(*state, "running" | "recovery_required" | "receipt_invalid"))
    {
        return Err(CoreError::new(
            "invalid_transition",
            "Pause and reconcile in-flight effects before replanning",
        ));
    }
    graph
        .revision
        .checked_add(1)
        .ok_or_else(|| CoreError::invalid("Graph revision limit reached"))?;
    let rfc = rfc(tx, &graph.rfc_id)?;
    let mut tasks = prepare_tasks(tx, &graph.id, &rfc, input.tasks)?;
    let proposed: BTreeMap<_, _> = tasks
        .iter()
        .map(|task| (&task.input.task_id, task))
        .collect();
    if tasks.len() != graph.tasks.len() {
        return Err(CoreError::new(
            "contract_conflict",
            "Replan requires the same approved task set",
        ));
    }
    for old in &graph.tasks {
        let new = proposed.get(&old.input.task_id).ok_or_else(|| {
            CoreError::new(
                "contract_conflict",
                "Replan cannot add or remove approved tasks",
            )
        })?;
        let state = statuses[&old.input.task_id];
        if state == "passed" && store::digest(old)? != store::digest(*new)? {
            return Err(CoreError::new(
                "contract_conflict",
                "Completed task and effects are immutable",
            ));
        }
        // Keep the cause of a failed dependency in the revised graph. A fresh
        // sealed mission must earn a new receipt before the dependent can run.
        if !old
            .input
            .dependencies
            .iter()
            .all(|dependency| new.input.dependencies.contains(dependency))
        {
            return Err(CoreError::new(
                "contract_conflict",
                "Replan cannot remove an approved dependency",
            ));
        }
        if old.input.mission_id != new.input.mission_id {
            let used: bool = tx.query_row(
                "SELECT EXISTS(SELECT 1 FROM mission_runs WHERE mission_id=?1)",
                [&new.input.mission_id],
                |row| row.get(0),
            )?;
            if used || state == "passed" {
                return Err(CoreError::new(
                    "contract_conflict",
                    "Retry requires a fresh sealed mission",
                ));
            }
            let (original, _, _) = mission(tx, &old.input.mission_id)?;
            let (replacement, _, _) = mission(tx, &new.input.mission_id)?;
            if authority_digest(original)? != authority_digest(replacement)? {
                return Err(CoreError::new(
                    "contract_conflict",
                    "Retry changes the original task authority",
                ));
            }
        }
    }
    // Clone only after the complete requested revision passes authority checks.
    for requested in &mut tasks {
        if let Some(previous) = graph.tasks.iter().find(|task| {
            task.input.task_id == requested.input.task_id
                && task.input.mission_id == requested.input.mission_id
                && matches!(statuses[&task.input.task_id], "failed" | "interrupted")
        }) {
            requested.input.mission_id = retry_clone(tx, &graph, previous)?;
            requested.contract_digest = mission(tx, &requested.input.mission_id)?.1;
        }
    }
    graph.revision = graph
        .revision
        .checked_add(1)
        .ok_or_else(|| CoreError::invalid("Graph revision limit reached"))?;
    graph.digest = store::digest(&(&graph.id, &rfc.digest, graph.revision, &tasks))?;
    graph.tasks = tasks;
    graph.state = "draft".into();
    persist_plan(tx, &graph)?;
    Ok(graph)
}

pub(crate) fn handle(
    tx: &Transaction<'_>,
    request_id: &str,
    action: &str,
    payload: &Value,
) -> CoreResult<Value> {
    if action == "rfc_create" {
        let result = create_rfc(tx, parse(payload)?)?;
        store::event(
            tx,
            "task_rfc_created",
            json!({"request_id":request_id,"rfc_id":result["rfc_id"],
            "input_id":result["input_id"],"chat_id":result["chat_id"],"digest":result["digest"]}),
        )?;
        return Ok(result);
    }
    if action == "rfc_get" {
        #[derive(Deserialize)]
        #[serde(deny_unknown_fields)]
        struct RfcId {
            rfc_id: String,
        }
        let id: RfcId = parse(payload)?;
        return Ok(serde_json::to_value(rfc(tx, &id.rfc_id)?)?);
    }
    if action == "get" {
        let input: GraphInput = parse(payload)?;
        return view(tx, &load(tx, &input.graph_id)?);
    }
    let mut newly_approved = None;
    let mut cancel_missions = None;
    let graph = match action {
        "plan" => plan(tx, parse(payload)?)?,
        "replan" => replan(tx, parse(payload)?)?,
        "activate" | "pause" | "resume" | "cancel" => {
            let input: RevisionInput = parse(payload)?;
            let mut graph = load(tx, &input.graph_id)?;
            require_digest(&graph, &input.digest)?;
            match (action, graph.state.as_str()) {
                ("activate", _) => newly_approved = Some(activate(tx, &mut graph, &input.digest)?),
                ("pause", "active") => set_state(tx, &mut graph, "paused")?,
                ("resume", "paused") => {
                    let statuses = states(tx, &graph)?;
                    if statuses
                        .values()
                        .any(|status| matches!(*status, "recovery_required" | "receipt_invalid"))
                    {
                        return Err(CoreError::new(
                            "recovery_required",
                            "Reconcile task effects before resuming",
                        ));
                    }
                    set_state(tx, &mut graph, "active")?;
                }
                ("cancel", "draft" | "active" | "paused") => {
                    let statuses = states(tx, &graph)?;
                    cancel_missions = Some(
                        graph
                            .tasks
                            .iter()
                            .filter(|task| statuses[&task.input.task_id] == "running")
                            .map(|task| task.input.mission_id.clone())
                            .collect::<Vec<_>>(),
                    );
                    set_state(tx, &mut graph, "cancelled")?;
                }
                _ => {
                    return Err(CoreError::new(
                        "invalid_transition",
                        "Graph cannot enter the requested state",
                    ));
                }
            }
            graph
        }
        _ => return Err(CoreError::invalid("Unknown task graph action")),
    };
    store::event(
        tx,
        "task_graph_transition",
        json!({"request_id":request_id,"action":action,
        "graph_id":graph.id,"rfc_id":graph.rfc_id,"revision":graph.revision,
        "state":graph.state,"digest":graph.digest}),
    )?;
    let mut result = view(tx, &graph)?;
    if let Some(newly_approved) = newly_approved {
        result["newly_approved"] = json!(newly_approved);
    }
    if let Some(cancel_missions) = cancel_missions {
        result["cancel_missions"] = json!(cancel_missions);
    }
    Ok(result)
}

pub(crate) fn create_planner_graph(
    tx: &Transaction<'_>,
    job_id: &str,
    mission_id: &str,
    contract: &MissionContract,
    children: Vec<(String, PlannedTask)>,
) -> CoreResult<String> {
    let rfc_id = format!("rfc-{}", store::digest(&(mission_id, job_id))?);
    let input_id = tx
        .query_row(
            "SELECT id FROM input_records WHERE mission_id=?1 ORDER BY rowid LIMIT 1",
            [mission_id],
            |row| row.get::<_, String>(0),
        )
        .optional()?;
    let rfc = handle(
        tx,
        job_id,
        "rfc_create",
        &json!({
            "rfc_id":rfc_id,"scope":contract.scope,"objective":contract.objective,"input_id":input_id,
        }),
    )?;
    let tasks = children
        .into_iter()
        .map(|(id, task)| TaskInput {
            task_id: task.task_id,
            mission_id: id,
            dependencies: task.dependencies,
            priority: task.priority,
        })
        .collect();
    let graph = plan(
        tx,
        PlanInput {
            graph_id: mission_id.to_owned(),
            rfc_id,
            rfc_digest: rfc["digest"]
                .as_str()
                .expect("RFC supplies digest")
                .to_owned(),
            tasks,
        },
    )?;
    store::event(
        tx,
        "task_graph_transition",
        json!({"request_id":job_id,"action":"plan",
        "graph_id":graph.id,"rfc_id":graph.rfc_id,"revision":graph.revision,
        "state":graph.state,"digest":graph.digest}),
    )?;
    Ok(graph.digest)
}

pub(crate) fn bind_planner_root(tx: &Transaction<'_>, mission_id: &str) -> CoreResult<()> {
    tx.execute(
        "INSERT INTO task_graph_planner_roots(mission_id,graph_id) VALUES(?1,?1)",
        [mission_id],
    )?;
    Ok(())
}

fn planner_graph_id(tx: &Transaction<'_>, mission_id: &str) -> CoreResult<Option<String>> {
    Ok(tx
        .query_row(
            "SELECT graph_id FROM task_graph_planner_roots WHERE mission_id=?1",
            [mission_id],
            |row| row.get(0),
        )
        .optional()?)
}

pub(crate) fn planner_root(tx: &Transaction<'_>, mission_id: &str) -> CoreResult<Option<Value>> {
    let Some(graph_id) = planner_graph_id(tx, mission_id)? else {
        return Ok(None);
    };
    Ok(Some(view(tx, &load(tx, &graph_id)?)?))
}

pub(crate) fn approve_planner_root(
    tx: &Transaction<'_>,
    request_id: &str,
    mission_id: &str,
    contract_digest: &str,
) -> CoreResult<Option<Value>> {
    let Some(graph_id) = planner_graph_id(tx, mission_id)? else {
        return Ok(None);
    };
    let (contract, recorded, state) = mission(tx, mission_id)?;
    if recorded != contract_digest || state != "proposed" {
        return Err(CoreError::new(
            "contract_conflict",
            "Parent mission approval differs from its sealed proposal",
        ));
    }
    let digest = &contract.execution.as_ref().unwrap().task_graph_digest;
    let mut result = handle(
        tx,
        request_id,
        "activate",
        &json!({"graph_id":graph_id,"digest":digest}),
    )?;
    result["mission_id"] = json!(mission_id);
    result["contract_digest"] = json!(recorded);
    Ok(Some(result))
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::contracts::{Generation, MissionExecutionLimits, ToolOperation};

    fn fixture() -> (tempfile::TempDir, store::Store) {
        let root = tempfile::tempdir().unwrap();
        let workspace = root.path().join("workspace");
        std::fs::create_dir(&workspace).unwrap();
        let store = store::Store::open(&root.path().join("state"), &workspace).unwrap();
        (root, store)
    }

    fn sealed(tx: &Transaction<'_>, id: &str, path: &str, objective: &str) -> String {
        let plan = format!("plan-{id}");
        let model = json!({"id":"model","provider":"lm_studio","endpoint":"http://127.0.0.1:1234",
            "capabilities":["chat"],"memory_bytes":1000});
        let model = serde_json::from_value::<crate::contracts::ModelManifest>(model).unwrap();
        let model_digest = store::digest(&model).unwrap();
        let contract: MissionContract = serde_json::from_value(json!({
            "version":1,"scope":"project:graph","objective":objective,
            "actions":["mission_generate","artifact_create"],"resources":[path],
            "rollback":"owned verified removal","execution":{
                "plan_id":plan, "primary_model":model,"primary_model_digest":model_digest,
                "context_handoff":{"digest":store::digest(&json!({"constraint":"keep sealed history"})).unwrap(),"data":{"constraint":"keep sealed history"}},
                "review_model":model,"review_model_digest":model_digest,"review_generation":Generation::default(),
                "artifacts":[{"path":path,"purpose":"Perform the task"}],
                "checks":[{"kind":"json_validate","entrypoint":path}],"limits":MissionExecutionLimits::default()
            }
        })).unwrap();
        tx.execute(
            "INSERT INTO ai_jobs(id,kind,model_id,status) VALUES(?1,'mission_plan','model','succeeded')",
            [&plan],
        ).unwrap();
        tx.execute(
            "INSERT INTO mission_plans(mission_id,job_id,snapshot,sealed_contract) VALUES(?1,?2,'{}',?3)",
            params![id,plan,serde_json::to_string(&contract).unwrap()],
        ).unwrap();
        missions::propose(tx, id, &contract).unwrap()["contract_digest"]
            .as_str()
            .unwrap()
            .to_owned()
    }

    fn prepared(tx: &Transaction<'_>, tasks: Value) -> Value {
        let rfc = handle(
            tx,
            "request-rfc",
            "rfc_create",
            &json!({"rfc_id":"rfc","scope":"project:graph","objective":"Produce verified outputs"}),
        )
        .unwrap();
        handle(
            tx,
            "request-plan",
            "plan",
            &json!({
                "graph_id":"graph","rfc_id":"rfc","rfc_digest":rfc["digest"],"tasks":tasks
            }),
        )
        .unwrap()
    }

    fn transition(tx: &Transaction<'_>, action: &str, graph: &Value) -> CoreResult<Value> {
        handle(
            tx,
            action,
            action,
            &json!({"graph_id":"graph","digest":graph["digest"]}),
        )
    }

    fn publication(tx: &Transaction<'_>, id: &str, contract: &str, path: &str) -> String {
        let artifacts = vec![CandidateArtifact {
            path: path.into(),
            content: "{}".into(),
        }];
        let digest = store::digest(&artifacts).unwrap();
        tx.execute(
            "INSERT INTO mission_runs(mission_id,contract_digest,status,candidate,candidate_digest,review)
                VALUES(?1,?2,'review_ready',?3,?4,?5)",
            params![id, contract, serde_json::to_string(&artifacts).unwrap(), digest,
                json!({"approved":true,"reason":"fixture"}).to_string()],
        ).unwrap();
        tx.execute(
            "INSERT INTO mission_integrations(mission_id,status,post_index) VALUES(?1,'integrated',1)",
            [id],
        ).unwrap();
        let operation = ToolOperation::Create {
            path: path.into(),
            content: "{}".into(),
        };
        let intent_digest = store::digest(&(contract, Some(digest.as_str()), &operation)).unwrap();
        tx.execute(
            "INSERT INTO tool_intents(request_id,request_digest,mission_id,target,content_digest,status)
                VALUES('intent',?1,?2,?3,?4,'confirmed')",
            params![intent_digest,id,path, crate::tools::sha(b"{}")],
        ).unwrap();
        tx.execute(
            "INSERT INTO intent_operations(request_id,operation) VALUES('intent',?1)",
            [serde_json::to_string(&operation).unwrap()],
        )
        .unwrap();
        #[cfg(windows)]
        let identity = {
            let database: String = tx
                .query_row(
                    "SELECT file FROM pragma_database_list WHERE name='main'",
                    [],
                    |row| row.get(0),
                )
                .unwrap();
            let state = std::path::Path::new(&database).parent().unwrap();
            let workspace: String = tx
                .query_row(
                    "SELECT value FROM metadata WHERE key='workspace_root'",
                    [],
                    |row| row.get(0),
                )
                .unwrap();
            crate::tools::prepare(std::path::Path::new(&workspace), state, &operation)
                .unwrap()
                .create_owned(b"{}")
                .unwrap()
                .0
        };
        #[cfg(not(windows))]
        let identity = "verified-identity";
        tx.execute(
            "INSERT INTO mission_integration_files(mission_id,position,intent_id,identity,status)
             VALUES(?1,0,'intent',?2,'confirmed')",
            params![id, identity],
        )
        .unwrap();
        digest
    }

    fn receipt(tx: &Transaction<'_>, stage: &str, contract: &str, candidate: &str) -> String {
        let check_id = mission_run::stage_id("first-mission", stage).unwrap();
        let (sealed, _, _) = mission(tx, "first-mission").unwrap();
        let policy = sealed.execution.unwrap();
        let recipe_digest =
            store::digest(&(contract, 0u32, &policy.checks[0], &policy.limits)).unwrap();
        tx.execute(
            "INSERT INTO project_checks(id,mission_id,contract_digest,check_index,candidate_digest,
                 check_digest,tool_digest,run_name,run_directory,status,cleanup,receipt)
             VALUES(?1,'first-mission',?2,0,?3,?4,?5,?1,?1,'succeeded','complete',?6)",
            params![
                check_id,
                contract,
                candidate,
                recipe_digest,
                "0".repeat(64),
                json!({"token":{"lpac":true}}).to_string()
            ],
        )
        .unwrap();
        check_id
    }

    #[test]
    fn dependencies_require_bound_and_passing_publication_receipts() {
        let (_root, mut store) = fixture();
        let tx = store.transaction().unwrap();
        let first = sealed(&tx, "first-mission", "first.json", "Make first");
        sealed(&tx, "second-mission", "second.json", "Make second");
        let graph = prepared(
            &tx,
            json!([
                {"task_id":"second","mission_id":"second-mission","dependencies":["first"],"priority":99},
                {"task_id":"first","mission_id":"first-mission"}
            ]),
        );
        assert!(admit(&tx, "first-mission").is_err());
        let graph = transition(&tx, "activate", &graph).unwrap();
        assert_eq!(
            graph["newly_approved"],
            json!(["second-mission", "first-mission"])
        );
        assert_eq!(next(&tx).unwrap().as_deref(), Some("first-mission"));
        assert!(admit(&tx, "second-mission").is_err());

        let output = publication(&tx, "first-mission", &first, "first.json");
        assert_eq!(next(&tx).unwrap(), None);
        receipt(&tx, "check-0", &first, &output);
        let post = receipt(&tx, "post-check-0", &first, "stale");
        assert_eq!(next(&tx).unwrap(), None);
        tx.execute(
            "UPDATE project_checks SET candidate_digest=?2,status='failed' WHERE id=?1",
            params![post, output],
        )
        .unwrap();
        assert_eq!(next(&tx).unwrap(), None);
        tx.execute(
            "UPDATE project_checks SET status='succeeded' WHERE id=?1",
            [&post],
        )
        .unwrap();
        assert_eq!(next(&tx).unwrap().as_deref(), Some("second-mission"));
        assert_eq!(
            dependency_inputs(&tx, "second-mission").unwrap()[0]["artifacts"][0]["content"],
            "{}"
        );

        let graph = transition(&tx, "pause", &graph).unwrap();
        assert_eq!(graph["state"], "paused");
        assert_eq!(next(&tx).unwrap(), None);
        let graph = transition(&tx, "resume", &graph).unwrap();
        assert_eq!(next(&tx).unwrap().as_deref(), Some("second-mission"));
        let (_, launch) = mission_run::start(&tx, "second-mission", false).unwrap();
        let prompt: Value =
            serde_json::from_str(launch.messages[1]["content"].as_str().unwrap()).unwrap();
        assert_eq!(
            prompt["dependency_inputs"][0]["artifacts"][0]["content"],
            "{}"
        );
        assert_eq!(
            transition(&tx, "pause", &graph).unwrap()["state"],
            "pausing"
        );
        assert_eq!(
            transition(&tx, "cancel", &graph).unwrap()["cancel_missions"],
            json!(["second-mission"])
        );
        assert_eq!(next(&tx).unwrap(), None);
    }

    #[test]
    fn restart_requires_fresh_sealed_retry_without_extending_authority() {
        let (root, mut store) = fixture();
        {
            let tx = store.transaction().unwrap();
            let first = sealed(&tx, "first-mission", "first.json", "Make first");
            sealed(&tx, "second-mission", "second.json", "Make second");
            sealed(&tx, "retry", "first.json", "Make first");
            sealed(&tx, "wider", "third.json", "Different objective");
            let graph = prepared(
                &tx,
                json!([
                    {"task_id":"first","mission_id":"first-mission"},
                    {"task_id":"second","mission_id":"second-mission","dependencies":["first"]}
                ]),
            );
            transition(&tx, "activate", &graph).unwrap();
            tx.execute(
                "INSERT INTO mission_runs(mission_id,contract_digest,status)
                 VALUES('first-mission',?1,'generating')",
                [&first],
            )
            .unwrap();
            tx.commit().unwrap();
        }
        drop(store);
        let mut store =
            store::Store::open(&root.path().join("state"), &root.path().join("workspace")).unwrap();
        let tx = store.transaction().unwrap();
        let graph = handle(&tx, "read", "get", &json!({"graph_id":"graph"})).unwrap();
        assert_eq!(graph["tasks"][0]["status"], "interrupted");
        assert_eq!(graph["tasks"][1]["status"], "blocked");
        assert_eq!(next(&tx).unwrap(), None);
        let graph = transition(&tx, "pause", &graph).unwrap();
        let revise = |id: &str, dependencies: Vec<&str>| {
            handle(
                &tx,
                "replan",
                "replan",
                &json!({"graph_id":"graph","digest":graph["digest"],"tasks":[
                    {"task_id":"first","mission_id":id},
                    {"task_id":"second","mission_id":"second-mission","dependencies":dependencies}
                ]}),
            )
        };
        assert_eq!(
            revise("wider", vec!["first"]).unwrap_err().code,
            "contract_conflict"
        );
        assert_eq!(
            revise("retry", vec![]).unwrap_err().code,
            "contract_conflict"
        );
        let revision = revise("retry", vec!["first"]).unwrap();
        assert_eq!(revision["revision"], 2);
        assert!(transition(&tx, "activate", &graph).is_err());
        assert_eq!(next(&tx).unwrap(), None);
        transition(&tx, "activate", &revision).unwrap();
        assert!(admit(&tx, "first-mission").is_err());
        assert_eq!(next(&tx).unwrap().as_deref(), Some("retry"));
    }

    #[test]
    fn same_list_replan_seals_exact_retry_without_running_or_releasing_dependents() {
        let (_root, mut store) = fixture();
        let tx = store.transaction().unwrap();
        let digest = sealed(&tx, "first-mission", "first.json", "Make first");
        sealed(&tx, "second-mission", "second.json", "Make second");
        let graph = prepared(
            &tx,
            json!([
                {"task_id":"first","mission_id":"first-mission"},
                {"task_id":"second","mission_id":"second-mission","dependencies":["first"]}
            ]),
        );
        transition(&tx, "activate", &graph).unwrap();
        tx.execute("INSERT INTO mission_runs(mission_id,contract_digest,status,error) VALUES('first-mission',?1,'interrupted','worker_interrupted')", [&digest]).unwrap();
        let original = mission(&tx, "first-mission").unwrap().0;
        let original_seal = serde_json::to_value(&original).unwrap();
        let graph = transition(&tx, "pause", &graph).unwrap();
        let revision = handle(
            &tx,
            "retry",
            "replan",
            &json!({"graph_id":"graph","digest":graph["digest"],"tasks":[
                {"task_id":"first","mission_id":"first-mission"},
                {"task_id":"second","mission_id":"second-mission","dependencies":["first"]}
            ]}),
        )
        .unwrap();
        assert_eq!(revision["revision"], 2);
        assert_eq!(revision["state"], "draft");
        let retry = revision["tasks"][0]["task"]["mission_id"].as_str().unwrap();
        assert_ne!(retry, "first-mission");
        let (cloned, _, state) = mission(&tx, retry).unwrap();
        assert_eq!(state, "proposed");
        assert_ne!(
            cloned.execution.as_ref().unwrap().plan_id,
            original.execution.as_ref().unwrap().plan_id
        );
        assert_eq!(
            authority_digest(cloned).unwrap(),
            authority_digest(original).unwrap()
        );
        assert_eq!(
            serde_json::to_value(mission(&tx, "first-mission").unwrap().0).unwrap(),
            original_seal
        );
        assert_eq!(next(&tx).unwrap(), None);
        let run_count: u32 = tx
            .query_row(
                "SELECT COUNT(*) FROM mission_runs WHERE mission_id=?1",
                [retry],
                |row| row.get(0),
            )
            .unwrap();
        assert_eq!(run_count, 0);
        assert_eq!(revision["tasks"][1]["status"], "blocked");
        transition(&tx, "activate", &revision).unwrap();
        assert_eq!(next(&tx).unwrap().as_deref(), Some(retry));
        assert!(admit(&tx, "first-mission").is_err());
        assert!(admit(&tx, "second-mission").is_err());
    }

    #[test]
    fn rejects_duplicate_missing_and_cyclic_dependencies() {
        for tasks in [
            json!([{"task_id":"a","mission_id":"first","dependencies":["a"]}]),
            json!([{"task_id":"a","mission_id":"first","dependencies":["missing"]}]),
            json!([{"task_id":"a","mission_id":"first","dependencies":["b","b"]},
                   {"task_id":"b","mission_id":"second"}]),
            json!([{"task_id":"a","mission_id":"first","dependencies":["b"]},
                   {"task_id":"b","mission_id":"second","dependencies":["a"]}]),
        ] {
            assert!(validate_dag(&parse::<Vec<TaskInput>>(&tasks).unwrap()).is_err());
        }
    }
}
