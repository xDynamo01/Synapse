//! Destination checks for a future isolated browser transport. No network I/O.
use std::net::{IpAddr, Ipv4Addr, Ipv6Addr};
use url::{Host, Url};

#[derive(Debug, PartialEq, Eq)]
pub enum DestinationError {
    InvalidUrl,
    OriginDenied,
    AddressDenied,
}

pub struct NavigationPolicy {
    origin: url::Origin,
}

impl NavigationPolicy {
    pub fn new(approved_origin: &str) -> Result<Self, DestinationError> {
        let url = parse_public_https(approved_origin)?;
        if url.path() != "/" || url.query().is_some() || url.fragment().is_some() {
            return Err(DestinationError::InvalidUrl);
        }
        Ok(Self {
            origin: url.origin(),
        })
    }

    pub fn destination(&self, value: &str) -> Result<Url, DestinationError> {
        let url = parse_public_https(value)?;
        if url.origin() != self.origin {
            return Err(DestinationError::OriginDenied);
        }
        Ok(url)
    }

    pub fn redirect(&self, current: &Url, location: &str) -> Result<Url, DestinationError> {
        self.destination(current.as_str())?;
        if location.len() > 4096
            || location.trim() != location
            || location
                .bytes()
                .any(|byte| byte.is_ascii_control() || byte == b'\\')
        {
            return Err(DestinationError::InvalidUrl);
        }
        let first_segment = location.split(['/', '?', '#']).next().unwrap_or_default();
        if first_segment.contains(':') {
            return self.destination(location);
        }
        let next = current
            .join(location)
            .map_err(|_| DestinationError::InvalidUrl)?;
        self.destination(next.as_str())
    }

    /// Check all DNS answers and the actual peer. A transport must dial only
    /// the checked addresses, with TLS verification for the original host.
    pub fn check_peer(&self, resolved: &[IpAddr], peer: IpAddr) -> Result<(), DestinationError> {
        if !resolved.contains(&peer) || !resolved.iter().copied().all(public_address) {
            return Err(DestinationError::AddressDenied);
        }
        Ok(())
    }
}

fn parse_public_https(value: &str) -> Result<Url, DestinationError> {
    if !value
        .get(..8)
        .is_some_and(|prefix| prefix.eq_ignore_ascii_case("https://"))
        || value.len() > 4096
        || value.trim() != value
        || value.bytes().any(|b| b.is_ascii_control() || b == b'\\')
    {
        return Err(DestinationError::InvalidUrl);
    }
    let url = Url::parse(value).map_err(|_| DestinationError::InvalidUrl)?;
    let host_allowed = matches!(url.host(), Some(Host::Domain(host)) if host.contains('.') && !host.ends_with('.') && !["local", "localhost", "internal", "test", "invalid", "onion", "example", "arpa"].contains(&host.rsplit('.').next().unwrap_or_default()));
    if url.scheme() != "https"
        || url.port().is_some()
        || !url.username().is_empty()
        || url.password().is_some()
        || !host_allowed
    {
        return Err(DestinationError::InvalidUrl);
    }
    Ok(url)
}

/// Convert an untrusted search suggestion to a public HTTPS homepage.
pub fn public_https_origin(value: &str) -> Result<String, DestinationError> {
    Ok(parse_public_https(value)?.origin().ascii_serialization())
}

