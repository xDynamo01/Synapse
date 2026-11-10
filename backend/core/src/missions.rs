use crate::{
    contracts::{CoreError, CoreResult, MissionContract, bounded, scope},
    store,
};
use rusqlite::{OptionalExtension, Transaction, params};
use serde_json::{Value, json};

fn validate(contract: &MissionContract) -> CoreResult<()> {
    if contract.version != 1 {
        return Err(CoreError::new(
            "unsupported_version",
            "Mission contract version must be 1",
        ));
    }
    scope(&contract.scope)?;
    bounded(&contract.objective, "objective", 2048)?;
    bounded(&contract.rollback, "rollback", 2048)?;
    if contract.actions.is_empty()
        || contract.actions.len() > 32
        || contract.resources.is_empty()
        || contract.resources.len() > 64
    {
        return Err(CoreError::invalid(
            "Mission actions and resources must be bounded, nonempty lists",
        ));
    }
    for action in &contract.actions {
        bounded(action, "action", 128)?;
    }
    for resource in &contract.resources {
        bounded(resource, "resource", 512)?;
    }
    if [
        &contract.artifact_digests,
        &contract.artifact_previous_digests,
    ]
    .iter()
    .any(|digests| {
        digests.len() > 64
            || digests.iter().any(|(path, digest)| {
                !contract.resources.contains(path)
                    || digest.len() != 64
                    || !digest
                        .bytes()
                        .all(|b| b.is_ascii_digit() || (b'a'..=b'f').contains(&b))
            })
    }) {
        return Err(CoreError::invalid(
            "Artifact digests must bind approved resources to lowercase SHA-256",
        ));
    }
    Ok(())
}

pub(crate) fn propose(
    tx: &Transaction<'_>,
    id: &str,
    contract: &MissionContract,
) -> CoreResult<Value> {
    bounded(id, "mission_id", 128)?;
    validate(contract)?;
    crate::planner::validate_seal(tx, id, contract)?;
    if let Some(pin) = &contract.skill {
        if pin.scope != contract.scope {
            return Err(CoreError::new(
                "permission_denied",
                "Skill scope differs from mission",
            ));
        }
        let row: Option<(String, String)> = tx
            .query_row(
                "SELECT manifest,digest FROM skills WHERE scope=?1 AND id=?2 AND version=?3",
                params![pin.scope, pin.id, pin.version],
                |r| Ok((r.get(0)?, r.get(1)?)),
            )
            .optional()?;
        let (manifest, digest) =
            row.ok_or_else(|| CoreError::new("not_found", "Pinned Skill not found"))?;
        let skill: crate::contracts::SkillManifest = serde_json::from_str(&manifest)?;
        if digest != pin.digest || store::digest(&skill)? != digest {
            return Err(CoreError::new(
                "contract_conflict",
                "Pinned Skill digest differs",
            ));
        }
        if skill
            .permissions
            .iter()
            .any(|p| !contract.actions.contains(p))
            || skill.tools.iter().any(|p| !contract.actions.contains(p))
        {
            return Err(CoreError::new(
                "permission_denied",
                "Skill declarations exceed mission actions",
            ));
        }
    }
    let duplicate: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM missions WHERE id=?1)",
        [id],
        |r| r.get(0),
    )?;
    if duplicate {
        return Err(CoreError::new(
            "already_exists",
            "Mission ID already exists",
        ));
    }
    let digest = store::digest(contract)?;
    tx.execute(
        "INSERT INTO missions(id,contract,contract_digest,state) VALUES(?1,?2,?3,'proposed')",
        params![id, serde_json::to_string(contract)?, digest],
    )?;
    store::event(
        tx,
        "mission_proposed",
        json!({"mission_id":id,"contract_digest":digest,"scope":contract.scope}),
    )?;
    Ok(json!({"mission_id":id,"contract":contract,"contract_digest":digest,"state":"proposed"}))
}

pub(crate) fn approve(tx: &Transaction<'_>, id: &str, contract_digest: &str) -> CoreResult<Value> {
    bounded(id, "mission_id", 128)?;
    bounded(contract_digest, "contract_digest", 64)?;
    let (recorded, state) = read_status(tx, id)?;
    if state != "proposed" {
        return Err(CoreError::new(
            "invalid_transition",
            "Only a proposed mission can be approved",
        ));
    }
    if contract_digest != recorded {
        return Err(CoreError::new(
            "contract_conflict",
            "Approved digest differs from the proposed contract",
        ));
    }
    tx.execute("UPDATE missions SET state='approved' WHERE id=?1", [id])?;
    store::event(
        tx,
        "mission_approved",
        json!({"mission_id":id,"contract_digest":recorded}),
    )?;
    Ok(json!({"mission_id":id,"contract_digest":recorded,"state":"approved"}))
}

pub(crate) fn stop(
    tx: &Transaction<'_>,
    id: &str,
    target: &str,
    reason: &str,
) -> CoreResult<Value> {
    bounded(id, "mission_id", 128)?;
    bounded(reason, "reason", 2048)?;
    let (_, state) = read_status(tx, id)?;
    let allowed = match target {
        "cancelled" => state == "proposed" || state == "approved",
        "revoked" => state == "approved",
        _ => false,
    };
    if !allowed {
        return Err(CoreError::new(
            "invalid_transition",
            "Mission cannot enter requested terminal state",
        ));
    }
    tx.execute(
        "UPDATE missions SET state=?2,reason=?3 WHERE id=?1",
        params![id, target, reason],
    )?;
    store::event(
        tx,
        if target == "cancelled" {
            "mission_cancelled"
        } else {
            "mission_revoked"
        },
        json!({"mission_id":id,"reason":reason}),
    )?;
    Ok(json!({"mission_id":id,"state":target,"reason":reason}))
}

fn read_status(tx: &Transaction<'_>, id: &str) -> CoreResult<(String, String)> {
    tx.query_row(
        "SELECT contract_digest,state FROM missions WHERE id=?1",
        [id],
        |r| Ok((r.get(0)?, r.get(1)?)),
    )
    .optional()?
    .ok_or_else(|| CoreError::new("not_found", "Mission not found"))
}

pub(crate) fn get(tx: &Transaction<'_>, id: &str) -> CoreResult<Value> {
    bounded(id, "mission_id", 128)?;
    let row: Option<(String, String, String, Option<String>)> = tx
        .query_row(
            "SELECT contract,contract_digest,state,reason FROM missions WHERE id=?1",
            [id],
            |r| Ok((r.get(0)?, r.get(1)?, r.get(2)?, r.get(3)?)),
        )
        .optional()?;
    let (contract, digest, state, reason) =
        row.ok_or_else(|| CoreError::new("not_found", "Mission not found"))?;
    Ok(
        json!({"mission_id":id,"contract":serde_json::from_str::<Value>(&contract)?,"contract_digest":digest,"state":state,"reason":reason}),
    )
}
