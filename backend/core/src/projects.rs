use crate::{
    CoreError, CoreResult,
    contracts::{self, ToolOperation},
    store, tools,
};
use rusqlite::{OptionalExtension, Transaction, params};
use serde_json::{Value, json};
use std::path::{Path, PathBuf};

fn record(tx: &Transaction<'_>, scope: &str) -> CoreResult<Option<(String, String)>> {
    Ok(tx
        .query_row(
            "SELECT root, identity FROM workspace_projects WHERE scope=?1",
            [scope],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?)
}

fn pin(root: &Path, state: &Path) -> CoreResult<tools::Broker> {
    tools::prepare(root, state, &ToolOperation::List { path: ".".into() })
}

pub(crate) fn register(
    tx: &Transaction<'_>,
    scope: &str,
    root: &str,
    state: &Path,
) -> CoreResult<Value> {
    contracts::scope(scope)?;
    contracts::bounded(root, "root", 4096)?;
    let root = Path::new(root);
    if !root.is_absolute() {
        return Err(CoreError::invalid(
            "Project root must be an absolute directory",
        ));
    }
    let broker = pin(root, state)?;
    crate::self_change::guard_project_root(root)?;
    let identity = broker.root_identity()?;
    let root = broker.target();
    if let Some((recorded_root, recorded_identity)) = record(tx, scope)? {
        if recorded_root == root && recorded_identity == identity {
            return Ok(json!({"scope":scope,"root":root}));
        }
        return Err(CoreError::new(
            "project_binding_conflict",
            "Project scope is already bound to another directory or identity",
        ));
    }
    let occupied: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM workspace_projects WHERE identity=?1 OR root=?2)",
        params![identity, root],
        |row| row.get(0),
    )?;
    if occupied {
        return Err(CoreError::new(
            "project_binding_conflict",
            "Project directory is already bound to another scope",
        ));
    }
    tx.execute(
        "INSERT INTO workspace_projects(scope,root,identity) VALUES(?1,?2,?3)",
        params![scope, root, identity],
    )?;
    store::event(tx, "workspace_project_registered", json!({"scope":scope}))?;
    Ok(json!({"scope":scope,"root":root}))
}

pub(crate) fn get(tx: &Transaction<'_>, scope: &str, state: &Path) -> CoreResult<Value> {
    contracts::scope(scope)?;
    let (root, identity) = record(tx, scope)?
        .ok_or_else(|| CoreError::new("not_found", "Project scope is not registered"))?;
    let _guard = verify(&root, &identity, state)?;
    Ok(json!({"scope":scope,"root":root}))
}

pub(crate) enum ProjectRoot<'a> {
    Legacy(&'a Path),
    Registered {
        root: PathBuf,
        _guard: tools::Broker,
    },
}

impl ProjectRoot<'_> {
    pub(crate) fn path(&self) -> &Path {
        match self {
            Self::Legacy(path) => path,
            Self::Registered { root, .. } => root,
        }
    }
}

fn verify(root: &str, identity: &str, state: &Path) -> CoreResult<tools::Broker> {
    let changed = || {
        CoreError::new(
            "project_root_changed",
            "Registered project directory cannot be verified",
        )
    };
    let broker = pin(Path::new(root), state).map_err(|_| changed())?;
    crate::self_change::guard_effect(Path::new(root))?;
    if broker.root_identity().map_err(|_| changed())? != identity || broker.target() != root {
        return Err(changed());
    }
    Ok(broker)
}

// A missing binding remains legacy for the life of the mission. Registering
// the same scope later cannot redirect an existing mission or tool intent.
pub(crate) fn bind(
    tx: &Transaction<'_>,
    mission: &str,
    scope: &str,
    state: &Path,
) -> CoreResult<Option<String>> {
    let Some((root, identity)) = record(tx, scope)? else {
        return Ok(None);
    };
    let _guard = verify(&root, &identity, state)?;
    tx.execute(
        "INSERT INTO mission_project_bindings(mission_id,scope,root,identity) VALUES(?1,?2,?3,?4)",
        params![mission, scope, root, identity],
    )?;
    Ok(Some(root))
}

pub(crate) fn recorded_root(tx: &Transaction<'_>, mission: &str) -> CoreResult<Option<String>> {
    Ok(tx
        .query_row(
            "SELECT root FROM mission_project_bindings WHERE mission_id=?1",
            [mission],
            |row| row.get(0),
        )
        .optional()?)
}

pub(crate) fn for_mission<'a>(
    tx: &Transaction<'_>,
    mission: &str,
    fallback: &'a Path,
    state: &Path,
) -> CoreResult<ProjectRoot<'a>> {
    let binding: Option<(String, String)> = tx
        .query_row(
            "SELECT root,identity FROM mission_project_bindings WHERE mission_id=?1",
            [mission],
            |row| Ok((row.get(0)?, row.get(1)?)),
        )
        .optional()?;
    let Some((root, identity)) = binding else {
        crate::self_change::guard_effect(fallback)?;
        return Ok(ProjectRoot::Legacy(fallback));
    };
    let guard = verify(&root, &identity, state)?;
    Ok(ProjectRoot::Registered {
        root: root.into(),
        _guard: guard,
    })
}