// These grants only cover public document reads. A browser worker must
// independently enforce DNS, connected peer and redirect restrictions.
pub(crate) fn request_origin(
    tx: &rusqlite::Transaction<'_>,
    mission_id: &str,
    destination: &str,
) -> crate::CoreResult<serde_json::Value> {
    use rusqlite::{OptionalExtension, params};
    use serde_json::{Value, json};
    let digest = browse_contract(tx, mission_id)?;
    let url = parse_public_https(destination)
        .map_err(|_| crate::CoreError::invalid("Browser destination must use public HTTPS"))?;
    if url.port_or_known_default() != Some(443) {
        return Err(crate::CoreError::invalid(
            "Browser destination must use HTTPS port 443",
        ));
    }
    let origin = url.origin().ascii_serialization();
    let request: Option<i64> = tx
        .query_row(
            "SELECT cursor FROM events WHERE kind='browser_origin_requested'
         AND json_extract(payload,'$.mission_id')=?1
         AND json_extract(payload,'$.contract_digest')=?2
         AND json_extract(payload,'$.origin')=?3 ORDER BY cursor DESC LIMIT 1",
            params![mission_id, digest, origin],
            |row| row.get(0),
        )
        .optional()?;
    let challenge = if let Some(cursor) = request {
        cursor as u64
    } else {
        let count: u32 = tx.query_row(
            "SELECT COUNT(*) FROM events WHERE kind='browser_origin_requested'
             AND json_extract(payload,'$.mission_id')=?1",
            [mission_id],
            |row| row.get(0),
        )?;
        if count >= 32 {
            return Err(crate::CoreError::new(
                "limit_exceeded",
                "Mission browser origin limit reached",
            ));
        }
        crate::store::event(
            tx,
            "browser_origin_requested",
            json!({"mission_id":mission_id,"contract_digest":digest,"origin":origin}),
        )?
    };
    let status = origin_decision(tx, challenge)?.unwrap_or_else(|| "pending".to_owned());
    Ok(
        json!({"mission_id":mission_id,"origin":origin,"challenge":challenge,"status":Value::String(status)}),
    )
}

pub(crate) fn decide_origin(
    tx: &rusqlite::Transaction<'_>,
    mission_id: &str,
    challenge: u64,
    allow: bool,
) -> crate::CoreResult<serde_json::Value> {
    use rusqlite::{OptionalExtension, params};
    use serde_json::json;
    let digest = browse_contract(tx, mission_id)?;
    let cursor = i64::try_from(challenge)
        .map_err(|_| crate::CoreError::invalid("Invalid browser challenge"))?;
    let origin: String = tx
        .query_row(
            "SELECT json_extract(payload,'$.origin') FROM events WHERE cursor=?1
         AND kind='browser_origin_requested' AND json_extract(payload,'$.mission_id')=?2
         AND json_extract(payload,'$.contract_digest')=?3",
            params![cursor, mission_id, digest],
            |row| row.get(0),
        )
        .optional()?
        .ok_or_else(|| {
            crate::CoreError::new("not_found", "Browser authorization request not found")
        })?;
    if origin_decision(tx, challenge)?.is_some() {
        return Err(crate::CoreError::new(
            "contract_conflict",
            "Browser authorization was already decided",
        ));
    }
    let status = if allow { "approved" } else { "denied" };
    let record = json!({"mission_id":mission_id,"contract_digest":digest,
                        "origin":origin,"challenge":challenge,"status":status});
    crate::store::event(tx, "browser_origin_decided", record.clone())?;
    Ok(record)
}

pub(crate) fn begin_read(
    tx: &rusqlite::Transaction<'_>,
    mission_id: &str,
    destination: &str,
) -> crate::CoreResult<serde_json::Value> {
    begin_read_receipt(tx, mission_id, destination, "read")
}

fn begin_read_receipt(
    tx: &rusqlite::Transaction<'_>,
    mission_id: &str,
    destination: &str,
    operation: &str,
) -> crate::CoreResult<serde_json::Value> {
    use serde_json::json;
    // A denied preflight rolls back the surrounding command savepoint.
    let permission = request_origin(tx, mission_id, destination)?;
    if permission["status"] != "approved" {
        return Err(crate::CoreError::new(
            "permission_denied",
            "Browser origin is not approved",
        ));
    }
    let receipt = json!({
        "mission_id":mission_id,
        "origin":permission["origin"],
        "challenge":permission["challenge"],
        "destination_digest":crate::store::digest(&destination)?,
        "status":"started","operation":operation,
    });
    let attempt = crate::store::event(tx, "browser_read_started", receipt.clone())?;
    Ok(json!({"attempt":attempt,"receipt":receipt}))
}

pub(crate) fn begin_download(
    tx: &rusqlite::Transaction<'_>,
    mission_id: &str,
    destination: &str,
) -> crate::CoreResult<serde_json::Value> {
    use serde_json::json;
    let checked = parse_public_https(destination)
        .map_err(|_| crate::CoreError::invalid("Invalid download destination"))?;
    if checked.fragment().is_some() {
        return Err(crate::CoreError::invalid("Invalid download destination"));
    }
    let mission = crate::missions::get(tx, mission_id)?;
    let contract = &mission["contract"];
    let action = contract["actions"]
        .as_array()
        .is_some_and(|actions| actions.contains(&json!("browser_download")));
    let resource = contract["resources"]
        .as_array()
        .is_some_and(|resources| resources.contains(&json!(destination)));
    if !action || !resource {
        return Err(crate::CoreError::new(
            "permission_denied",
            "Download is outside the approved contract",
        ));
    }
    begin_read_receipt(tx, mission_id, destination, "download")
}

