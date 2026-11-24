use rusqlite::Connection;
use serde_json::{Value,json};
use synapse_core::Core;

fn call(core:&mut Core,id:&str,command:Value)->Value {
    serde_json::to_value(core.dispatch_line(&serde_json::to_vec(&json!({"version":1,"request_id":id,"command":command})).unwrap())).unwrap()
}

#[test]
fn populated_v15_extensions_migrate_once_without_losing_data_or_receipts(){
    let root=tempfile::tempdir().unwrap();
    let state=root.path().join("state");
    let mut core=Core::open(&state,root.path()).unwrap();
    let chat=call(&mut core,"chat",json!({"type":"chat_create","chat_id":"chat","title":"PRIVATE_CANARY","scope":"project:compat"}));
    assert_eq!(chat["ok"],true,"{chat}");
    drop(core);
    let db=Connection::open(state.join("core.sqlite3")).unwrap();
    db.execute("INSERT INTO orchestration_profiles VALUES('profile',?1)",[r#"{"resource_policy":"ECONOMICAL","model_mode":"automatic","memory_budget_bytes":1000000,"assignments":{},"purpose_modes":{}}"#]).unwrap();
    db.execute("INSERT INTO input_records VALUES('old','chat',NULL,NULL,'conversation','model','{}','{}')",[]).unwrap();
    db.execute("DELETE FROM schema_migrations WHERE version=16",[]).unwrap();
    db.pragma_update(None,"user_version",15).unwrap();
    drop(db);
    let mut core=Core::open(&state,root.path()).unwrap();
    assert_eq!(call(&mut core,"chat",json!({"type":"chat_create","chat_id":"chat","title":"PRIVATE_CANARY","scope":"project:compat"})),chat);
    let compatibility=call(&mut core,"compat",json!({"type":"compatibility"}));
    assert_eq!(compatibility["result"]["storage_schema"],16);
    assert_eq!(compatibility["result"]["worker_versions"],json!([4,5]));
    drop(core);
    let core=Core::open(&state,root.path()).unwrap();drop(core);
    let db=Connection::open(state.join("core.sqlite3")).unwrap();
    assert_eq!(db.query_row("SELECT count(*) FROM schema_migrations WHERE version=16",[],|r|r.get::<_,u32>(0)).unwrap(),1);
    assert_eq!(db.query_row("SELECT count(*) FROM input_records WHERE id='old'",[],|r|r.get::<_,u32>(0)).unwrap(),1);
    assert_eq!(db.query_row("SELECT settings FROM orchestration_profiles WHERE id='profile'",[],|r|r.get::<_,String>(0)).unwrap().contains("ECONOMICAL"),true);
}

#[test]
fn newer_database_and_incomplete_restore_fail_closed_without_deleting_data(){
    let root=tempfile::tempdir().unwrap();let state=root.path().join("state");
    drop(Core::open(&state,root.path()).unwrap());
    let db=Connection::open(state.join("core.sqlite3")).unwrap();
    db.execute("INSERT INTO metadata VALUES('canary','PRESERVE')",[]).unwrap();
    db.pragma_update(None,"user_version",17).unwrap();drop(db);
    let error=Core::open(&state,root.path()).err().unwrap();
    assert_eq!(error.code,"unsupported_storage_version");
    let db=Connection::open(state.join("core.sqlite3")).unwrap();
    assert_eq!(db.query_row("SELECT value FROM metadata WHERE key='canary'",[],|r|r.get::<_,String>(0)).unwrap(),"PRESERVE");
    db.pragma_update(None,"user_version",16).unwrap();drop(db);
    std::fs::write(state.join(".restore-incomplete"),"incomplete").unwrap();
    assert_eq!(Core::open(&state,root.path()).err().unwrap().code,"state_restore_incomplete");
}

#[test]
fn numeric_schema_without_required_shape_is_not_accepted(){
    let root=tempfile::tempdir().unwrap();let state=root.path().join("state");
    drop(Core::open(&state,root.path()).unwrap());
    let db=Connection::open(state.join("core.sqlite3")).unwrap();
    db.execute("DROP TABLE operational_attempts",[]).unwrap();drop(db);
    assert_eq!(Core::open(&state,root.path()).err().unwrap().code,"incompatible_storage_schema");
}

