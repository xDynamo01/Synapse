//! Core-owned operational ledger. Only IDs, fixed diagnostics, and measured
//! counters enter this store; prompts/provider bodies never do.
use crate::{
    contracts::{CoreError, CoreResult, bounded},
    conversation::Launch,
    operational::{Admission, MissionBudget, MissionUsage, WorkerMetrics},
    store,
};
use rusqlite::{OptionalExtension, Transaction, params};
use serde::Deserialize;
use serde_json::{Value, json};

pub(crate) fn migrate(tx: &Transaction<'_>) -> CoreResult<()> {
    tx.execute_batch("CREATE TABLE IF NOT EXISTS operational_budgets(
      scope_id TEXT PRIMARY KEY,budget TEXT NOT NULL,usage TEXT NOT NULL,
      started_ms INTEGER,last_seen_ms INTEGER);
      CREATE TABLE IF NOT EXISTS operational_attempts(
      attempt_id TEXT PRIMARY KEY,scope_id TEXT NOT NULL REFERENCES operational_budgets(scope_id),
      job_id TEXT NOT NULL,mission_id TEXT,model_id TEXT NOT NULL,purpose TEXT NOT NULL,
      started_ms INTEGER NOT NULL,finished_ms INTEGER,elapsed_ms INTEGER,
      status TEXT NOT NULL CHECK(status IN ('running','finished','interrupted')),
      outcome TEXT,metrics TEXT,snapshot TEXT NOT NULL);
      CREATE INDEX IF NOT EXISTS operational_attempt_scope ON operational_attempts(scope_id,started_ms);
      CREATE INDEX IF NOT EXISTS operational_attempt_job ON operational_attempts(job_id);")?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    fn launch(job: &str) -> Launch {
        Launch {
            id: job.into(),
            model_id: "manual-model".into(),
            endpoint: "http://127.0.0.1:9".into(),
            messages: vec![json!({"role":"user","content":"CANARY-private-prompt"})],
            generation: Default::default(),
            purpose: crate::conversation::Purpose::MissionPlan,
        }
    }
    fn seed(tx: &Transaction<'_>) {
        tx.execute_batch("INSERT INTO missions VALUES('root','{}','digest','proposed',NULL);
            INSERT INTO missions VALUES('child','{}','digest','proposed',NULL);
            INSERT INTO ai_jobs(id,kind,model_id,status) VALUES('job','mission_plan','manual-model','running');
            INSERT INTO ai_jobs(id,kind,model_id,status) VALUES('child-job','mission_plan','manual-model','running');
            INSERT INTO mission_plans(mission_id,job_id,snapshot) VALUES('root','job','{}');
            INSERT INTO mission_plans(mission_id,job_id,snapshot) VALUES('child','child-job','{}');
            INSERT INTO task_rfcs(id,scope,objective,digest) VALUES('rfc','project:test','test','digest');
            INSERT INTO task_graphs(id,rfc_id,revision,state,digest,tasks) VALUES('graph','rfc',1,'draft','digest','[]');
            INSERT INTO task_graph_planner_roots VALUES('root','graph');
            INSERT INTO task_graph_missions VALUES('child','graph','task','pending');").unwrap();
    }
    fn budget(calls: u64) -> Value {
        json!({"elapsed_ms":1_800_000,"tokens":null,"inference_calls":calls,"ram_bytes":null,"vram_bytes":null})
    }
    #[test]
    fn root_ledger_aggregates_children_retries_and_idempotent_finishes() {
        let dir = tempfile::tempdir().unwrap();
        let mut db = crate::store::Store::open(dir.path(), dir.path()).unwrap();
        let tx = db.transaction().unwrap();
        seed(&tx);
        dispatch(
            &tx,
            "budget_set",
            &json!({"mission_id":"root","budget":budget(3)}),
        )
        .unwrap();
        let job = launch("job");
        admit(&tx, &job).unwrap();
        begin(&tx, &job, "job:1").unwrap();
        let metrics = WorkerMetrics::unavailable();
        finish(&tx, "job", "job:1", &metrics, 20, "CANARY-private-error").unwrap();
        finish(&tx, "job", "job:1", &metrics, 20, "CANARY-private-error").unwrap();
        begin(&tx, &job, "job:2").unwrap();
        finish(&tx, "job", "job:2", &metrics, 30, "completed").unwrap();
        let child = launch("child-job");
        admit(&tx, &child).unwrap();
        begin(&tx, &child, "child:1").unwrap();
        finish(&tx, "child-job", "child:1", &metrics, 40, "completed").unwrap();
        assert_eq!(
            admit(&tx, &child).unwrap_err().code,
            "budget_calls_exhausted"
        );
        let value = dispatch(&tx, "budget_get", &json!({"mission_id":"child"})).unwrap();
        assert_eq!(value["scope_id"], "mission:root");
        assert_eq!(value["usage"]["attempts"], 3);
        assert_eq!(value["usage"]["unknown_token_attempts"], 3);
        assert_eq!(value["retry_attempts"], 1);
        assert_eq!(value["failed_attempts"], 1);
        assert_eq!(value["attempt_duration_ms"], 90);
        let attempts = dispatch(&tx, "attempts", &json!({"mission_id":"root"})).unwrap();
        assert_eq!(attempts["attempts"].as_array().unwrap().len(), 3);
        assert!(!attempts.to_string().contains("CANARY"));
        let events: String = tx
            .query_row(
                "SELECT GROUP_CONCAT(payload) FROM events WHERE kind LIKE 'operational_%'",
                [],
                |row| row.get(0),
            )
            .unwrap();
        assert!(!events.contains("CANARY"));
    }
    #[test]
    fn admission_is_fail_closed_and_started_budgets_only_tighten() {
        let dir = tempfile::tempdir().unwrap();
        let mut db = crate::store::Store::open(dir.path(), dir.path()).unwrap();
        let tx = db.transaction().unwrap();
        seed(&tx);
        assert_eq!(
            dispatch(
                &tx,
                "budget_set",
                &json!({"mission_id":"missing","budget":budget(1)})
            )
            .unwrap_err()
            .code,
            "not_found"
        );
        dispatch(
            &tx,
            "budget_set",
            &json!({"mission_id":"root","budget":budget(0)}),
        )
        .unwrap();
        assert_eq!(
            admit(&tx, &launch("job")).unwrap_err().code,
            "budget_calls_exhausted"
        );
        let mut limits = budget(2);
        limits["tokens"] = json!(10000);
        dispatch(
            &tx,
            "budget_set",
            &json!({"mission_id":"root","budget":limits}),
        )
        .unwrap();
        assert_eq!(
            admit(&tx, &launch("job")).unwrap_err().code,
            "budget_token_counter_unavailable"
        );
        dispatch(
            &tx,
            "budget_set",
            &json!({"mission_id":"root","budget":budget(2)}),
        )
        .unwrap();
        begin(&tx, &launch("job"), "job:1").unwrap();
        assert_eq!(
            dispatch(
                &tx,
                "budget_set",
                &json!({"mission_id":"root","budget":budget(3)})
            )
            .unwrap_err()
            .code,
            "budget_expansion_forbidden"
        );
        dispatch(
            &tx,
            "budget_set",
            &json!({"mission_id":"root","budget":budget(1)}),
        )
        .unwrap();
        recover(&tx).unwrap();
        recover(&tx).unwrap();
        let value = dispatch(&tx, "budget_get", &json!({"mission_id":"root"})).unwrap();
        assert_eq!(value["usage"]["unknown_token_attempts"], 1);
        assert_eq!(value["usage"]["peak_vram_bytes"], Value::Null);
        let now = now_ms().unwrap();
        tx.execute(
            "UPDATE operational_budgets SET last_seen_ms=?1",
            [(now + 50000) as i64],
        )
        .unwrap();
        assert_eq!(
            admit(&tx, &launch("job")).unwrap_err().code,
            "budget_clock_unavailable"
        );
    }
    #[test]
    fn manual_graph_adopts_prior_planning_attempts_and_shares_the_strictest_cap() {
        let dir = tempfile::tempdir().unwrap();
        let mut db = crate::store::Store::open(dir.path(), dir.path()).unwrap();
        let tx = db.transaction().unwrap();
        seed(&tx);
        tx.execute_batch(
            "DELETE FROM task_graph_planner_roots;DELETE FROM task_graph_missions;
            INSERT INTO missions VALUES('graph','{}','digest','proposed',NULL);",
        )
        .unwrap();
        dispatch(
            &tx,
            "budget_set",
            &json!({"mission_id":"root","budget":budget(2)}),
        )
        .unwrap();
        dispatch(
            &tx,
            "budget_set",
            &json!({"mission_id":"child","budget":budget(3)}),
        )
        .unwrap();
        begin(&tx, &launch("job"), "root-plan").unwrap();
        finish(
            &tx,
            "job",
            "root-plan",
            &WorkerMetrics::unavailable(),
            10,
            "completed",
        )
        .unwrap();
        begin(&tx, &launch("child-job"), "child-plan").unwrap();
        finish(
            &tx,
            "child-job",
            "child-plan",
            &WorkerMetrics::unavailable(),
            20,
            "completed",
        )
        .unwrap();
        tx.execute_batch(
            "INSERT INTO task_graph_missions VALUES('root','graph','first','pending');
            INSERT INTO task_graph_missions VALUES('child','graph','second','pending');",
        )
        .unwrap();
        let shared = dispatch(&tx, "budget_get", &json!({"mission_id":"child"})).unwrap();
        assert_eq!(shared["scope_id"], "graph:graph");
        assert_eq!(shared["budget"]["inference_calls"], 2);
        assert_eq!(shared["usage"]["attempts"], 2);
        assert_eq!(shared["usage"]["unknown_token_attempts"], 2);
        assert_eq!(shared["attempt_duration_ms"], 30);
        assert_eq!(
            admit(&tx, &launch("child-job")).unwrap_err().code,
            "budget_calls_exhausted"
        );
        let repeated = dispatch(&tx, "budget_get", &json!({"mission_id":"root"})).unwrap();
        assert_eq!(repeated["usage"]["unknown_token_attempts"], 2);
        let standalone = dispatch(&tx, "budget_get", &json!({"mission_id":"graph"})).unwrap();
        assert_eq!(standalone["scope_id"], "mission:graph");
        assert_eq!(standalone["usage"]["attempts"], 0);
        let receipts = dispatch(&tx, "attempts", &json!({"job_id":"job"})).unwrap();
        assert_eq!(receipts["attempts"].as_array().unwrap().len(), 2);
    }
}
fn now_ms() -> CoreResult<u64> {
    let value = std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_err(|_| {
            CoreError::new(
                "budget_clock_unavailable",
                "Operational clock is unavailable",
            )
        })?
        .as_millis();
    u64::try_from(value)
        .ok()
        .filter(|value| *value <= i64::MAX as u64)
        .ok_or_else(|| {
            CoreError::new(
                "budget_clock_unavailable",
                "Operational clock is unavailable",
            )
        })
}
fn mission_scope(tx: &Transaction<'_>, mission: &str) -> CoreResult<String> {
    let graph: Option<(String, Option<String>)> = tx
        .query_row(
            "SELECT c.graph_id,r.mission_id FROM task_graph_missions c
       LEFT JOIN task_graph_planner_roots r ON r.graph_id=c.graph_id WHERE c.mission_id=?1",
            [mission],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?;
    Ok(match graph {
        Some((_, Some(root))) => format!("mission:{root}"),
        // RFC-created graphs have no synthetic planner mission. They still
        // share one budget; a separate namespace prevents a mission ID clash.
        Some((graph, None)) => format!("graph:{graph}"),
        None => format!("mission:{mission}"),
    })
}
fn existing_mission(tx: &Transaction<'_>, mission: &str) -> CoreResult<()> {
    bounded(mission, "mission_id", 128)?;
    let exists:bool=tx.query_row("SELECT EXISTS(SELECT 1 FROM missions WHERE id=?1 UNION ALL SELECT 1 FROM mission_plans WHERE mission_id=?1)",[mission],|row|row.get(0))?;
    if !exists {
        return Err(CoreError::new("not_found", "Mission does not exist"));
    }
    Ok(())
}
fn tighter_optional(next: Option<u64>, old: Option<u64>) -> bool {
    match (next, old) {
        (_, None) => true,
        (Some(next), Some(old)) => next <= old,
        (None, Some(_)) => false,
    }
}
fn job_scope(tx: &Transaction<'_>, job: &str) -> CoreResult<(String, Option<String>)> {
    let mission: Option<String> = tx
        .query_row(
            "SELECT mission_id FROM mission_plans WHERE job_id=?1
       UNION ALL SELECT mission_id FROM mission_runs WHERE ai_id=?1
       UNION ALL SELECT mission_id FROM operational_attempts WHERE job_id=?1 AND mission_id IS NOT NULL LIMIT 1",
            [job],
            |row| row.get(0),
        )
        .optional()?;
    let scope = match &mission {
        Some(mission) => mission_scope(tx, mission)?,
        None => format!("job:{job}"),
    };
    Ok((scope, mission))
}
fn ensure(tx: &Transaction<'_>, scope: &str) -> CoreResult<()> {
    tx.execute(
        "INSERT OR IGNORE INTO operational_budgets(scope_id,budget,usage) VALUES(?1,?2,?3)",
        params![
            scope,
            serde_json::to_string(&MissionBudget::default())?,
            serde_json::to_string(&MissionUsage::default())?
        ],
    )?;
    adopt_graph_attempts(tx, scope)?;
    Ok(())
}
fn minimum_optional(a: Option<u64>, b: Option<u64>) -> Option<u64> {
    match (a, b) {
        (Some(a), Some(b)) => Some(a.min(b)),
        (a, b) => a.or(b),
    }
}
/// Individually planned missions can join an RFC graph after their planning
/// attempts have completed. Move those receipts, not just future calls, into
/// the shared ledger without resetting usage or expanding any earlier cap.
fn adopt_graph_attempts(tx: &Transaction<'_>, scope: &str) -> CoreResult<()> {
    let graph = if let Some(graph) = scope.strip_prefix("graph:") {
        Some(graph.to_owned())
    } else if let Some(mission) = scope.strip_prefix("mission:") {
        tx.query_row(
            "SELECT graph_id FROM task_graph_planner_roots WHERE mission_id=?1",
            [mission],
            |row| row.get::<_, String>(0),
        )
        .optional()?
    } else {
        None
    };
    let Some(graph) = graph else {
        return Ok(());
    };
    let old_scopes: Vec<String> = tx
        .prepare(
            "SELECT DISTINCT b.scope_id FROM operational_budgets b
        JOIN task_graph_missions c ON b.scope_id='mission:'||c.mission_id
        WHERE c.graph_id=?1 AND b.scope_id<>?2",
        )?
        .query_map(params![graph, scope], |row| row.get(0))?
        .collect::<Result<_, _>>()?;
    if old_scopes.is_empty() {
        return Ok(());
    }
    let (raw, mut started, mut last): (String, Option<i64>, Option<i64>) = tx.query_row(
        "SELECT budget,started_ms,last_seen_ms FROM operational_budgets WHERE scope_id=?1",
        [scope],
        |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
    )?;
    let mut budget: MissionBudget = serde_json::from_str(&raw)?;
    for old_scope in old_scopes {
        let (raw, old_started, old_last): (String, Option<i64>, Option<i64>) = tx.query_row(
            "SELECT budget,started_ms,last_seen_ms FROM operational_budgets WHERE scope_id=?1",
            [&old_scope],
            |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?)),
        )?;
        let old: MissionBudget = serde_json::from_str(&raw)?;
        budget.elapsed_ms = budget.elapsed_ms.min(old.elapsed_ms);
        budget.inference_calls = budget.inference_calls.min(old.inference_calls);
        budget.tokens = minimum_optional(budget.tokens, old.tokens);
        budget.ram_bytes = minimum_optional(budget.ram_bytes, old.ram_bytes);
        budget.vram_bytes = minimum_optional(budget.vram_bytes, old.vram_bytes);
        started = match (started, old_started) {
            (Some(a), Some(b)) => Some(a.min(b)),
            (a, b) => a.or(b),
        };
        last = match (last, old_last) {
            (Some(a), Some(b)) => Some(a.max(b)),
            (a, b) => a.or(b),
        };
        tx.execute(
            "UPDATE operational_attempts SET scope_id=?2 WHERE scope_id=?1",
            params![old_scope, scope],
        )?;
        // Its setting remains in the immutable event history. All receipts now
        // reference the shared budget, so retire only this duplicate container.
        tx.execute(
            "DELETE FROM operational_budgets WHERE scope_id=?1",
            [&old_scope],
        )?;
    }
    let completed:Vec<(Option<String>,Option<i64>)>=tx.prepare("SELECT metrics,elapsed_ms FROM operational_attempts WHERE scope_id=?1 AND status<>'running'")?
        .query_map([scope],|row|Ok((row.get(0)?,row.get(1)?)))?.collect::<Result<_,_>>()?;
    let mut usage = MissionUsage::default();
    for (metrics, elapsed) in completed {
        let metrics = metrics
            .map(|raw| serde_json::from_str::<WorkerMetrics>(&raw))
            .transpose()?
            .unwrap_or_else(WorkerMetrics::unavailable);
        usage.record(&metrics, elapsed.unwrap_or(0).max(0) as u64);
    }
    tx.execute("UPDATE operational_budgets SET budget=?2,usage=?3,started_ms=?4,last_seen_ms=?5 WHERE scope_id=?1",
        params![scope,serde_json::to_string(&budget)?,serde_json::to_string(&usage)?,started,last])?;
    store::event(
        tx,
        "operational_graph_budget_adopted",
        json!({"version":1,"scope_id":scope,"graph_id":graph}),
    )?;
    Ok(())
}
fn state(
    tx: &Transaction<'_>,
    scope: &str,
) -> CoreResult<(MissionBudget, MissionUsage, Option<u64>)> {
    let (budget, usage, started, last): (String, String, Option<i64>, Option<i64>) = tx.query_row(
        "SELECT budget,usage,started_ms,last_seen_ms FROM operational_budgets WHERE scope_id=?1",
        [scope],
        |row| Ok((row.get(0)?, row.get(1)?, row.get(2)?, row.get(3)?)),
    )?;
    let mut usage: MissionUsage = serde_json::from_str(&usage)?;
    let now = now_ms()?;
    if last.is_some_and(|last| now < last.max(0) as u64) {
        return Err(CoreError::new(
            "budget_clock_unavailable",
            "Clock moved backwards; mission admission stopped",
        ));
    }
    usage.elapsed_ms = started.map_or(0, |started| now.saturating_sub(started.max(0) as u64));
    usage.attempts = tx
        .query_row::<i64, _, _>(
            "SELECT COUNT(*) FROM operational_attempts WHERE scope_id=?1",
            [scope],
            |row| row.get(0),
        )?
        .max(0) as u64;
    Ok((
        serde_json::from_str(&budget)?,
        usage,
        started.map(|value| value.max(0) as u64),
    ))
}
fn admission_error(decision: Admission) -> CoreError {
    let label = serde_json::to_value(decision).unwrap_or(Value::Null);
    CoreError::new(
        &format!("budget_{}", label.as_str().unwrap_or("unavailable")),
        "Mission resource admission refused; inspect its operational budget and counters",
    )
}
pub(crate) fn admit(tx: &Transaction<'_>, launch: &Launch) -> CoreResult<()> {
    let (scope, _) = job_scope(tx, &launch.id)?;
    ensure(tx, &scope)?;
    let (budget, usage, _) = state(tx, &scope)?;
    let remote = !launch
        .endpoint
        .strip_prefix("http://")
        .is_some_and(|endpoint| {
            endpoint
                .strip_suffix("/v1")
                .unwrap_or(endpoint)
                .strip_prefix("127.0.0.1:")
                .or_else(|| {
                    endpoint
                        .strip_suffix("/v1")
                        .unwrap_or(endpoint)
                        .strip_prefix("[::1]:")
                })
                .and_then(|port| port.parse::<u16>().ok())
                .is_some_and(|port| port > 0)
        });
    let decision = budget.admit(
        &usage,
        launch.generation.timeout_ms.saturating_add(8_000),
        remote,
        None,
        None,
    );
    if decision != Admission::Allowed {
        return Err(admission_error(decision));
    }
    Ok(())
}
pub(crate) fn begin(tx: &Transaction<'_>, launch: &Launch, lease: &str) -> CoreResult<()> {
    let (scope, mission) = job_scope(tx, &launch.id)?;
    ensure(tx, &scope)?;
    let now = now_ms()?;
    let attempt = store::digest(&lease)?;
    let snapshot = crate::operational::memory_snapshot();
    let inserted = tx.execute("INSERT OR IGNORE INTO operational_attempts(attempt_id,scope_id,job_id,mission_id,model_id,purpose,started_ms,status,snapshot)
        VALUES(?1,?2,?3,?4,?5,?6,?7,'running',?8)",params![attempt,scope,launch.id,mission,launch.model_id,
        serde_json::to_value(launch.purpose)?.as_str().unwrap_or("unavailable"),now as i64,serde_json::to_string(&snapshot)?])?;
    if inserted > 0 {
        tx.execute("UPDATE operational_budgets SET started_ms=COALESCE(started_ms,?2),last_seen_ms=?2 WHERE scope_id=?1",params![scope,now as i64])?;
        store::event(
            tx,
            "operational_attempt_started",
            json!({"version":1,"attempt_id":attempt,"scope_id":scope,"job_id":launch.id,
            "mission_id":mission,"model_id":launch.model_id,"model_selection":"pinned_launch","response_cache":"disabled","snapshot":snapshot}),
        )?;
    }
    Ok(())
}
pub(crate) fn finish(
    tx: &Transaction<'_>,
    job: &str,
    lease: &str,
    metrics: &WorkerMetrics,
    elapsed_ms: u64,
    outcome: &str,
) -> CoreResult<()> {
    let attempt = store::digest(&lease)?;
    let row: Option<(String, String)> = tx
        .query_row(
            "SELECT scope_id,status FROM operational_attempts WHERE attempt_id=?1 AND job_id=?2",
            params![attempt, job],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?;
    let Some((scope, status)) = row else {
        return Ok(());
    };
    if status != "running" {
        return Ok(());
    }
    // Only a fixed outcome class is persisted. Arbitrary error text is excluded.
    let outcome = match outcome {
        "completed" => "completed",
        "cancelled" => "cancelled",
        "preempted" => "preempted",
        "worker_interrupted" => "worker_interrupted",
        _ => "failed",
    };
    let now = now_ms()?;
    let raw: String = tx.query_row(
        "SELECT usage FROM operational_budgets WHERE scope_id=?1",
        [&scope],
        |row| row.get(0),
    )?;
    let mut usage: MissionUsage = serde_json::from_str(&raw)?;
    usage.record(metrics, elapsed_ms);
    tx.execute("UPDATE operational_attempts SET status=?2,finished_ms=?3,elapsed_ms=?4,outcome=?5,metrics=?6 WHERE attempt_id=?1 AND status='running'",
        params![attempt,if outcome=="worker_interrupted"{"interrupted"}else{"finished"},now as i64,elapsed_ms.min(i64::MAX as u64) as i64,outcome,serde_json::to_string(metrics)?])?;
    tx.execute("UPDATE operational_budgets SET usage=?2,last_seen_ms=MAX(COALESCE(last_seen_ms,0),?3) WHERE scope_id=?1",
        params![scope,serde_json::to_string(&usage)?,now as i64])?;
    store::event(
        tx,
        "operational_attempt_finished",
        json!({"version":1,"attempt_id":attempt,"scope_id":scope,"job_id":job,
        "outcome":outcome,"elapsed_ms":elapsed_ms,"metrics":metrics}),
    )?;
    Ok(())
}
pub(crate) fn recover(tx: &Transaction<'_>) -> CoreResult<()> {
    let attempts:Vec<(String,String,String,i64)> = tx.prepare("SELECT attempt_id,job_id,scope_id,started_ms FROM operational_attempts WHERE status='running'")?
        .query_map([],|row|Ok((row.get(0)?,row.get(1)?,row.get(2)?,row.get(3)?)))?.collect::<Result<_,_>>()?;
    let now = now_ms()?;
    for (attempt, job, scope, start) in attempts {
        let raw: String = tx.query_row(
            "SELECT usage FROM operational_budgets WHERE scope_id=?1",
            [&scope],
            |row| row.get(0),
        )?;
        let mut usage: MissionUsage = serde_json::from_str(&raw)?;
        let metrics = WorkerMetrics::unavailable();
        usage.record(&metrics, now.saturating_sub(start.max(0) as u64));
        tx.execute("UPDATE operational_attempts SET status='interrupted',finished_ms=?2,elapsed_ms=?3,outcome='worker_interrupted',metrics=?4 WHERE attempt_id=?1",
            params![attempt,now as i64,now.saturating_sub(start.max(0) as u64) as i64,serde_json::to_string(&metrics)?])?;
        tx.execute(
            "UPDATE operational_budgets SET usage=?2 WHERE scope_id=?1",
            params![scope, serde_json::to_string(&usage)?],
        )?;
        store::event(
            tx,
            "operational_attempt_interrupted",
            json!({"version":1,"attempt_id":attempt,"scope_id":scope,"job_id":job,"metrics":metrics}),
        )?;
    }
    Ok(())
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct BudgetSet {
    mission_id: String,
    budget: MissionBudget,
}
#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct Query {
    mission_id: Option<String>,
    job_id: Option<String>,
    limit: Option<u32>,
}
pub(crate) fn dispatch(tx: &Transaction<'_>, action: &str, payload: &Value) -> CoreResult<Value> {
    if action == "budget_set" {
        let input: BudgetSet = serde_json::from_value(payload.clone())?;
        existing_mission(tx, &input.mission_id)?;
        if input.budget.elapsed_ms == 0
            || input.budget.elapsed_ms > 86_400_000
            || input.budget.inference_calls > 10_000
            || [
                input.budget.tokens,
                input.budget.ram_bytes,
                input.budget.vram_bytes,
            ]
            .into_iter()
            .flatten()
            .any(|value| value > (1_u64 << 53) - 1)
        {
            return Err(CoreError::invalid("Invalid operational budget"));
        }
        let scope = mission_scope(tx, &input.mission_id)?;
        ensure(tx, &scope)?;
        let (old, _, started) = state(tx, &scope)?;
        if started.is_some()
            && (input.budget.elapsed_ms > old.elapsed_ms
                || input.budget.inference_calls > old.inference_calls
                || !tighter_optional(input.budget.tokens, old.tokens)
                || !tighter_optional(input.budget.ram_bytes, old.ram_bytes)
                || !tighter_optional(input.budget.vram_bytes, old.vram_bytes))
        {
            return Err(CoreError::new(
                "budget_expansion_forbidden",
                "Started mission budgets may only be tightened",
            ));
        }
        tx.execute(
            "UPDATE operational_budgets SET budget=?2 WHERE scope_id=?1",
            params![scope, serde_json::to_string(&input.budget)?],
        )?;
        store::event(
            tx,
            "operational_budget_set",
            json!({"version":1,"scope_id":scope,"budget":input.budget}),
        )?;
        return Ok(
            json!({"version":1,"scope_id":scope,"budget":input.budget,"strict_token_budget":"requires_trusted_input_token_bound","remote_inference_calls_limit":0}),
        );
    }
    let input: Query = serde_json::from_value(payload.clone())?;
    let scope = match (&input.mission_id, &input.job_id) {
        (Some(mission), None) => {
            existing_mission(tx, mission)?;
            mission_scope(tx, mission)?
        }
        (None, Some(job)) => {
            bounded(job, "job_id", 128)?;
            let exists: bool = tx.query_row(
                "SELECT EXISTS(SELECT 1 FROM ai_jobs WHERE id=?1)",
                [job],
                |row| row.get(0),
            )?;
            if !exists {
                return Err(CoreError::new("not_found", "Job does not exist"));
            }
            job_scope(tx, job)?.0
        }
        _ => {
            return Err(CoreError::invalid(
                "Select exactly one mission_id or job_id",
            ));
        }
    };
    ensure(tx, &scope)?;
    match action {
        "budget_get" => {
            let (budget, usage, _) = state(tx, &scope)?;
            let (retries,failures,duration):(i64,i64,i64)=tx.query_row("SELECT COUNT(*)-COUNT(DISTINCT job_id),
                COALESCE(SUM(CASE WHEN outcome IN ('failed','worker_interrupted') THEN 1 ELSE 0 END),0),COALESCE(SUM(elapsed_ms),0)
                FROM operational_attempts WHERE scope_id=?1",[&scope],|row|Ok((row.get(0)?,row.get(1)?,row.get(2)?)))?;
            Ok(
                json!({"version":1,"scope_id":scope,"budget":budget,"usage":usage,"retry_attempts":retries,"failed_attempts":failures,"attempt_duration_ms":duration,
            "remote_inference_calls_limit":0,"token_counter":"provider_reported_or_unavailable","ram_scope":"worker_and_provider_separate","vram_scope":"provider_only_when_measured"}),
            )
        }
        "attempts" => {
            let limit = input.limit.unwrap_or(50);
            if !(1..=200).contains(&limit) {
                return Err(CoreError::invalid("Invalid limit"));
            }
            let mut query=tx.prepare("SELECT attempt_id,job_id,mission_id,model_id,purpose,started_ms,finished_ms,elapsed_ms,status,outcome,metrics,snapshot
                FROM operational_attempts WHERE scope_id=?1 ORDER BY started_ms,attempt_id LIMIT ?2")?;
            let rows=query.query_map(params![scope,limit],|row|Ok(json!({"version":1,"attempt_id":row.get::<_,String>(0)?,"job_id":row.get::<_,String>(1)?,
                "mission_id":row.get::<_,Option<String>>(2)?,"model_id":row.get::<_,String>(3)?,"purpose":row.get::<_,String>(4)?,
                "started_ms":row.get::<_,i64>(5)?,"finished_ms":row.get::<_,Option<i64>>(6)?,"elapsed_ms":row.get::<_,Option<i64>>(7)?,
                "status":row.get::<_,String>(8)?,"outcome":row.get::<_,Option<String>>(9)?,
                "metrics":row.get::<_,Option<String>>(10)?.and_then(|raw|serde_json::from_str::<Value>(&raw).ok()),
                "snapshot":serde_json::from_str::<Value>(&row.get::<_,String>(11)?).ok()})))?.collect::<Result<Vec<_>,_>>()?;
            Ok(json!({"version":1,"scope_id":scope,"attempts":rows}))
        }
        _ => Err(CoreError::invalid("Unknown operational action")),
    }
}