pub(crate) fn begin_session_read(
    tx: &rusqlite::Transaction<'_>,
    mission_id: &str,
    destination: &str,
    session_handle: &str,
) -> crate::CoreResult<serde_json::Value> {
    use serde_json::json;
    let checked = parse_public_https(destination)
        .map_err(|_| crate::CoreError::invalid("Invalid authenticated destination"))?;
    if checked.as_str() != destination
        || checked.fragment().is_some()
        || !valid_handle(session_handle)
    {
        return Err(crate::CoreError::invalid(
            "Invalid authenticated read parameters",
        ));
    }
    let record = crate::missions::get(tx, mission_id)?;
    let contract = &record["contract"];
    let session = format!("session:{session_handle}");
    if !contract["actions"]
        .as_array()
        .is_some_and(|actions| actions.contains(&json!("browser_session_read")))
        || !contract["resources"].as_array().is_some_and(|resources| {
            resources.contains(&json!(destination)) && resources.contains(&json!(session))
        })
    {
        return Err(crate::CoreError::new(
            "permission_denied",
            "Authenticated read is outside the approved contract",
        ));
    }
    begin_read_receipt(tx, mission_id, destination, "session_read")
}

fn valid_handle(handle: &str) -> bool {
    handle.len() == 32
        && handle
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
}

pub(crate) fn begin_login(
    tx: &rusqlite::Transaction<'_>,
    mission_id: &str,
    page: &str,
    action: &str,
    probe: &str,
    expected_text: &str,
    credential_handle: &str,
) -> crate::CoreResult<serde_json::Value> {
    use rusqlite::params;
    use serde_json::json;
    let permission = request_origin(tx, mission_id, action)?;
    if permission["status"] != "approved" {
        return Err(crate::CoreError::new(
            "permission_denied",
            "Login origin is not approved",
        ));
    }
    let origin = permission["origin"]
        .as_str()
        .ok_or_else(|| crate::CoreError::invalid("Missing login origin"))?;
    let policy = NavigationPolicy::new(origin)
        .map_err(|_| crate::CoreError::invalid("Invalid login origin"))?;
    for address in [page, action, probe] {
        let checked = policy
            .destination(address)
            .map_err(|_| crate::CoreError::invalid("Login URL is outside the approved origin"))?;
        if checked.fragment().is_some() || checked.as_str() != address {
            return Err(crate::CoreError::invalid(
                "Login requires exact canonical HTTPS URLs",
            ));
        }
    }
    if credential_handle.len() != 32
        || !credential_handle
            .bytes()
            .all(|byte| byte.is_ascii_digit() || (b'a'..=b'f').contains(&byte))
    {
        return Err(crate::CoreError::invalid(
            "Invalid browser credential handle",
        ));
    }
    let record = crate::missions::get(tx, mission_id)?;
    let contract = &record["contract"];
    crate::contracts::bounded(expected_text, "login_verification_marker", 256)?;
    let credential = format!("credential:{credential_handle}");
    let marker = format!("marker:{expected_text}");
    if !contract["actions"]
        .as_array()
        .is_some_and(|actions| actions.contains(&json!("browser_login")))
        || !contract["resources"].as_array().is_some_and(|resources| {
            [page, action, probe, &credential, &marker]
                .into_iter()
                .all(|resource| resources.contains(&json!(resource)))
        })
    {
        return Err(crate::CoreError::new(
            "permission_denied",
            "Login parameters are outside the approved contract",
        ));
    }
    let digest = crate::store::digest(&action)?;
    let dispatched: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM events WHERE kind='browser_read_started'
         AND json_extract(payload,'$.mission_id')=?1 AND json_extract(payload,'$.operation')='login'
         AND json_extract(payload,'$.destination_digest')=?2)",
        params![mission_id, digest],
        |row| row.get(0),
    )?;
    if dispatched {
        return Err(crate::CoreError::new(
            "contract_conflict",
            "This mission already attempted the login",
        ));
    }
    let receipt = json!({"mission_id":mission_id,"origin":origin,"challenge":permission["challenge"],
        "destination_digest":digest,"operation":"login","status":"started",
        "read_digests":[crate::store::digest(&page)?, crate::store::digest(&probe)?, digest]});
    let attempt = crate::store::event(tx, "browser_read_started", receipt.clone())?;
    Ok(json!({"attempt":attempt,"receipt":receipt}))
}

pub(crate) fn authorize_dispatch(
    tx: &rusqlite::Transaction<'_>,
    mission_id: &str,
    attempt: u64,
    destination: &str,
    method: crate::contracts::BrowserNetworkMethod,
) -> crate::CoreResult<serde_json::Value> {
    use crate::contracts::BrowserNetworkMethod;
    use rusqlite::{OptionalExtension, params};
    use serde_json::{Value, json};
    browse_contract(tx, mission_id)?;
    let cursor = i64::try_from(attempt)
        .map_err(|_| crate::CoreError::invalid("Invalid browser read attempt"))?;
    let started: String = tx
        .query_row(
            "SELECT payload FROM events WHERE cursor=?1 AND kind='browser_read_started'
         AND json_extract(payload,'$.mission_id')=?2",
            params![cursor, mission_id],
            |row| row.get(0),
        )
        .optional()?
        .ok_or_else(|| crate::CoreError::new("not_found", "Browser attempt not found"))?;
    let started: Value = serde_json::from_str(&started)?;
    let finished: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM events WHERE kind='browser_read_finished'
         AND json_extract(payload,'$.attempt')=?1)",
        [cursor],
        |row| row.get(0),
    )?;
    let destination_digest = json!(crate::store::digest(&destination)?);
    let allowed = match method {
        BrowserNetworkMethod::Get if started["operation"] == "login" => started["read_digests"]
            .as_array()
            .is_some_and(|digests| digests.contains(&destination_digest)),
        BrowserNetworkMethod::Get if started["operation"] == "session_read" => {
            started["destination_digest"] == destination_digest
        }
        BrowserNetworkMethod::Post if started["operation"] == "login" => {
            started["destination_digest"] == destination_digest
        }
        _ => false,
    };
    if finished || !allowed {
        return Err(crate::CoreError::new(
            "permission_denied",
            "Browser dispatch is outside the open attempt",
        ));
    }
    let (total, posts): (u32, u32) = tx.query_row(
        "SELECT COUNT(*), COALESCE(SUM(json_extract(payload,'$.method')='post'),0)
         FROM events WHERE kind='browser_request_authorized'
         AND json_extract(payload,'$.attempt')=?1",
        [cursor],
        |row| Ok((row.get(0)?, row.get(1)?)),
    )?;
    if total >= 16 || (matches!(method, BrowserNetworkMethod::Post) && posts != 0) {
        return Err(crate::CoreError::new(
            "contract_conflict",
            "Browser dispatch limit reached",
        ));
    }
    crate::store::event(
        tx,
        "browser_request_authorized",
        json!({
            "mission_id":mission_id,"attempt":attempt,"origin":started["origin"],
            "method":method,"destination_digest":destination_digest
        }),
    )?;
    Ok(json!({"authorized":true}))
}

pub(crate) fn finish_read(
    tx: &rusqlite::Transaction<'_>,
    mission_id: &str,
    attempt: u64,
    outcome: crate::contracts::BrowserReadOutcome,
) -> crate::CoreResult<serde_json::Value> {
    use rusqlite::{OptionalExtension, params};
    use serde_json::json;
    let cursor = i64::try_from(attempt)
        .map_err(|_| crate::CoreError::invalid("Invalid browser read attempt"))?;
    let started: String = tx
        .query_row(
            "SELECT payload FROM events WHERE cursor=?1 AND kind='browser_read_started'
         AND json_extract(payload,'$.mission_id')=?2",
            params![cursor, mission_id],
            |row| row.get(0),
        )
        .optional()?
        .ok_or_else(|| crate::CoreError::new("not_found", "Browser read attempt not found"))?;
    let finished: bool = tx.query_row(
        "SELECT EXISTS(SELECT 1 FROM events WHERE kind='browser_read_finished'
         AND json_extract(payload,'$.attempt')=?1)",
        [cursor],
        |row| row.get(0),
    )?;
    if finished {
        return Err(crate::CoreError::new(
            "contract_conflict",
            "Browser read already has an outcome",
        ));
    }
    let started: serde_json::Value = serde_json::from_str(&started)?;
    let still_approved = browse_contract(tx, mission_id).is_ok();
    let receipt = json!({
        "mission_id":mission_id,"attempt":attempt,"origin":started["origin"],
        "destination_digest":started["destination_digest"],"outcome":outcome,
        "permission_active_at_finish":still_approved,
        "operation":started["operation"].as_str().unwrap_or("read"),
    });
    crate::store::event(tx, "browser_read_finished", receipt.clone())?;
    Ok(receipt)
}

fn browse_contract(tx: &rusqlite::Transaction<'_>, mission: &str) -> crate::CoreResult<String> {
    let record = crate::missions::get(tx, mission)?;
    let permitted = record["contract"]["actions"]
        .as_array()
        .is_some_and(|items| items.iter().any(|action| action == "browser_read"));
    if record["state"] != "approved" || !permitted {
        return Err(crate::CoreError::new(
            "permission_denied",
            "An approved browser_read mission is required",
        ));
    }
    Ok(record["contract_digest"]
        .as_str()
        .ok_or_else(|| crate::CoreError::invalid("Missing browser mission digest"))?
        .to_owned())
}

fn origin_decision(
    tx: &rusqlite::Transaction<'_>,
    challenge: u64,
) -> crate::CoreResult<Option<String>> {
    use rusqlite::OptionalExtension;
    Ok(tx.query_row(
        "SELECT json_extract(payload,'$.status') FROM events WHERE kind='browser_origin_decided'
         AND json_extract(payload,'$.challenge')=?1",
        [challenge as i64], |row| row.get(0),
    ).optional()?)
}

fn public_address(address: IpAddr) -> bool {
    match address {
        IpAddr::V4(ip) => public_v4(ip),
        IpAddr::V6(ip) => public_v6(ip),
    }
}

fn public_v4(ip: Ipv4Addr) -> bool {
    !matches!(
        ip.octets(),
        [0 | 10 | 127 | 224..=255, ..]
            | [100, 64..=127, ..]
            | [169, 254, ..]
            | [172, 16..=31, ..]
            | [192, 0, 0 | 2, _]
            | [192, 88, 99, _]
            | [192, 168, ..]
            | [198, 18 | 19, ..]
            | [198, 51, 100, _]
            | [203, 0, 113, _]
    )
}

fn public_v6(ip: Ipv6Addr) -> bool {
    matches!(ip.segments(), [0x2000..=0x3fff, ..])
        && !matches!(
            ip.segments(),
            [0x2001, 0..=0x1ff | 0xdb8, ..] | [0x2002, ..] | [0x3fff, 0..=0xfff, ..]
        )
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn navigation_and_redirect_require_the_exact_https_origin() {
        let policy = NavigationPolicy::new("https://EXAMPLE.com:443").unwrap();
        let start = policy.destination("https://example.com/a").unwrap();
        assert_eq!(policy.redirect(&start, "../b").unwrap().path(), "/b");
        for target in [
            "//other.example.com",
            "https://example.com:8443/",
            "http://example.com/",
            "https://u:p@example.com/",
            "https://127.1/",
            "file:///test",
            "https:example.com",
            " https://example.com/",
            "\\other.example.com",
        ] {
            assert!(policy.redirect(&start, target).is_err(), "{target}");
        }
        assert!(NavigationPolicy::new("https://example.com/path").is_err());
        assert!(NavigationPolicy::new("https://machine.local").is_err());
    }

    #[test]
    fn every_dns_answer_and_the_connected_peer_are_checked() {
        let policy = NavigationPolicy::new("https://example.com").unwrap();
        let public = "93.184.216.34".parse().unwrap();
        let public_v6 = "2606:4700::1111".parse().unwrap();
        assert!(policy.check_peer(&[public, public_v6], public_v6).is_ok());
        assert!(policy.check_peer(&[public], public_v6).is_err());
        for ip in [
            "127.0.0.1",
            "100.64.0.1",
            "169.254.169.254",
            "192.168.0.1",
            "::1",
            "::ffff:127.0.0.1",
            "fc00::1",
            "2002:7f00:1::",
            "2001:db8::1",
        ] {
            assert!(
                policy
                    .check_peer(&[public, ip.parse().unwrap()], public)
                    .is_err(),
                "{ip}"
            );
        }
    }
}
